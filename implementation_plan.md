# Dashboard B2B de Prospecção — Indústrias Alimentícias (SIF/MAPA)

Painel privado de prospecção B2B em **Streamlit** focado em indústrias do setor alimentício (CNAE 10.*) com registro SIF/MAPA. Autenticação via **WordPress Headless da Harpy P&D** (`harpypd.com.br`) usando plugin **Simple JWT Login**.

---

## User Review Required

> [!IMPORTANT]
> **reCAPTCHA v2 + Streamlit**: O reCAPTCHA v2 do Google é um widget JavaScript do lado do cliente (renderiza um `<iframe>` com o checkbox "Não sou um robô"). O Streamlit **não suporta componentes JS arbitrários nativamente** — não há como injetar o widget reCAPTCHA v2 de forma funcional na tela de login do Streamlit. A alternativa funcional e segura é um **CAPTCHA visual em Python** (imagem gerada com texto distorcido + campo de input). Isso é independente de ser WordPress Headless ou não — é uma limitação do Streamlit como framework.
>
> **Se precisar de reCAPTCHA v2 obrigatoriamente**, a opção seria migrar o login para uma página HTML separada (fora do Streamlit) que exibe o reCAPTCHA, valida no backend WordPress, e redireciona com o JWT para o Streamlit. Isso adiciona complexidade mas é viável.

> [!NOTE]
> **Autenticação via WordPress Headless da Harpy P&D — já mapeada:**
> - **Endpoint de Auth**: `https://harpypd.com.br/wp-json/simple-jwt-login/v1/auth?AUTH_KEY=API_HARPY_2026`
> - **Endpoint de Registro**: `https://harpypd.com.br/wp-json/simple-jwt-login/v1/users?AUTH_KEY=API_HARPY_2026`
> - **Perfil**: `https://harpypd.com.br/wp-json/wp/v2/users/me`
> - **Token**: armazenado em `st.session_state` (equivalente ao `localStorage.userToken` do frontend HTML)
> - **Resposta**: `data.data.jwt` no JSON de sucesso
> - **AUTH_KEY**: `API_HARPY_2026` (será movida para `.env`)

---

## Rate Limiting — BrasilAPI (Especificado)

> [!WARNING]
> **A BrasilAPI NÃO possui rate limit oficial documentado.** A proteção é feita pela **Vercel/Cloudflare WAF** (header `x-vercel-mitigated: deny`), que bloqueia padrões de tráfego suspeitos.
>
> **Estratégia implementada no `data_loader.py`:**
>
> | Parâmetro | Valor |
> |---|---|
> | Requests máx. por segundo | **3 req/s** (conservador) |
> | Delay entre requisições | **~350ms** (`time.sleep(0.35)`) |
> | Cache TTL (CNPJ) | **7 dias** (dados cadastrais mudam pouco) |
> | Retry com backoff | **3 tentativas**, delay 1s → 2s → 4s |
> | User-Agent customizado | `MKT-GEAENG-Dashboard/1.0 (contato@harpypd.com.br)` |
> | Tratamento 429 | Pausa de **60 segundos** + retry |
> | Tratamento 404 | Ignora CNPJ e continua |

---

## Open Questions

1. **A AUTH_KEY `API_HARPY_2026`** pode ficar no `.env` ou ela é pública de propósito no frontend? Vou mover para `.env` por padrão (mais seguro).

2. **Quem poderá acessar este dashboard?** Qualquer usuário cadastrado no WordPress Harpy, ou apenas um admin específico? Vou assumir **qualquer usuário com JWT válido da Harpy** pode acessar.

---

## Estrutura de Diretórios

```
MKT_GEAENG/
├── app.py                  # Entrada principal do Streamlit
├── auth.py                 # Autenticação via WP Headless (Simple JWT Login)
├── data_loader.py          # SIGSIF, BrasilAPI, geocodificação
├── config.py               # Constantes, CNAE mapping, URLs
├── requirements.txt        # Dependências Python
├── .env.example            # Template de variáveis de ambiente
├── .gitignore              # Bloqueio rigoroso de dados sensíveis
├── data/                   # Cache local (gitignored)
│   └── .gitkeep
└── assets/                 # Recursos estáticos
    └── .gitkeep
```

---

## Proposed Changes

### Configuração e Segurança

#### [NEW] [.gitignore](file:///c:/Users/caio_/Documents/GitHub/MKT_GEAENG/.gitignore)
Bloqueio rigoroso:
- `.env`, `*.sqlite`, `*.db`, `*.log`
- `__pycache__/`, `.streamlit/secrets.toml`
- `data/*.csv`, `*.cache`, `.cache/`
- `geocode_cache.json`

#### [NEW] [.env.example](file:///c:/Users/caio_/Documents/GitHub/MKT_GEAENG/.env.example)
Template com:
```env
# WordPress Headless (Harpy P&D)
WP_API_BASE=https://harpypd.com.br/wp-json
WP_AUTH_KEY=API_HARPY_2026

# CAPTCHA (visual Python — sem Google reCAPTCHA)
CAPTCHA_ENABLED=true
CAPTCHA_LENGTH=5

# BrasilAPI
BRASILAPI_RATE_LIMIT=3
BRASILAPI_USER_AGENT=MKT-GEAENG-Dashboard/1.0

# App
APP_TITLE=GEA ENG — Prospecção B2B
```

#### [NEW] [config.py](file:///c:/Users/caio_/Documents/GitHub/MKT_GEAENG/config.py)
- Dicionário completo de CNAE alimentícios (10.11-2 a 10.99-6) com labels
- URLs do SIGSIF CSV e BrasilAPI
- Configurações do mapa Folium (tile Esri, zoom padrão)
- Constantes de rate limiting

