"""Fiabilidad: cómo se obtienen los datos, qué se comprueba y qué conviene revisar."""

import pandas as pd
import streamlit as st

import calculos as calc
import componentes as comp
import datos

fondos = datos.cargar_o_avisar(datos.fondos)
resumen = datos.cargar_o_avisar(datos.resumen)
calidad = resumen["calidad"]
pendientes = calc.citas_no_encontradas(fondos)

comp.pregunta(
    "¿Hasta qué punto son fiables estos datos?",
    f"Un modelo de IA lee cada KID y devuelve sus datos con la cita del documento de la que salen. "
    f"De {calidad['evidencias_total']} citas, {calidad['evidencias_verificadas']} aparecen literalmente en el "
    "texto del KID; el resto se señala para revisarlo.",
)

comp.seccion("¿Cómo se obtienen?")
st.html(
    """
<ol class="kid-pasos">
  <li><b>Captura</b><span>Cada mes se descargan los KID de las webs de Bestinver y Azvalor, respetando su
  robots.txt. Se guarda el origen, la fecha y la huella de cada PDF, para no procesar dos veces el mismo
  documento.</span></li>
  <li><b>Conversión a texto</b><span>Cada PDF se convierte a texto estructurado, con reconocimiento óptico de
  caracteres en las páginas que lo necesitan.</span></li>
  <li><b>Extracción con IA</b><span>Un modelo de Amazon Bedrock rellena un esquema cerrado con los campos del KID.
  La salida estructurada garantiza el formato, y si un dato no aparece en el documento queda vacío: no se
  inventa.</span></li>
  <li><b>Comprobación</b><span>Se valida el ISIN con su dígito de control y contra el publicado en la web, se
  comprueba que el riesgo esté entre 1 y 7 y se busca cada cita en el texto del documento.</span></li>
  <li><b>Carga</b><span>Los datos se guardan en una base de datos PostgreSQL, sin duplicados, y se consultan
  a través de una API.</span></li>
</ol>
"""
)

comp.seccion("¿Qué se comprueba?")
n = len(fondos)
coinciden = calidad["isin_coinciden_web"]
comparables = calidad["isin_comparables_web"]
sri_ok = int(fondos["validaciones"].apply(lambda v: bool((v or {}).get("sri_en_rango"))).sum())
st.html(
    comp.medidor(
        "ISIN válido",
        [
            (calidad["isin_validos"], comp.VERIFICADO, "Válidos"),
            (n - calidad["isin_validos"], comp.NO_VERIFICADO, "No válidos"),
        ],
        f"{calidad['isin_validos']} de {n}",
    )
    + comp.medidor(
        "ISIN igual al de la web de la gestora",
        [
            (coinciden, comp.VERIFICADO, "Coinciden"),
            (comparables - coinciden, comp.NO_VERIFICADO, "No coinciden"),
            (n - comparables, comp.APAGADO, "La web no publica un ISIN único"),
        ],
        f"{coinciden} de {comparables} comparables; {n - comparables} sin ISIN en la web",
    )
    + comp.medidor(
        "Indicador de riesgo entre 1 y 7",
        [(sri_ok, comp.VERIFICADO, "En rango"), (n - sri_ok, comp.NO_VERIFICADO, "Fuera de rango")],
        f"{sri_ok} de {n}",
    )
    + comp.medidor(
        "Citas encontradas en el texto del KID",
        [
            (calidad["evidencias_verificadas"], comp.VERIFICADO, "Encontradas"),
            (calidad["evidencias_total"] - calidad["evidencias_verificadas"], comp.NO_VERIFICADO, "No encontradas"),
        ],
        f"{calidad['evidencias_verificadas']} de {calidad['evidencias_total']}",
    )
    + comp.leyenda_estados()
)

if pendientes:
    comp.seccion(
        "¿Qué conviene revisar?",
        "Estas citas no aparecen tal cual en el texto del documento. No significa que el dato sea erróneo: "
        "a menudo se debe a diferencias de formato entre el PDF y su texto, como tablas o saltos de línea. "
        "Conviene comprobarlas en el KID original.",
    )
    filas = []
    for isin, campo in pendientes:
        detalle = datos.cargar_o_avisar(datos.detalle, isin) or {}
        filas.append(
            {
                "isin": isin,
                "fondo": fondos.loc[fondos["isin"] == isin, "nombre_corto"].iloc[0],
                "campo": calc.CAMPOS.get(campo, campo),
                "valor": comp.valor_campo(campo, detalle.get(campo)),
                "cita": (detalle.get("evidencias") or {}).get(campo),
            }
        )
    st.html(comp.tabla_revision(filas))

comp.seccion("¿Cuándo se actualizan?")
ultima = fondos["ultima_descarga"].max()
proxima = calc.proxima_ejecucion(pd.Timestamp.now(tz="Europe/Madrid"))
modelos = ", ".join(sorted({calc.nombre_modelo(m) for m in fondos["modelo"].dropna()}))
st.html(
    f'<p class="kid-respuesta">El proceso completo se ejecuta solo el día 15 de cada mes a las 9:00. '
    f"La última actualización fue el {ultima:%d/%m/%Y} y la próxima será el {proxima:%d/%m/%Y}. "
    f"Si una gestora publica un KID nuevo, se conserva el anterior como versión histórica. "
    f"Modelo que extrae los datos: {comp.e(modelos)}, en Amazon Bedrock.</p>"
)
