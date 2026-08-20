"""
app.py — Dashboard B2B de Prospecção (Indústrias Alimentícias SIF/MAPA)

Entrada principal do Streamlit. Orquestra:
- Autenticação via WordPress Headless (Harpy P&D / Simple JWT Login)
- Carregamento e filtros do SIGSIF + BrasilAPI
- Mapa Folium com camada satélite Esri + MarkerCluster
- Tabela de dados interativa com download CSV
"""
import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

from config import (
    APP_TITLE,
    CNAE_ALIMENTICIO,
    UFS_BRASIL,
    ESRI_SATELLITE_TILES,
    ESRI_ATTRIBUTION,
    MAP_DEFAULT_LOCATION,
    MAP_DEFAULT_ZOOM,
)
from auth import check_auth, render_login_page, logout, decode_jwt_payload
from data_loader import (
    load_sigsif_data,
    enrich_with_coordinates,
    enrich_with_brasilapi,
    filter_by_cnae,
    filter_by_status,
    filter_by_uf,
    filter_by_municipio,
    filter_by_radius,
    geocode_city,
)


# ============================================
# Configuração da Página
# ============================================
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================
# CSS Global
# ============================================
st.markdown("""
<style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap');

    /* Global font */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Outfit', sans-serif;
    }

    /* KPI Cards */
    .kpi-card {
        background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
        border: 1px solid rgba(0, 201, 255, 0.15);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        border-color: rgba(0, 201, 255, 0.4);
    }
    .kpi-value {
        font-family: 'Outfit', sans-serif;
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #00C9FF, #92FE9D);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .kpi-label {
        color: #8892a4;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 4px;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a0e14 0%, #111827 100%);
    }
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #00C9FF;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }

    /* User badge */
    .user-badge {
        display: flex;
        align-items: center;
        gap: 8px;
        background: rgba(0, 201, 255, 0.08);
        border: 1px solid rgba(0, 201, 255, 0.2);
        border-radius: 8px;
        padding: 8px 12px;
        margin-bottom: 1rem;
        font-size: 0.8rem;
        color: #b0bec5;
    }
    .user-badge strong {
        color: #00C9FF;
    }

    /* Section headers */
    .section-header {
        font-family: 'Outfit', sans-serif;
        font-size: 1.1rem;
        font-weight: 600;
        color: #e0e0e0;
        margin: 1.5rem 0 0.8rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #1E2330;
    }

    /* Map container */
    .map-container {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(0, 201, 255, 0.15);
    }

    /* Footer */
    .app-footer {
        text-align: center;
        color: #555;
        font-size: 0.7rem;
        margin-top: 2rem;
        padding-top: 1rem;
        border-top: 1px solid #1E2330;
    }
</style>
""", unsafe_allow_html=True)


# ============================================
# Guarda de Autenticação
# ============================================
if not check_auth():
    render_login_page()
    st.stop()


