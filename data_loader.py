"""
data_loader.py — Carregamento de dados SIGSIF, consulta BrasilAPI e geocodificação.

Funções cacheadas para consumir:
- CSV do SIGSIF (Dados Abertos do MAPA)
- BrasilAPI (consulta de CNPJ/CNAE)
- Nominatim (geocodificação de municípios)
"""
import os
import json
import time
import math
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import requests
import streamlit as st
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

from config import (
    SIGSIF_CSV_URL,
    SIGSIF_CACHE_PATH,
    SIGSIF_CACHE_TTL_HOURS,
    BRASILAPI_BASE_URL,
    BRASILAPI_RATE_LIMIT,
    BRASILAPI_USER_AGENT,
    BRASILAPI_CACHE_TTL_DAYS,
    BRASILAPI_RETRY_ATTEMPTS,
    BRASILAPI_RETRY_BACKOFF,
    BRASILAPI_429_PAUSE,
    GEOCODE_CACHE_PATH,
    NOMINATIM_USER_AGENT,
    NOMINATIM_RATE_LIMIT_SECONDS,
    CNAE_ALIMENTICIO,
)


# ============================================
# 1. SIGSIF — CSV de Dados Abertos do MAPA
# ============================================

def _is_cache_valid(cache_path: str, ttl_hours: int) -> bool:
    """Verifica se o cache local existe e está dentro do TTL."""
    if not os.path.exists(cache_path):
        return False
    mod_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
    return (datetime.now() - mod_time) < timedelta(hours=ttl_hours)


@st.cache_data(ttl=86400, show_spinner=False)
def load_sigsif_data() -> pd.DataFrame:
    """
    Carrega o CSV do SIGSIF (estabelecimentos registrados no SIF).

    - Tenta download da URL oficial do MAPA
    - Salva cache local em data/sigsif_cache.csv
    - Fallback para cache local se download falhar
    - TTL de cache: 24 horas
    """
    # Tenta usar cache local se válido
    if _is_cache_valid(SIGSIF_CACHE_PATH, SIGSIF_CACHE_TTL_HOURS):
        try:
            df = pd.read_csv(SIGSIF_CACHE_PATH, sep=";", encoding="utf-8", dtype=str)
            if not df.empty:
                return _normalize_sigsif_columns(df)
        except Exception:
            pass

    # Download do CSV
    try:
        response = requests.get(
            SIGSIF_CSV_URL,
            timeout=60,
            headers={"User-Agent": BRASILAPI_USER_AGENT},
        )
        response.raise_for_status()

        # Detectar encoding e separador
        content = response.content
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                text = content.decode("latin-1")

        # Detectar separador
        first_line = text.split("\n")[0]
        sep = ";" if ";" in first_line else ","

        # Salvar cache local
        os.makedirs(os.path.dirname(SIGSIF_CACHE_PATH), exist_ok=True)
        with open(SIGSIF_CACHE_PATH, "w", encoding="utf-8") as f:
            f.write(text)

        from io import StringIO
        df = pd.read_csv(StringIO(text), sep=sep, dtype=str)

        if not df.empty:
            return _normalize_sigsif_columns(df)

    except Exception as e:
        st.warning(f"⚠️ Erro ao baixar CSV do SIGSIF: {e}. Usando cache local.")

    # Fallback: cache local
    if os.path.exists(SIGSIF_CACHE_PATH):
        try:
            df = pd.read_csv(SIGSIF_CACHE_PATH, sep=";", encoding="utf-8", dtype=str)
            if df.empty:
                df = pd.read_csv(SIGSIF_CACHE_PATH, sep=",", encoding="utf-8", dtype=str)
            return _normalize_sigsif_columns(df)
        except Exception:
            pass

    return pd.DataFrame()


