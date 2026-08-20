"""
auth.py — Autenticação via WordPress Headless (Simple JWT Login) + CAPTCHA visual.

Integra com o backend WordPress da Harpy P&D (harpypd.com.br) para validar
credenciais e obter tokens JWT. O CAPTCHA é gerado server-side em Python
(imagem distorcida + input) porque o Streamlit não suporta reCAPTCHA v2 nativo.
"""
import io
import json
import string
import random
import base64
from datetime import datetime, timedelta

import requests
import streamlit as st

try:
    from captcha.image import ImageCaptcha
    CAPTCHA_LIB_AVAILABLE = True
except ImportError:
    CAPTCHA_LIB_AVAILABLE = False

from config import (
    WP_AUTH_ENDPOINT,
    WP_AUTH_KEY,
    CAPTCHA_ENABLED,
    CAPTCHA_LENGTH,
    APP_TITLE,
)


# ============================================
# CAPTCHA Visual (Python-side)
# ============================================

def _generate_captcha_text(length: int = CAPTCHA_LENGTH) -> str:
    """Gera texto aleatório para o CAPTCHA (letras maiúsculas + dígitos)."""
    chars = string.ascii_uppercase + string.digits
    # Remove caracteres ambíguos (0/O, 1/I/L)
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("L", "").replace("1", "")
    return "".join(random.choices(chars, k=length))


def generate_captcha() -> None:
    """Gera uma nova imagem CAPTCHA e armazena a resposta em session_state."""
    captcha_text = _generate_captcha_text()
    st.session_state["_captcha_answer"] = captcha_text
    st.session_state["_captcha_timestamp"] = datetime.now().isoformat()

    if CAPTCHA_LIB_AVAILABLE:
        image_gen = ImageCaptcha(width=280, height=90, font_sizes=(42, 50, 56))
        img_bytes = image_gen.generate(captcha_text)
        st.session_state["_captcha_image"] = img_bytes.getvalue()
    else:
        # Fallback: CAPTCHA textual simples se a lib não estiver instalada
        st.session_state["_captcha_image"] = None


def verify_captcha(user_input: str) -> bool:
    """Valida a resposta do CAPTCHA (case-insensitive)."""
    answer = st.session_state.get("_captcha_answer", "")
    if not answer:
        return False
    return user_input.strip().upper() == answer.upper()


def _render_captcha_widget() -> str | None:
    """Renderiza o widget CAPTCHA e retorna o input do usuário."""
    if not CAPTCHA_ENABLED:
        return "__SKIP__"

    # Gera CAPTCHA novo se não existir ou se foi verificado
    if "_captcha_answer" not in st.session_state:
        generate_captcha()

    # Exibe imagem
    captcha_img = st.session_state.get("_captcha_image")
    if captcha_img:
        st.image(captcha_img, caption="Digite o código acima", width=280)
    else:
        # Fallback textual
        st.info(
            f"🔒 Código de verificação: "
            f"**{st.session_state['_captcha_answer']}**"
        )

    col1, col2 = st.columns([3, 1])
    with col1:
        captcha_input = st.text_input(
            "Código CAPTCHA",
            key="captcha_input",
            max_chars=CAPTCHA_LENGTH + 2,
            placeholder="Ex: A3BX9",
            label_visibility="collapsed",
        )
    with col2:
        if st.button("🔄", key="refresh_captcha", help="Gerar novo código"):
            generate_captcha()
            st.rerun()

    return captcha_input


# ============================================
# Autenticação WordPress Headless
# ============================================

def authenticate_wp(email: str, password: str) -> dict | None:
    """
    Autentica contra o WordPress via Simple JWT Login.

    POST /simple-jwt-login/v1/auth?AUTH_KEY=...
    Body: { "email": "...", "password": "..." }
    Resposta: { "success": true, "data": { "jwt": "eyJ..." } }

    Retorna o dict completo da resposta ou None se falhar.
    """
    try:
        response = requests.post(
            WP_AUTH_ENDPOINT,
            params={"AUTH_KEY": WP_AUTH_KEY},
            json={"email": email, "password": password},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=15,
        )

        data = response.json()

        if response.ok and data.get("success") and data.get("data", {}).get("jwt"):
            return data
        else:
            msg = (
                data.get("data", {}).get("message")
                or data.get("message")
                or "Credenciais inválidas."
            )
            st.error(f"❌ {msg}")
            return None

    except requests.exceptions.Timeout:
        st.error("⏳ Servidor demorou para responder. Tente novamente.")
        return None
    except requests.exceptions.ConnectionError:
        st.error("🔌 Erro de conexão com o servidor de autenticação.")
        return None
    except Exception as e:
        st.error(f"⚠️ Erro inesperado: {str(e)}")
        return None