# ============================================
# SIDEBAR — Filtros
# ============================================
with st.sidebar:
    # User info
    user_name = st.session_state.get("user_name", "Usuário")
    user_email = st.session_state.get("user_email", "")
    st.markdown(f"""
    <div class="user-badge">
        👤 <strong>{user_name}</strong>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🔍 Filtros de Prospecção")

    # CNAE
    cnae_options = [f"{code} — {desc}" for code, desc in CNAE_ALIMENTICIO.items()]
    selected_cnae_labels = st.multiselect(
        "🏭 CNAE (Setor Alimentício)",
        options=cnae_options,
        default=[],
        placeholder="Selecione os CNAEs...",
        help="Filtre por atividade econômica principal",
    )
    # Extrair códigos do label selecionado
    selected_cnae_codes = [label.split(" — ")[0] for label in selected_cnae_labels]

    st.markdown("---")

    # Status
    status_filter = st.selectbox(
        "📊 Status",
        options=["Ativo", "Todos"],
        index=0,
        help="Filtrar por situação cadastral",
    )

    # UF
    uf_filter = st.selectbox(
        "📍 UF (Estado)",
        options=["Todos"] + UFS_BRASIL,
        index=0,
        help="Filtrar por Unidade Federativa",
    )

    # Município
    municipio_filter = st.text_input(
        "🏙️ Município",
        value="",
        placeholder="Ex: São Paulo",
        help="Busca parcial por nome do município",
    )

    st.markdown("---")

    # Raio de busca
    st.markdown("### 📏 Busca por Raio")
    enable_radius = st.checkbox("Ativar filtro por raio", value=False)

    radius_km = 100
    radius_city = ""
    radius_uf = ""

    if enable_radius:
        radius_city = st.text_input(
            "Cidade de referência",
            value="",
            placeholder="Ex: Campinas",
        )
        radius_uf = st.selectbox(
            "UF de referência",
            options=UFS_BRASIL,
            index=25,  # SP
            key="radius_uf",
        )
        radius_km = st.slider(
            "Raio (km)",
            min_value=10,
            max_value=500,
            value=100,
            step=10,
        )

    st.markdown("---")

    # Botão de busca
    search_clicked = st.button(
        "🔎 Buscar Estabelecimentos",
        use_container_width=True,
        type="primary",
    )

    st.markdown("---")

    # Logout
    if st.button("🚪 Sair", use_container_width=True):
        logout()
        st.rerun()

    st.markdown("""
    <div class="app-footer">
        <p>GEA ENG — Prospecção B2B</p>
        <p>Dados: SIGSIF/MAPA + BrasilAPI</p>
    </div>
    """, unsafe_allow_html=True)


# ============================================
# ÁREA PRINCIPAL
# ============================================
st.markdown(f"""
<h1 style="font-family: 'Outfit', sans-serif; font-size: 1.6rem; margin-bottom: 0.2rem;">
    🏭 {APP_TITLE}
</h1>
<p style="color: #8892a4; font-size: 0.85rem; margin-bottom: 1.5rem;">
    Prospecção de indústrias do setor alimentício com registro SIF/MAPA
</p>
""", unsafe_allow_html=True)


# ============================================
# Carregamento de Dados
# ============================================
with st.spinner("📥 Carregando base SIGSIF (Dados Abertos do MAPA)..."):
    df_raw = load_sigsif_data()

if df_raw.empty:
    st.error(
        "❌ Não foi possível carregar os dados do SIGSIF. "
        "Verifique sua conexão ou tente novamente mais tarde."
    )
    st.stop()

# Copiar para não modificar cache
df = df_raw.copy()


# ============================================
# Aplicar Filtros
# ============================================
if status_filter != "Todos":
    df = filter_by_status(df, status_filter)

if uf_filter != "Todos":
    df = filter_by_uf(df, uf_filter)

if municipio_filter:
    df = filter_by_municipio(df, municipio_filter)

if selected_cnae_codes and "cnae_fiscal" in df.columns:
    df = filter_by_cnae(df, selected_cnae_codes)

# Geocodificação
if not df.empty and ("latitude" not in df.columns or "longitude" not in df.columns):
    if len(df) <= 200:
        with st.spinner("🌍 Geocodificando municípios..."):
            df = enrich_with_coordinates(df)
    else:
        st.info(
            f"ℹ️ {len(df)} resultados encontrados. "
            "Refine os filtros para geocodificar (máx. 200 registros no mapa)."
        )

# Filtro por raio
if enable_radius and radius_city and "latitude" in df.columns:
    center_coords = geocode_city(radius_city, radius_uf)
    if center_coords:
        df = filter_by_radius(df, center_coords[0], center_coords[1], radius_km)
        if "_distancia_km" in df.columns:
            df["distancia_km"] = df["_distancia_km"].round(1)
            df = df.drop(columns=["_distancia_km"], errors="ignore")
    else:
        st.warning(f"⚠️ Não foi possível geocodificar '{radius_city}/{radius_uf}'.")


# ============================================
# KPIs
# ============================================
total = len(df)
total_ufs = df["uf"].nunique() if "uf" in df.columns else 0
total_com_telefone = (
    df["telefone"].notna().sum()
    if "telefone" in df.columns
    else (df["telefone_1"].notna().sum() if "telefone_1" in df.columns else 0)
)
total_municipios = df["municipio"].nunique() if "municipio" in df.columns else 0

kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.markdown(f"""
    <div class="kpi-card">
        <p class="kpi-value">{total:,}</p>
        <p class="kpi-label">Estabelecimentos</p>
    </div>
    """, unsafe_allow_html=True)

with kpi2:
    st.markdown(f"""
    <div class="kpi-card">
        <p class="kpi-value">{total_ufs}</p>
        <p class="kpi-label">Estados (UFs)</p>
    </div>
    """, unsafe_allow_html=True)

with kpi3:
    st.markdown(f"""
    <div class="kpi-card">
        <p class="kpi-value">{total_municipios}</p>
        <p class="kpi-label">Municípios</p>
    </div>
    """, unsafe_allow_html=True)

with kpi4:
    st.markdown(f"""
    <div class="kpi-card">
        <p class="kpi-value">{total_com_telefone}</p>
        <p class="kpi-label">Com Telefone</p>
    </div>
    """, unsafe_allow_html=True)


# ============================================
# Mapa Folium
# ============================================
st.markdown('<p class="section-header">🗺️ Mapa de Prospecção — Satélite Esri</p>', unsafe_allow_html=True)

if "latitude" in df.columns and "longitude" in df.columns:
    df_map = df.dropna(subset=["latitude", "longitude"]).copy()

    if not df_map.empty:
        # Centro do mapa: média das coordenadas
        center_lat = df_map["latitude"].astype(float).mean()
        center_lon = df_map["longitude"].astype(float).mean()

        # Criar mapa com satélite Esri
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=6,
            tiles=ESRI_SATELLITE_TILES,
            attr=ESRI_ATTRIBUTION,
        )

        # MarkerCluster
        marker_cluster = MarkerCluster(name="Estabelecimentos SIF").add_to(m)

        # Adicionar marcadores
        for _, row in df_map.iterrows():
            lat = float(row["latitude"])
            lon = float(row["longitude"])

            # Dados para popup
            razao = row.get("razao_social", "N/D")
            municipio = row.get("municipio", "")
            uf = row.get("uf", "")
            endereco = row.get("endereco", "")
            sif = row.get("sif", "")
            classificacao = row.get("classificacao", "")

            # CNAE
            cnae = row.get("cnae_fiscal", "")
            cnae_desc = row.get("cnae_descricao", row.get("classificacao", ""))

            # Telefone e WhatsApp
            telefone = row.get("telefone_1", row.get("telefone", ""))
            whatsapp_html = ""
            if telefone and str(telefone).strip() and str(telefone).strip() != "nan":
                tel_clean = "".join(filter(str.isdigit, str(telefone)))
                if len(tel_clean) >= 10:
                    whatsapp_url = f"https://wa.me/55{tel_clean}"
                    whatsapp_html = f"""
                    <a href="{whatsapp_url}" target="_blank"
                       style="display:inline-block; margin-top:8px; padding:6px 14px;
                              background:#25D366; color:white; border-radius:6px;
                              text-decoration:none; font-size:12px; font-weight:600;">
                        📱 WhatsApp: ({tel_clean[:2]}) {tel_clean[2:]}
                    </a>
                    """

            # Distância (se filtro por raio ativo)
            dist_html = ""
            if "distancia_km" in row.index and pd.notna(row.get("distancia_km")):
                dist_html = f"""
                <p style="color:#00C9FF; font-size:11px; margin:4px 0 0 0;">
                    📏 {row['distancia_km']:.1f} km do ponto de referência
                </p>
                """

            # Popup HTML estilizado
            popup_html = f"""
            <div style="font-family: 'Inter', Arial, sans-serif; width: 280px; padding: 8px;">
                <h4 style="margin:0 0 6px 0; color:#0d1117; font-size:14px; font-weight:700;
                           border-bottom:2px solid #00C9FF; padding-bottom:4px;">
                    {razao}
                </h4>
                <table style="font-size:11px; color:#333; width:100%; border-collapse:collapse;">
                    <tr>
                        <td style="padding:2px 8px 2px 0; font-weight:600; color:#555;">SIF:</td>
                        <td>{sif}</td>
                    </tr>
                    <tr>
                        <td style="padding:2px 8px 2px 0; font-weight:600; color:#555;">CNAE:</td>
                        <td>{cnae} {cnae_desc}</td>
                    </tr>
                    <tr>
                        <td style="padding:2px 8px 2px 0; font-weight:600; color:#555;">Classificação:</td>
                        <td>{classificacao}</td>
                    </tr>
                    <tr>
                        <td style="padding:2px 8px 2px 0; font-weight:600; color:#555;">Endereço:</td>
                        <td>{endereco}</td>
                    </tr>
                    <tr>
                        <td style="padding:2px 8px 2px 0; font-weight:600; color:#555;">Cidade:</td>
                        <td>{municipio}/{uf}</td>
                    </tr>
                </table>
                {dist_html}
                {whatsapp_html}
            </div>
            """

            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=320),
                tooltip=f"{razao} ({municipio}/{uf})",
                icon=folium.Icon(color="green", icon="industry", prefix="fa"),
            ).add_to(marker_cluster)

        # Renderizar mapa
        st.markdown('<div class="map-container">', unsafe_allow_html=True)
        st_folium(m, width=None, height=520, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    else:
        st.info("📍 Nenhum estabelecimento com coordenadas para exibir no mapa.")
else:
    if not df.empty:
        st.info(
            "📍 Refine os filtros (máx. 200 resultados) para visualizar no mapa."
        )


# ============================================
# Tabela de Dados
# ============================================
st.markdown('<p class="section-header">📋 Dados dos Estabelecimentos</p>', unsafe_allow_html=True)

if not df.empty:
    # Selecionar colunas para exibição
    display_cols = []
    for col in [
        "sif", "razao_social", "cnpj", "classificacao", "cnae_fiscal",
        "municipio", "uf", "endereco", "cep", "telefone", "telefone_1",
        "situacao", "distancia_km",
    ]:
        if col in df.columns:
            display_cols.append(col)

    if display_cols:
        st.dataframe(
            df[display_cols].reset_index(drop=True),
            use_container_width=True,
            height=400,
        )
    else:
        st.dataframe(df.head(500), use_container_width=True, height=400)

    # Download CSV
    csv_data = df.to_csv(index=False, sep=";", encoding="utf-8")
    st.download_button(
        label="📥 Download CSV dos resultados",
        data=csv_data,
        file_name=f"prospeccao_b2b_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )
else:
    st.info("🔍 Nenhum resultado encontrado. Ajuste os filtros no painel lateral.")


# ============================================
# Rodapé
# ============================================
st.markdown("""
<div class="app-footer">
    <p>GEA ENG — Prospecção B2B | Dados: SIGSIF/MAPA (Dados Abertos) + BrasilAPI</p>
    <p>🛡️ Sessão autenticada via WordPress Headless — Harpy P&D</p>
</div>
""", unsafe_allow_html=True)
