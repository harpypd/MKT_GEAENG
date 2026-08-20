"""
config.py — Constantes, mapeamento CNAE e configurações do Dashboard B2B.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
# WordPress Headless — Harpy P&D
# ============================================
WP_API_BASE = os.getenv("WP_API_BASE", "https://harpypd.com.br/wp-json")
WP_AUTH_KEY = os.getenv("WP_AUTH_KEY", "")
WP_AUTH_ENDPOINT = f"{WP_API_BASE}/simple-jwt-login/v1/auth"
WP_USERS_ENDPOINT = f"{WP_API_BASE}/simple-jwt-login/v1/users"

# ============================================
# CAPTCHA
# ============================================
CAPTCHA_ENABLED = os.getenv("CAPTCHA_ENABLED", "true").lower() == "true"
CAPTCHA_LENGTH = int(os.getenv("CAPTCHA_LENGTH", "5"))

# ============================================
# BrasilAPI
# ============================================
BRASILAPI_BASE_URL = "https://brasilapi.com.br/api/cnpj/v1"
BRASILAPI_RATE_LIMIT = int(os.getenv("BRASILAPI_RATE_LIMIT", "3"))
BRASILAPI_USER_AGENT = os.getenv(
    "BRASILAPI_USER_AGENT", "MKT-GEAENG-Dashboard/1.0"
)
BRASILAPI_CACHE_TTL_DAYS = 7
BRASILAPI_RETRY_ATTEMPTS = 3
BRASILAPI_RETRY_BACKOFF = [1, 2, 4]  # segundos
BRASILAPI_429_PAUSE = 60  # segundos de pausa ao receber 429

# ============================================
# SIGSIF — CSV de Dados Abertos do MAPA
# ============================================
SIGSIF_CSV_URL = (
    "https://dados.agricultura.gov.br/dataset/"
    "062166e3-b515-4274-8e7d-68aadd64b820/resource/"
    "97277e92-264a-4dc0-9aea-f87b8ea93798/download/"
    "sigsifestabelecimentosregistradosnosif.csv"
)
SIGSIF_CACHE_PATH = os.path.join("data", "sigsif_cache.csv")
SIGSIF_CACHE_TTL_HOURS = 24

# ============================================
# Geocodificação
# ============================================
GEOCODE_CACHE_PATH = os.path.join("data", "geocode_cache.json")
NOMINATIM_USER_AGENT = "MKT-GEAENG-Geocoder/1.0 (contato@harpypd.com.br)"
NOMINATIM_RATE_LIMIT_SECONDS = 1.1  # Nominatim policy: max 1 req/s

# ============================================
# Mapa Folium
# ============================================
ESRI_SATELLITE_TILES = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
ESRI_ATTRIBUTION = "Esri"
MAP_DEFAULT_LOCATION = [-15.7801, -47.9292]  # Brasília
MAP_DEFAULT_ZOOM = 4

# ============================================
# Título da Aplicação
# ============================================
APP_TITLE = os.getenv("APP_TITLE", "GEA ENG — Prospecção B2B")

# ============================================
# Mapeamento CNAE — Setor Alimentício (Divisão 10)
# ============================================
CNAE_ALIMENTICIO = {
    "10.11-2": "Frigoríficos — Abate de bovinos",
    "10.12-1": "Abate de suínos, aves e outros pequenos animais",
    "10.13-9": "Fabricação de produtos de carne",
    "10.20-1": "Preservação do pescado e fabricação de produtos do pescado",
    "10.31-7": "Fabricação de conservas de frutas",
    "10.32-5": "Fabricação de conservas de legumes e outros vegetais",
    "10.33-3": "Fabricação de sucos de frutas, hortaliças e legumes",
    "10.41-4": "Fabricação de óleos vegetais em bruto",
    "10.42-2": "Fabricação de óleos vegetais refinados",
    "10.43-1": "Fabricação de margarina e outras gorduras vegetais",
    "10.51-1": "Laticínios — Preparação do leite",
    "10.52-0": "Fabricação de laticínios",
    "10.53-8": "Fabricação de sorvetes e outros gelados comestíveis",
    "10.61-9": "Beneficiamento de arroz e fabricação de produtos do arroz",
    "10.62-7": "Moagem de trigo e fabricação de derivados",
    "10.63-5": "Fabricação de farinha de mandioca e derivados",
    "10.64-3": "Fabricação de farinha de milho e derivados",
    "10.65-1": "Fabricação de amidos e féculas de vegetais",
    "10.66-0": "Fabricação de alimentos para animais",
    "10.69-4": "Moagem e fabricação de produtos de origem vegetal (outros)",
    "10.71-6": "Fabricação de açúcar em bruto",
    "10.72-4": "Fabricação de açúcar refinado",
    "10.81-3": "Torrefação e moagem de café",
    "10.82-1": "Fabricação de produtos à base de café",
    "10.91-1": "Fabricação de produtos de panificação",
    "10.92-9": "Fabricação de biscoitos e bolachas",
    "10.93-7": "Fabricação de produtos derivados do cacau e chocolates",
    "10.94-5": "Fabricação de massas alimentícias",
    "10.95-3": "Fabricação de especiarias, molhos, temperos e condimentos",
    "10.96-1": "Fabricação de alimentos e pratos prontos",
    "10.99-6": "Fabricação de outros produtos alimentícios",
}

# Lista de UFs brasileiras para filtros
UFS_BRASIL = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
