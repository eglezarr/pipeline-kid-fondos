"""Aplicación web de los KID de fondos (Streamlit). Punto de entrada: streamlit run kid_app.py

Lee los datos solo de la API (variable de entorno API_URL). Cada página responde a una de las
preguntas con las que el propio KID organiza su información.
"""

from pathlib import Path

import streamlit as st

import componentes as comp
import datos

ESTATICOS = Path(__file__).parent / "static"

st.set_page_config(page_title="Lector de KID", page_icon=str(ESTATICOS / "icono.png"), layout="wide")
comp.estilos()
st.logo(str(ESTATICOS / "logo.svg"), size="large")

paginas = [
    st.Page("paginas/panorama.py", title="Panorama", default=True),
    st.Page("paginas/buscador.py", title="Buscador", url_path="buscador"),
    st.Page("paginas/costes.py", title="Costes", url_path="costes"),
    st.Page("paginas/ficha.py", title="Ficha de un fondo", url_path="ficha"),
    st.Page("paginas/fiabilidad.py", title="Fiabilidad", url_path="fiabilidad"),
]
st.navigation(paginas, position="top").run()

try:
    comp.pie(datos.fondos())
except datos.ApiNoDisponible:
    comp.pie(None)
