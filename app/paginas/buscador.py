"""Buscador: fondos que encajan con el riesgo, el plazo y el coste que acepta el inversor."""

import math

import streamlit as st

import calculos as calc
import componentes as comp
import datos

fondos = datos.cargar_o_avisar(datos.fondos)

comp.pregunta(
    "¿Qué fondos encajan contigo?",
    "Indica cuánto riesgo aceptas, cuánto tiempo puedes dejar el dinero invertido y cuánto estás dispuesto "
    "a pagar cada año en gastos.",
)

# Límites de los controles a partir de los datos (redondeados hacia arriba)
plazos, gastos = fondos["periodo_mantenimiento_anios"].dropna(), fondos["gastos_corrientes_pct"].dropna()
plazo_max = max(1, math.ceil(plazos.max())) if len(plazos) else 10
gasto_max = math.ceil(gastos.max() * 10) / 10 if len(gastos) else 3.0
pasos_gasto = [round(x * 0.1, 1) for x in range(0, int(gasto_max * 10) + 1)]

c1, c2, c3 = st.columns(3, gap="large")
riesgo = c1.select_slider("Riesgo que aceptas", options=list(calc.NIVELES_RIESGO), value=(1, 7))
plazo = c2.select_slider(
    "Tiempo que puedes mantener la inversión",
    options=list(range(1, plazo_max + 1)),
    value=plazo_max,
    format_func=calc.anios,
)
gasto = c3.select_slider(
    "Gastos corrientes máximos al año", options=pasos_gasto, value=pasos_gasto[-1], format_func=calc.pct
)
c4, c5, c6 = st.columns([1.2, 1.4, 1], gap="large")
fuentes = sorted(fondos["fuente"].unique())
elegidas = c4.pills("Gestora", fuentes, selection_mode="multi", default=fuentes, format_func=comp.nombre_gestora)
texto = c5.text_input("Nombre o ISIN", placeholder="Por ejemplo, Internacional o ES0112611001")
orden = c6.selectbox("Ordenar por", ["Riesgo", "Gastos corrientes", "Plazo recomendado", "Nombre"])

# Filtros: el plazo y el gasto solo excluyen fondos cuando se restringen
filtro = fondos["sri"].between(*riesgo) & fondos["fuente"].isin(elegidas or fuentes)
if plazo < plazo_max:
    filtro &= fondos["periodo_mantenimiento_anios"] <= plazo
if gasto < pasos_gasto[-1]:
    filtro &= fondos["gastos_corrientes_pct"] <= gasto
if texto.strip():
    buscado = calc.sin_acentos(texto.strip())
    filtro &= (fondos["nombre_producto"].map(calc.sin_acentos).str.contains(buscado, regex=False)) | (
        fondos["isin"].str.lower().str.contains(buscado, regex=False)
    )
columnas_orden = {
    "Riesgo": ["sri", "gastos_corrientes_pct"],
    "Gastos corrientes": ["gastos_corrientes_pct", "sri"],
    "Plazo recomendado": ["periodo_mantenimiento_anios", "sri"],
    "Nombre": ["nombre_corto"],
}
encontrados = fondos[filtro].sort_values(columnas_orden[orden], na_position="last")

if encontrados.empty:
    st.html(
        '<p class="kid-respuesta">Ningún fondo cumple todos estos criterios. Amplía el riesgo, el plazo o el '
        "gasto máximo para ver más.</p>"
    )
else:
    st.html(f'<p class="kid-respuesta">{len(encontrados)} de {len(fondos)} fondos cumplen estos criterios.</p>')
    st.html(comp.tabla_fondos(encontrados))
    exportar = encontrados[
        [
            "isin",
            "nombre_producto",
            "nombre_clase",
            "gestora",
            "fecha_documento",
            "sri",
            "periodo_mantenimiento_anios",
            "gastos_corrientes_pct",
            "costes_entrada_pct",
            "costes_salida_pct",
        ]
    ]
    st.download_button(
        "Descargar estos fondos (CSV)",
        exportar.to_csv(index=False, sep=";", decimal=",", date_format="%d/%m/%Y").encode("utf-8-sig"),
        file_name="fondos_kid.csv",
        mime="text/csv",
        icon=":material/download:",
    )
