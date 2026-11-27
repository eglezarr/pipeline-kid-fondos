"""Panorama: dónde está cada fondo en la escala de riesgo, y cómo se relacionan riesgo, coste y plazo."""

import streamlit as st

import calculos as calc
import componentes as comp
import datos

fondos = datos.cargar_o_avisar(datos.fondos)

comp.pregunta("¿Cuánto riesgo declara cada fondo?", calc.frase_escala(fondos))
st.html(comp.escalera(fondos))
comp.nota(
    "El indicador resumido de riesgo (SRI) del KID va de 1 a 7 y combina el riesgo de mercado con el "
    "riesgo de que el fondo no pueda pagar. Pulsa un fondo para abrir su ficha."
)

comp.seccion("¿Se paga más por asumir más riesgo?", calc.frase_riesgo_coste(fondos))
evento = st.altair_chart(
    comp.grafico_riesgo_coste(fondos), theme=None, on_select="rerun", selection_mode="fondo", key="riesgo_coste"
)
comp.ir_a_ficha(evento)
comp.nota("Cada punto es un fondo y cada raya, la mediana de su nivel de riesgo. Pulsa un punto para abrir su ficha.")

comp.seccion("¿Cuánto tiempo hay que mantenerlos?", calc.frase_horizonte(fondos))
st.altair_chart(comp.grafico_horizonte(fondos), theme=None)

comp.seccion("¿En qué se diferencian Bestinver y Azvalor?", calc.frase_gestoras(fondos))
st.altair_chart(comp.grafico_gestoras(fondos), theme=None)
comp.nota("Cada punto es un fondo y cada raya vertical, la mediana de la gestora.")