def _normalize_sigsif_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza nomes de colunas do SIGSIF para um padrão consistente.
    O CSV pode ter variações nos nomes de coluna entre versões.
    """
    # Remover colunas duplicadas (ex: duas colunas 'telefone')
    df = df.loc[:, ~df.columns.duplicated()]

    # Limpar espaços e converter para minúsculo
    df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]

    # Mapeamento de nomes comuns → padrão
    column_map = {
        "razao_social": "razao_social",
        "razão_social": "razao_social",
        "razão social": "razao_social",
        "nome_empresarial": "razao_social",
        "municipio": "municipio",
        "município": "municipio",
        "uf": "uf",
        "estado": "uf",
        "cnpj": "cnpj",
        "sif": "sif",
        "numero_sif": "sif",
        "nº_sif": "sif",
        "classificacao": "classificacao",
        "classificação": "classificacao",
        "categoria": "classificacao",
        "situacao": "situacao",
        "situação": "situacao",
        "status": "situacao",
        "endereco": "endereco",
        "endereço": "endereco",
        "logradouro": "endereco",
        "telefone": "telefone",
        "fone": "telefone",
        "cep": "cep",
    }

    renamed = {}
    for old_col in df.columns:
        clean = old_col.strip().lower().replace(" ", "_")
        for pattern, standard in column_map.items():
            if pattern in clean:
                renamed[old_col] = standard
                break

    df = df.rename(columns=renamed)

    # Limpar valores
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()

    return df


# ============================================
# 2. BrasilAPI — Consulta CNPJ
# ============================================

@st.cache_data(ttl=604800, show_spinner=False)  # 7 dias
def fetch_cnpj_details(cnpj: str) -> dict | None:
    """
    Consulta dados de um CNPJ via BrasilAPI.

    GET https://brasilapi.com.br/api/cnpj/v1/{cnpj}

    Rate limit: ~3 req/s (conservador)
    Retry: 3 tentativas com backoff exponencial (1s → 2s → 4s)
    429: Pausa de 60 segundos + retry

    Retorna dict com dados ou None se não encontrado.
    """
    # Limpar CNPJ (só números)
    cnpj_clean = "".join(filter(str.isdigit, str(cnpj)))

    if len(cnpj_clean) != 14:
        return None

    url = f"{BRASILAPI_BASE_URL}/{cnpj_clean}"
    headers = {
        "User-Agent": BRASILAPI_USER_AGENT,
        "Accept": "application/json",
    }

    for attempt in range(BRASILAPI_RETRY_ATTEMPTS):
        try:
            # Rate limiting
            time.sleep(1.0 / BRASILAPI_RATE_LIMIT)

            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code == 200:
                return response.json()

            elif response.status_code == 404:
                return None

            elif response.status_code == 429:
                # Rate limited — pausa longa
                time.sleep(BRASILAPI_429_PAUSE)
                continue

            else:
                # Outros erros — backoff
                if attempt < BRASILAPI_RETRY_ATTEMPTS - 1:
                    time.sleep(BRASILAPI_RETRY_BACKOFF[attempt])

        except requests.exceptions.RequestException:
            if attempt < BRASILAPI_RETRY_ATTEMPTS - 1:
                time.sleep(BRASILAPI_RETRY_BACKOFF[attempt])

    return None


def enrich_with_brasilapi(df: pd.DataFrame, cnpj_column: str = "cnpj") -> pd.DataFrame:
    """
    Enriquece o DataFrame com dados da BrasilAPI para cada CNPJ.
    Adiciona colunas: cnae_fiscal, cnae_descricao, telefone_1, telefone_2.
    """
    if cnpj_column not in df.columns:
        return df

    new_data = {
        "cnae_fiscal": [],
        "cnae_descricao": [],
        "telefone_1": [],
    }

    progress = st.progress(0, text="Enriquecendo dados via BrasilAPI...")
    total = len(df)

    for idx, row in df.iterrows():
        cnpj = row.get(cnpj_column, "")
        details = fetch_cnpj_details(cnpj) if cnpj else None

        if details:
            cnae = str(details.get("cnae_fiscal", ""))
            new_data["cnae_fiscal"].append(cnae)
            new_data["cnae_descricao"].append(
                details.get("cnae_fiscal_descricao", "")
            )
            new_data["telefone_1"].append(
                details.get("ddd_telefone_1", "")
            )
        else:
            new_data["cnae_fiscal"].append("")
            new_data["cnae_descricao"].append("")
            new_data["telefone_1"].append("")

        progress.progress((idx + 1) / total, text=f"BrasilAPI: {idx + 1}/{total}")

    progress.empty()

    for col, values in new_data.items():
        df[col] = values

    return df


# ============================================
# 3. Geocodificação — Nominatim
# ============================================

def _load_geocode_cache() -> dict:
    """Carrega cache de geocodificação do disco."""
    if os.path.exists(GEOCODE_CACHE_PATH):
        try:
            with open(GEOCODE_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_geocode_cache(cache: dict) -> None:
    """Salva cache de geocodificação no disco."""
    os.makedirs(os.path.dirname(GEOCODE_CACHE_PATH), exist_ok=True)
    try:
        with open(GEOCODE_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


@st.cache_data(ttl=604800, show_spinner=False)  # 7 dias
def geocode_city(municipio: str, uf: str) -> tuple | None:
    """
    Geocodifica um município brasileiro via Nominatim.

    Rate limit: 1 req/s (Nominatim usage policy)
    Cache: 7 dias em memória + persistido em JSON local

    Retorna (latitude, longitude) ou None.
    """
    if not municipio or not uf:
        return None

    # Chave de cache
    cache_key = f"{municipio.strip().upper()}_{uf.strip().upper()}"

    # Verificar cache em disco
    disk_cache = _load_geocode_cache()
    if cache_key in disk_cache:
        coords = disk_cache[cache_key]
        if coords:
            return tuple(coords)
        return None

    # Consultar Nominatim
    try:
        geolocator = Nominatim(user_agent=NOMINATIM_USER_AGENT, timeout=10)
        time.sleep(NOMINATIM_RATE_LIMIT_SECONDS)

        query = f"{municipio}, {uf}, Brasil"
        location = geolocator.geocode(query, country_codes="br")

        if location:
            result = (location.latitude, location.longitude)
            disk_cache[cache_key] = list(result)
            _save_geocode_cache(disk_cache)
            return result
        else:
            disk_cache[cache_key] = None
            _save_geocode_cache(disk_cache)
            return None

    except (GeocoderTimedOut, GeocoderUnavailable):
        return None
    except Exception:
        return None


def enrich_with_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adiciona colunas latitude/longitude ao DataFrame via geocodificação em batch.
    Utiliza as colunas 'municipio' e 'uf' existentes.
    """
    if "municipio" not in df.columns or "uf" not in df.columns:
        st.warning("⚠️ Colunas 'municipio' e 'uf' não encontradas para geocodificação.")
        return df

    latitudes = []
    longitudes = []

    # Criar set de municípios únicos para evitar geocodificação duplicada
    unique_cities = df[["municipio", "uf"]].drop_duplicates()
    city_coords = {}

    progress = st.progress(0, text="Geocodificando municípios...")
    total = len(unique_cities)

    for idx, (_, row) in enumerate(unique_cities.iterrows()):
        municipio = str(row.get("municipio", "")).strip()
        uf = str(row.get("uf", "")).strip()
        key = f"{municipio}_{uf}"

        if key not in city_coords:
            coords = geocode_city(municipio, uf)
            city_coords[key] = coords

        progress.progress(
            (idx + 1) / total,
            text=f"Geocodificando: {municipio}/{uf} ({idx + 1}/{total})",
        )

    progress.empty()

    # Aplicar coordenadas ao DataFrame
    for _, row in df.iterrows():
        municipio = str(row.get("municipio", "")).strip()
        uf = str(row.get("uf", "")).strip()
        key = f"{municipio}_{uf}"
        coords = city_coords.get(key)

        if coords:
            latitudes.append(coords[0])
            longitudes.append(coords[1])
        else:
            latitudes.append(None)
            longitudes.append(None)

    df["latitude"] = latitudes
    df["longitude"] = longitudes

    return df