---

### Autenticação (`auth.py`) — WordPress Headless

#### [NEW] [auth.py](file:///c:/Users/caio_/Documents/GitHub/MKT_GEAENG/auth.py)

**Fluxo integrado com Simple JWT Login do WordPress:**

```
Usuário → CAPTCHA visual (Python) → Credenciais (email + senha)
  ↓
POST https://harpypd.com.br/wp-json/simple-jwt-login/v1/auth
  Body: { email, password }
  Param: AUTH_KEY (do .env)
  ↓
Resposta: { success: true, data: { jwt: "eyJ..." } }
  ↓
Decode JWT → Extrair user_nicename, user_email
  ↓
st.session_state["authenticated"] = True
st.session_state["jwt_token"] = jwt
st.session_state["user_email"] = email
```

**Funções:**
- `render_login_page()` — Tela isolada com CAPTCHA + campos
- `generate_captcha_image()` — Gera imagem CAPTCHA distorcida via lib `captcha`
- `verify_captcha(user_input)` — Valida resposta contra `st.session_state`
- `authenticate_wp(email, password)` — POST para Simple JWT Login endpoint
- `decode_jwt_payload(token)` — Decodifica payload do JWT (sem verificar assinatura, pois é do WP)
- `check_auth()` — Guard que verifica `st.session_state["authenticated"]`
- `logout()` — Limpa session_state

---

### Processamento de Dados (`data_loader.py`)

#### [NEW] [data_loader.py](file:///c:/Users/caio_/Documents/GitHub/MKT_GEAENG/data_loader.py)

**1. `load_sigsif_data()`** — `@st.cache_data(ttl=86400)`
- Download CSV do SIGSIF via MAPA (`dados.agricultura.gov.br`)
- Parse com pandas (UTF-8, separador `;`)
- Cache local em `data/sigsif_cache.csv`
- Fallback para cache se download falhar

**2. `fetch_cnpj_details(cnpj)`** — `@st.cache_data(ttl=604800)` (7 dias)
- GET `https://brasilapi.com.br/api/cnpj/v1/{cnpj}`
- Rate limit: **3 req/s** com `time.sleep(0.35)`
- Backoff exponencial: 1s → 2s → 4s (3 tentativas)
- User-Agent customizado
- Tratamento 429: pausa 60s + retry
- Retorna: razão_social, cnae_fiscal, endereço, telefone_1

**3. `geocode_city(municipio, uf)`** — `@st.cache_data(ttl=604800)`
- Nominatim via Geopy (1 req/s conforme policy)
- Fallback: cache JSON de centroides IBGE
- Retorna (lat, lon)

**4. `filter_by_cnae(df, cnae_codes)`**
**5. `filter_by_radius(df, lat, lon, radius_km)`** — Haversine
**6. `enrich_with_coordinates(df)`** — Batch geocoding com progress bar

---

### Aplicação Principal (`app.py`)

#### [NEW] [app.py](file:///c:/Users/caio_/Documents/GitHub/MKT_GEAENG/app.py)

**Layout (quando autenticado):**

```
┌─────────┬──────────────────────────────────┐
│SIDEBAR  │  ÁREA PRINCIPAL                  │
│         │                                  │
│🏭 CNAE ▼│  ┌──── KPIs ────────────────┐   │
│📊 Status│  │ Total │ Ativos │ UFs     │   │
│📏 Raio  │  └──────────────────────────┘   │
│🏙️ Munic.│                                  │
│📍 UF    │  ┌──── MAPA FOLIUM ─────────┐   │
│         │  │  🛰️ Satélite Esri        │   │
│[Buscar] │  │  📍 MarkerCluster         │   │
│         │  │  Popup: Razão Social      │   │
│👤 email │  │         CNAE, Endereço    │   │
│[Logout] │  │         📱 WhatsApp Link  │   │
│         │  └──────────────────────────┘   │
│         │                                  │
│         │  ┌──── TABELA ──────────────┐   │
│         │  │  st.dataframe + Download  │   │
│         │  └──────────────────────────┘   │
└─────────┴──────────────────────────────────┘
```

**Mapa Folium:**
- Tile: Esri World Imagery (satélite)
- `MarkerCluster` para agrupamento
- Popup HTML com: Razão Social, CNAE, Endereço, link WhatsApp (`https://wa.me/55{telefone}`)
- Renderização via `streamlit_folium.st_folium()`

---

### Dependências

#### [NEW] [requirements.txt](file:///c:/Users/caio_/Documents/GitHub/MKT_GEAENG/requirements.txt)

```
streamlit>=1.32.0
streamlit-folium>=0.18.0
folium>=0.15.0
pandas>=2.0.0
requests>=2.31.0
python-dotenv>=1.0.0
PyJWT>=2.8.0
geopy>=2.4.0
captcha>=0.5.0
numpy>=1.24.0
Pillow>=10.0.0
```

> **Removido `bcrypt`** — não precisa mais, pois a validação de senha é feita pelo WordPress (Simple JWT Login).

---

## Verification Plan

### Automated Tests
```bash
pip install -r requirements.txt
streamlit run app.py
```

### Manual Verification
1. Tela de login: CAPTCHA visual renderiza + campos email/senha
2. Login autentica via `harpypd.com.br/wp-json/simple-jwt-login/v1/auth`
3. Token JWT armazenado em session_state
4. CSV SIGSIF carrega e exibe dados
5. Filtros CNAE/UF/Município funcionam
6. Mapa com tiles Esri satélite renderiza
7. MarkerCluster agrupa marcadores
8. Popups mostram dados + link WhatsApp (quando disponível)
9. `.gitignore` bloqueia `.env` e caches
