"""Ficha de un fondo: los datos de su KID organizados como el propio documento, cada uno con la
cita literal de la que sale y el resultado de su verificación."""

import pandas as pd
import streamlit as st

import calculos as calc
import componentes as comp
import datos

fondos = datos.cargar_o_avisar(datos.fondos)
if fondos.empty:
    st.info("Todavía no hay fondos cargados.")
    st.stop()

# El fondo llega en la URL (?isin=...) desde los enlaces de otras páginas; se puede compartir
opciones = fondos.sort_values("nombre_corto")["isin"].tolist()
nombres = dict(zip(fondos["isin"], fondos["nombre_corto"], strict=True))
pedido = st.query_params.get("isin")
isin = st.selectbox(
    "Fondo",
    opciones,
    index=opciones.index(pedido) if pedido in opciones else 0,
    format_func=lambda i: f"{nombres[i]} ({i})",
)
st.query_params["isin"] = isin

d = datos.cargar_o_avisar(datos.detalle, isin)
if d is None:
    st.warning(f"No hay ningún KID con ISIN {isin}.")
    st.stop()

fondo = fondos[fondos["isin"] == isin].iloc[0]
evidencias = d.get("evidencias") or {}
verificadas = d.get("verificacion_evidencias") or {}
fecha_kid = pd.to_datetime(d.get("fecha_documento"))

presentacion = f"Fondo de {fondo.gestora_web}. ISIN {isin}."
if pd.notna(fecha_kid):
    presentacion += f" KID con fecha {fecha_kid:%d/%m/%Y}."
comp.pregunta(fondo.nombre_corto, presentacion)

# ¿Qué riesgos corro? -------------------------------------------------------------------------
comp.seccion("¿Qué riesgo tiene?")
st.html(comp.escala(int(d["sri"])) + comp.cita(evidencias.get("sri"), verificadas.get("sri")))

# Plazo y costes ------------------------------------------------------------------------------
comp.seccion("¿Cuánto tiempo hay que mantenerlo y cuánto cuesta?")
datos_clave = [
    ("periodo_mantenimiento_anios", "Plazo recomendado", calc.anios(d.get("periodo_mantenimiento_anios")), ""),
    ("gastos_corrientes_pct", "Gastos corrientes", calc.pct(d.get("gastos_corrientes_pct")), "al año"),
    ("costes_entrada_pct", "Comisión de entrada", calc.pct(d.get("costes_entrada_pct")), "al invertir"),
    ("costes_salida_pct", "Comisión de salida", calc.pct(d.get("costes_salida_pct")), "al reembolsar"),
]
for columna, (campo, etiqueta, valor, unidad) in zip(st.columns(4, gap="large"), datos_clave, strict=True):
    if valor == "sin dato":
        cifra = '<p class="kid-dato kid-dato--vacio">No figura en el KID</p>'
    else:
        cifra = f'<p class="kid-dato">{comp.e(valor)}{f"<small>{unidad}</small>" if unidad else ""}</p>'
    columna.html(
        f'<p class="kid-etiqueta">{etiqueta}</p>{cifra}' + comp.cita(evidencias.get(campo), verificadas.get(campo))
    )

if not calc.falta(fondo.gastos_corrientes_pct) and not calc.falta(fondo.periodo_mantenimiento_anios):
    plazo = fondo.periodo_mantenimiento_anios
    impacto = calc.impacto_costes(
        10_000, plazo, fondo.gastos_corrientes_pct, fondo.costes_entrada_pct, fondo.costes_salida_pct
    )
    comp.seccion(
        "¿Qué supone en euros?",
        f"Con 10.000 € mantenidos {calc.anios(plazo)} y sin rentabilidad, los costes se llevarían "
        f"{calc.eur(impacto['impacto'])} y quedarían {calc.eur(impacto['valor_con_costes'])}. "
        f"La incidencia anual de los costes es del {calc.pct(impacto['incidencia_anual_pct'])}.",
    )
    st.page_link("paginas/costes.py", label="Comparar los costes con los de otros fondos", icon=":material/euro:")

frase = calc.posicion_en_nivel(fondos, isin)
if frase:
    comp.seccion("¿Cómo se compara con fondos de su mismo riesgo?", frase)
    st.altair_chart(comp.grafico_riesgo_coste(fondos, destacar=isin, alto=320), theme=None)

# Origen y trazabilidad -----------------------------------------------------------------------
comp.seccion(
    "¿De dónde salen estos datos?",
    f"Del KID publicado en la web de {fondo.gestora_web}. Cada dato va acompañado del fragmento del documento "
    "del que se ha extraído.",
)
with st.container(horizontal=True):
    st.link_button("Abrir el KID original (PDF)", datos.enlace_kid(isin), icon=":material/picture_as_pdf:")
    if d.get("url_ficha"):
        st.link_button(f"Ver el fondo en la web de {fondo.gestora_web}", d["url_ficha"], icon=":material/open_in_new:")

st.html(comp.tabla_trazabilidad(d))
st.html(comp.validaciones(d.get("validaciones") or {}))

extraccion = pd.to_datetime(d.get("fecha_extraccion"))
primera = pd.to_datetime(d.get("primera_descarga"))
comp.nota(
    f"Datos extraídos con {calc.nombre_modelo(d.get('modelo'))} en Amazon Bedrock el {extraccion:%d/%m/%Y}. "
    f"El documento se descargó por primera vez el {primera:%d/%m/%Y}."
)

historial = d.get("historial") or []
if len(historial) > 1:
    comp.seccion("Versiones anteriores del KID", f"Se han capturado {len(historial)} versiones de este documento.")
    st.html(comp.tabla_versiones(historial))
