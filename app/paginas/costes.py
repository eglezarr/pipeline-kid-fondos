"""Costes: cuánto dinero se llevan los costes de cada fondo a lo largo de un plazo."""

import streamlit as st

import calculos as calc
import componentes as comp
import datos

fondos = datos.cargar_o_avisar(datos.fondos)

comp.pregunta(
    "¿Cuánto se llevan los costes?",
    "Los porcentajes de costes parecen pequeños, pero se acumulan año tras año. Elige cuánto invertir y "
    "durante cuánto tiempo para verlos en euros.",
)

c1, c2, c3 = st.columns(3, gap="large")
importe = c1.number_input("Importe invertido (€)", min_value=1_000, max_value=1_000_000, value=10_000, step=1_000)
modo = c2.radio(
    "Plazo",
    ["El mismo para todos", "El recomendado en cada KID"],
    horizontal=True,
    help="Con el mismo plazo, los fondos se comparan en igualdad de condiciones.",
)
plazo_fijo = None
if modo == "El mismo para todos":
    plazo_fijo = c2.select_slider("Años", options=list(range(1, 16)), value=5, format_func=calc.anios)
rentabilidad = c3.select_slider(
    "Rentabilidad bruta anual supuesta",
    options=[x / 2 for x in range(-6, 21)],
    value=0.0,
    format_func=calc.pct,
    help="Antes de costes. Con 0 % se ve solo el efecto de los costes.",
)
fuentes = sorted(fondos["fuente"].unique())
elegidas = st.pills("Gestora", fuentes, selection_mode="multi", default=fuentes, format_func=comp.nombre_gestora)

seleccion = fondos[fondos["fuente"].isin(elegidas or fuentes)]
tabla = calc.tabla_impacto(seleccion, importe, rentabilidad, plazo_fijo)

st.html(f'<p class="kid-respuesta">{comp.e(calc.frase_impacto(tabla, importe, rentabilidad, plazo_fijo))}</p>')
if not tabla.empty:
    st.altair_chart(comp.grafico_costes(tabla), theme=None)
    excluidos = len(seleccion) - len(tabla)
    if excluidos:
        comp.nota(f"{calc.fondos_txt(excluidos)} sin gastos corrientes o sin plazo recomendado en su KID no aparecen.")

with st.expander("Cómo se calcula"):
    st.markdown(
        """
Para cada fondo, con el importe $I$, el plazo de $T$ años y la rentabilidad bruta anual $r$:

- la comisión de entrada $e$ se descuenta al invertir;
- los gastos corrientes $g$ se descuentan cada año sobre el valor de la inversión;
- la comisión de salida $s$ se descuenta al reembolsar.

$$V_{\\text{sin costes}} = I\\,(1+r)^T \\qquad V_{\\text{con costes}} = I\\,(1-e)\\,\\big[(1+r)(1-g)\\big]^T\\,(1-s)$$

Lo que se llevan los costes es la diferencia entre ambos valores: incluye lo cobrado y la
rentabilidad que ese dinero ha dejado de generar. La **incidencia anual de los costes** es cuánto
rebajan la rentabilidad de cada año, el mismo concepto que usa el KID.

Es una aproximación: el KID calcula sus tablas de costes con sus propios escenarios de rentabilidad
e incluye conceptos que aquí no se extraen, como los costes de operación o las comisiones de éxito.
Si el KID no indica comisión de entrada o de salida, se toma como cero.
"""
    )

with st.expander("Ver los datos en una tabla"):
    columnas = ["nombre_corto", "gestora_web", "plazo", "gastos_corrientes_pct", "impacto", "valor_con_costes"]
    vista = tabla[columnas + ["incidencia_anual_pct"]].round(
        {"impacto": 0, "valor_con_costes": 0, "incidencia_anual_pct": 2}
    )
    st.dataframe(
        vista,
        hide_index=True,
        width="stretch",
        column_config={
            "nombre_corto": "Fondo",
            "gestora_web": "Gestora",
            "plazo": st.column_config.NumberColumn("Plazo (años)", format="localized"),
            "gastos_corrientes_pct": st.column_config.NumberColumn("Gastos corrientes (%)", format="localized"),
            "impacto": st.column_config.NumberColumn("Costes (€)", format="localized"),
            "valor_con_costes": st.column_config.NumberColumn("Valor final (€)", format="localized"),
            "incidencia_anual_pct": st.column_config.NumberColumn("Incidencia anual (%)", format="localized"),
        },
    )