# ============================================
# 4. Filtros
# ============================================

def filter_by_cnae(df: pd.DataFrame, cnae_codes: list) -> pd.DataFrame:
    """Filtra DataFrame por códigos CNAE selecionados."""
    if not cnae_codes or "cnae_fiscal" not in df.columns:
        return df

    # Normalizar códigos CNAE para comparação
    cnae_clean = []
    for code in cnae_codes:
        # Ex: "10.11-2" → "1011" (apenas dígitos do grupo principal)
        digits = "".join(filter(str.isdigit, code))
        cnae_clean.append(digits)

    # Filtrar por prefixo CNAE
    mask = df["cnae_fiscal"].apply(
        lambda x: any(
            str(x).startswith(prefix[:4]) for prefix in cnae_clean
        ) if pd.notna(x) and str(x).strip() else False
    )
    return df[mask]


def filter_by_status(df: pd.DataFrame, status: str = "Ativo") -> pd.DataFrame:
    """Filtra por status/situação do estabelecimento."""
    if "situacao" not in df.columns:
        return df
    if status == "Todos":
        return df
    return df[df["situacao"].str.contains(status, case=False, na=False)]


def filter_by_uf(df: pd.DataFrame, uf: str) -> pd.DataFrame:
    """Filtra por UF."""
    if not uf or uf == "Todos" or "uf" not in df.columns:
        return df
    return df[df["uf"].str.upper() == uf.upper()]


def filter_by_municipio(df: pd.DataFrame, municipio: str) -> pd.DataFrame:
    """Filtra por município (busca parcial, case-insensitive)."""
    if not municipio or "municipio" not in df.columns:
        return df
    return df[df["municipio"].str.contains(municipio, case=False, na=False)]


def filter_by_radius(
    df: pd.DataFrame,
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> pd.DataFrame:
    """
    Filtra estabelecimentos dentro de um raio (km) usando fórmula de Haversine.
    Requer colunas 'latitude' e 'longitude' no DataFrame.
    """
    if "latitude" not in df.columns or "longitude" not in df.columns:
        return df

    df_valid = df.dropna(subset=["latitude", "longitude"]).copy()
    if df_valid.empty:
        return df_valid

    lat1 = math.radians(center_lat)
    lon1 = math.radians(center_lon)

    def haversine_distance(row):
        try:
            lat2 = math.radians(float(row["latitude"]))
            lon2 = math.radians(float(row["longitude"]))
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            )
            c = 2 * math.asin(math.sqrt(a))
            r = 6371  # Raio da Terra em km
            return c * r
        except (ValueError, TypeError):
            return float("inf")

    df_valid["_distancia_km"] = df_valid.apply(haversine_distance, axis=1)
    result = df_valid[df_valid["_distancia_km"] <= radius_km].copy()
    result = result.sort_values("_distancia_km")

    return result