def decode_jwt_payload(token: str) -> dict:
    """
    Decodifica o payload de um JWT sem verificar a assinatura.
    (A assinatura é responsabilidade do WordPress.)
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        # Adiciona padding se necessário
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception:
        return {}


# ============================================
# Controle de Sessão
# ============================================

def check_auth() -> bool:
    """Verifica se o usuário está autenticado."""
    return st.session_state.get("authenticated", False)


def logout() -> None:
    """Limpa a sessão e força re-render."""
    keys_to_clear = [
        "authenticated", "jwt_token", "user_email", "user_name",
        "_captcha_answer", "_captcha_image", "_captcha_timestamp",
        "captcha_input",
    ]
    for key in keys_to_clear:
        st.session_state.pop(key, None)


# ============================================
# Tela de Login
# ============================================

def render_login_page() -> None:
    """Renderiza a tela de login isolada com CAPTCHA + credenciais."""

    # CSS customizado para a tela de login
    st.markdown("""
    <style>
        /* Esconde sidebar e footer na tela de login */
        [data-testid="stSidebar"] { display: none; }
        footer { display: none; }
        #MainMenu { display: none; }

        .login-container {
            max-width: 420px;
            margin: 0 auto;
            padding: 2rem;
        }
        .login-header {
            text-align: center;
            margin-bottom: 2rem;
        }
        .login-header h1 {
            background: linear-gradient(135deg, #00C9FF, #92FE9D);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 1.8rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .login-header p {
            color: #8892a4;
            font-size: 0.9rem;
        }
        .login-divider {
            border: none;
            border-top: 1px solid #1E2330;
            margin: 1.5rem 0;
        }
        .security-badge {
            display: inline-block;
            background: rgba(0, 201, 255, 0.1);
            border: 1px solid rgba(0, 201, 255, 0.2);
            color: #00C9FF;
            font-size: 0.7rem;
            padding: 4px 12px;
            border-radius: 20px;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-top: 0.5rem;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="login-header">
        <h1>🔒 GEA ENG</h1>
        <p>Painel de Prospecção B2B — Indústrias Alimentícias</p>
        <span class="security-badge">🛡️ Acesso Restrito</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<hr class="login-divider">', unsafe_allow_html=True)

    # --- CAPTCHA ---
    captcha_input = _render_captcha_widget()

    st.markdown('<hr class="login-divider">', unsafe_allow_html=True)

    # --- Credenciais ---
    email = st.text_input(
        "📧 E-mail",
        key="login_email",
        placeholder="seu@email.com",
    )
    password = st.text_input(
        "🔑 Senha",
        type="password",
        key="login_password",
        placeholder="••••••••",
    )

    st.markdown("", unsafe_allow_html=True)

    # --- Botão de Login ---
    if st.button("🚀 Entrar no Painel", use_container_width=True, type="primary"):
        # Validar CAPTCHA
        if CAPTCHA_ENABLED and captcha_input != "__SKIP__":
            if not captcha_input:
                st.warning("⚠️ Preencha o código CAPTCHA.")
                return
            if not verify_captcha(captcha_input):
                st.error("❌ Código CAPTCHA incorreto. Tente novamente.")
                generate_captcha()
                st.rerun()
                return

        # Validar campos
        if not email or not password:
            st.warning("⚠️ Preencha e-mail e senha.")
            return

        # Autenticar via WordPress
        with st.spinner("🔐 Autenticando via Harpy P&D..."):
            result = authenticate_wp(email, password)

        if result:
            jwt_token = result["data"]["jwt"]
            payload = decode_jwt_payload(jwt_token)

            st.session_state["authenticated"] = True
            st.session_state["jwt_token"] = jwt_token
            st.session_state["user_email"] = email

            # Extrair nome do payload JWT (estrutura Simple JWT Login)
            user_data = payload.get("data", {}).get("user", {})
            st.session_state["user_name"] = (
                user_data.get("user_nicename")
                or user_data.get("user_login")
                or email.split("@")[0]
            )

            # Limpar CAPTCHA da sessão
            for key in ["_captcha_answer", "_captcha_image", "_captcha_timestamp", "captcha_input"]:
                st.session_state.pop(key, None)

            st.success("✅ Login realizado com sucesso!")
            st.rerun()

    # Rodapé
    st.markdown("""
    <div style="text-align: center; margin-top: 3rem; color: #555; font-size: 0.75rem;">
        <p>Autenticação via WordPress Headless — Harpy P&D</p>
        <p>🔐 Sessão protegida por JWT (Simple JWT Login)</p>
    </div>
    """, unsafe_allow_html=True)
