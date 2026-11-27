"""Carga de datos desde la API con caché de Streamlit (10 minutos).

Los datos cambian una vez al mes, así que la caché evita llamadas repetidas a la API y a la base
de datos mientras se navega. La caché es del servidor: la comparten todas las sesiones.
"""

import pandas as pd
import streamlit as st

import calculos as calc
from cliente_api import ApiNoDisponible, pedir, url_api

CACHE = 600  # segundos
MENSAJE_CARGA = "Cargando los datos de los KID. Si la base de datos estaba en pausa, tarda unos segundos más."

COLUMNAS_NUMERICAS = [
    "sri",
    "periodo_mantenimiento_anios",
    "gastos_corrientes_pct",
    "costes_entrada_pct",
    "costes_salida_pct",
]


def preparar_fondos(registros: list[dict]) -> pd.DataFrame:
    """Lista de /fondos a DataFrame con columnas derivadas para la aplicación."""
    fondos = pd.DataFrame(registros)
    if fondos.empty:
        return fondos
    for columna in COLUMNAS_NUMERICAS:
        fondos[columna] = pd.to_numeric(fondos[columna], errors="coerce")
    fondos["sri"] = fondos["sri"].astype(int)
    fondos["fecha_documento"] = pd.to_datetime(fondos["fecha_documento"], errors="coerce")
    fondos["ultima_descarga"] = pd.to_datetime(fondos["ultima_descarga"], errors="coerce")
    fondos["nombre_corto"] = [
        calc.nombre_corto(p, c) for p, c in zip(fondos["nombre_producto"], fondos["nombre_clase"], strict=True)
    ]
    fondos["gestora_web"] = fondos["fuente"].map(calc.NOMBRES_FUENTE).fillna(fondos["fuente"].str.capitalize())
    verificacion = fondos["verificacion_evidencias"].apply(lambda v: v or {})
    fondos["citas_total"] = verificacion.apply(len)
    fondos["citas_encontradas"] = verificacion.apply(lambda v: sum(bool(x) for x in v.values()))
    return fondos.sort_values(["sri", "nombre_corto"], ignore_index=True)


@st.cache_data(ttl=CACHE, show_spinner=MENSAJE_CARGA)
def fondos() -> pd.DataFrame:
    return preparar_fondos(pedir("/fondos") or [])


@st.cache_data(ttl=CACHE, show_spinner=MENSAJE_CARGA)
def resumen() -> dict:
    return pedir("/resumen")


@st.cache_data(ttl=CACHE, show_spinner="Cargando la ficha del fondo")
def detalle(isin: str) -> dict | None:
    return pedir(f"/fondos/{isin}")


def enlace_kid(isin: str) -> str:
    """Dirección de la API que abre el PDF original del KID (enlace temporal de S3)."""
    return url_api(f"/fondos/{isin}/kid")


def cargar_o_avisar(funcion, *args):
    """Ejecuta una carga y, si la API no responde, muestra el problema y detiene la página."""
    try:
        return funcion(*args)
    except ApiNoDisponible as e:
        st.error(
            f"No se han podido cargar los datos: {e}. Vuelve a cargar la página en unos segundos.",
            icon=":material/cloud_off:",
        )
        st.stop()
