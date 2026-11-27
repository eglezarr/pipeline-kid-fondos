"""Sistema visual de la aplicación: colores, estilos, piezas HTML y gráficos de Altair.

El elemento central es la escala de riesgo de 1 a 7 del KID (el indicador SRI). Es lo único que
lleva color fuerte: una rampa de un solo tono, de claro (riesgo bajo) a oscuro (riesgo alto). El
resto de la interfaz es tinta azul marino sobre blanco, para que el riesgo destaque.
"""

import html

import altair as alt
import pandas as pd
import streamlit as st

import calculos as calc

# ---------------------------------------------------------------------------------------------
# Colores (validados: rampa monótona en luminosidad y contraste suficiente sobre blanco)
# ---------------------------------------------------------------------------------------------

TINTA = "#1d2b44"
TINTA_SUAVE = "#5b6577"
LINEA = "#e3e6eb"
PANEL = "#f4f5f7"
APAGADO = "#c9ced6"  # fondos no destacados en un gráfico

# Escala de riesgo: un tono, siete pasos de claro a oscuro. PISTA: casillas vacías de la escala.
RIESGO = ["#e49597", "#da767b", "#cd5760", "#bb3a49", "#a12437", "#841428", "#650c1d"]
PISTA = "#f5d5d5"
# Texto sobre cada paso de la rampa: tinta en los claros, blanco en los oscuros
TEXTO_RIESGO = [TINTA, TINTA, "#ffffff", "#ffffff", "#ffffff", "#ffffff", "#ffffff"]

# Gestoras: dos tonos distinguibles también con daltonismo (azul y ocre)
GESTORAS = {"bestinver": "#2e69b2", "azvalor": "#bd821a"}
OTRA_GESTORA = "#6b7280"

VERIFICADO = "#16794a"
NO_VERIFICADO = "#9a6700"

FUENTE = "Atkinson Hyperlegible Next"

LOCALE_ES = {
    "number": {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["", " €"]},
}


def color_gestora(fuente: str) -> str:
    return GESTORAS.get(fuente, OTRA_GESTORA)


def nombre_gestora(fuente: str) -> str:
    return calc.NOMBRES_FUENTE.get(fuente, fuente.capitalize())


def color_por_gestora(fondos: pd.DataFrame, leyenda: bool = True) -> alt.Color:
    """Color por gestora con una escala fija: cada gestora conserva su color aunque se filtre la otra."""
    fuentes = sorted(set(fondos["fuente"]) | set(GESTORAS))
    return alt.Color(
        "gestora_web:N",
        scale=alt.Scale(domain=[nombre_gestora(f) for f in fuentes], range=[color_gestora(f) for f in fuentes]),
        legend=alt.Legend(title=None) if leyenda else None,
    )


# ---------------------------------------------------------------------------------------------
# Estilos globales
# ---------------------------------------------------------------------------------------------

CSS = f"""
<style>
:root {{
  --tinta: {TINTA};
  --tinta-suave: {TINTA_SUAVE};
  --linea: {LINEA};
  --panel: {PANEL};
}}
[data-testid="stMainBlockContainer"] {{ padding-top: 5.5rem; padding-bottom: 4rem; max-width: 1180px; }}
h1, h2, h3 {{ letter-spacing: -0.015em; }}
.kid-pregunta {{ font-size: clamp(2rem, 4vw, 2.9rem); font-weight: 800; line-height: 1.08;
  margin: 0 0 .9rem; max-width: 24ch; color: var(--tinta); }}
.kid-respuesta {{ font-size: 1.2rem; line-height: 1.55; color: var(--tinta-suave);
  max-width: 64ch; margin: 0 0 1.75rem; }}
.kid-seccion {{ font-size: 1.55rem; font-weight: 750; line-height: 1.2; margin: 3.25rem 0 .5rem;
  max-width: 44ch; color: var(--tinta); }}
.kid-nota {{ font-size: .92rem; line-height: 1.5; color: var(--tinta-suave); max-width: 72ch; }}
.kid-marca {{ display: inline-block; width: .62rem; height: .62rem; border-radius: 50%;
  margin-right: .45rem; flex: none; }}
.kid-leyenda {{ display: flex; gap: 1.25rem; flex-wrap: wrap; font-size: .95rem; color: var(--tinta);
  margin: .25rem 0 0; align-items: center; }}
.kid-leyenda span {{ display: inline-flex; align-items: center; }}

/* Escalera de riesgo: la pieza principal de la portada */
.kid-escalera-marco {{ overflow-x: auto; padding-bottom: .5rem; }}
.kid-escalera {{ display: grid; grid-template-columns: repeat(7, minmax(118px, 1fr)); column-gap: 2px;
  min-width: 840px; }}
.kid-escalon {{ height: 132px; display: flex; align-items: flex-end; }}
.kid-escalon div {{ width: 100%; border-radius: 4px 4px 0 0; display: flex; align-items: flex-start;
  padding: .45rem .6rem; font-size: 1.6rem; font-weight: 800; line-height: 1; }}
.kid-eje {{ grid-column: 1 / -1; display: flex; align-items: center; gap: .75rem; margin: .6rem 0 1rem;
  font-size: .9rem; color: var(--tinta-suave); }}
.kid-flecha {{ flex: 1; height: 1px; background: currentColor; position: relative; }}
.kid-flecha::before, .kid-flecha::after {{ content: ""; position: absolute; top: -4px; width: 0; height: 0;
  border-top: 4.5px solid transparent; border-bottom: 4.5px solid transparent; }}
.kid-flecha::before {{ left: -1px; border-right: 7px solid currentColor; }}
.kid-flecha::after {{ right: -1px; border-left: 7px solid currentColor; }}
.kid-peldano {{ padding: 0 .6rem 0 0; }}
.kid-peldano p {{ margin: 0 0 .5rem; font-size: .85rem; color: var(--tinta-suave); }}
.kid-peldano ul {{ list-style: none; margin: 0; padding: 0; }}
.kid-peldano li {{ margin: 0 0 .4rem; line-height: 1.25; font-size: .93rem; }}
.kid-peldano a {{ display: flex; align-items: baseline; color: var(--tinta); text-decoration: none; }}
.kid-peldano a:hover, .kid-peldano a:focus-visible {{ text-decoration: underline; }}
.kid-peldano a .kid-marca {{ transform: translateY(-.05rem); }}

/* Escala de riesgo de la ficha, como la del KID */
.kid-escala {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; max-width: 520px; }}
.kid-escala span {{ height: 52px; display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 1.25rem; background: {PISTA}; color: {TINTA_SUAVE}; }}
.kid-escala span:first-child {{ border-radius: 4px 0 0 4px; }}
.kid-escala span:last-child {{ border-radius: 0 4px 4px 0; }}
.kid-escala-eje {{ display: flex; align-items: center; gap: .6rem; max-width: 520px; margin-top: .5rem;
  font-size: .85rem; color: var(--tinta-suave); }}

/* Escala en miniatura de las tablas */
.kid-mini {{ display: inline-flex; gap: 2px; vertical-align: middle; }}
.kid-mini i {{ width: 9px; height: 14px; background: {PISTA}; border-radius: 1px; }}
.kid-mini-n {{ font-weight: 700; margin-left: .45rem; }}

/* Tabla de fondos */
.kid-tabla {{ width: 100%; border-collapse: collapse; font-size: .95rem; }}
.kid-tabla th {{ text-align: left; font-weight: 600; color: var(--tinta-suave); font-size: .85rem;
  padding: .55rem .6rem; border-bottom: 1px solid var(--linea); white-space: nowrap; }}
.kid-tabla td {{ padding: .7rem .6rem; border-bottom: 1px solid var(--linea); vertical-align: middle; }}
.kid-tabla .n {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.kid-tabla a {{ color: var(--tinta); font-weight: 650; text-decoration: none; }}
.kid-tabla a:hover, .kid-tabla a:focus-visible {{ text-decoration: underline; }}
.kid-tabla small {{ display: block; color: var(--tinta-suave); font-size: .8rem; margin-top: .15rem; }}
.kid-tabla-marco {{ overflow-x: auto; }}
.kid-tabla--citas td {{ vertical-align: top; }}
.kid-tabla-cita {{ font-style: italic; color: var(--tinta-suave); line-height: 1.45; max-width: 46ch; }}
.kid-comprobaciones {{ list-style: none; padding: 0 !important; margin: 1.25rem 0 0; display: grid; gap: .5rem; }}
.kid-comprobaciones li {{ margin: 0 !important; padding: 0 !important; }}

/* Datos de la ficha con su cita del documento */
.kid-dato {{ font-size: 2.4rem; font-weight: 800; line-height: 1.05; color: var(--tinta); margin: .2rem 0; }}
.kid-dato--vacio {{ font-size: 1.15rem; font-weight: 600; color: var(--tinta-suave); padding: .55rem 0 .4rem; }}
.kid-dato small {{ font-size: 1rem; font-weight: 500; color: var(--tinta-suave); margin-left: .3rem; }}
.kid-etiqueta {{ font-size: .95rem; color: var(--tinta-suave); margin: 0; }}
.kid-cita {{ margin: .8rem 0 0; padding: 0 0 0 .9rem; border-left: 3px solid var(--linea); }}
.kid-cita blockquote {{ margin: 0; font-style: italic; color: var(--tinta); line-height: 1.5;
  font-size: .95rem; }}
.kid-cita figcaption {{ display: flex; align-items: center; gap: .35rem; font-size: .82rem;
  margin-top: .35rem; color: var(--tinta-suave); }}
.kid-icono {{ display: inline-block; position: relative; width: 15px; height: 15px; border-radius: 50%;
  flex: none; vertical-align: -2px; }}
.kid-icono--ok {{ background: {VERIFICADO}; }}
.kid-icono--ok::after {{ content: ""; position: absolute; left: 5px; top: 2.5px; width: 3.5px; height: 7px;
  border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }}
.kid-icono--aviso {{ background: {NO_VERIFICADO}; }}
.kid-icono--aviso::after {{ content: ""; position: absolute; left: 6.5px; top: 3px; width: 2px; height: 5.5px;
  background: #fff; box-shadow: 0 7px 0 #fff; }}
.kid-icono--neutro {{ border: 1.5px solid {APAGADO}; }}
.kid-icono--neutro::after {{ content: ""; position: absolute; left: 3px; top: 5.25px; width: 6px; height: 1.5px;
  background: {TINTA_SUAVE}; }}

/* Medidores de la página de fiabilidad */
.kid-medidor {{ margin: 0 0 1.4rem; max-width: 720px; }}
.kid-medidor p {{ margin: 0 0 .4rem; display: flex; justify-content: space-between; gap: 1rem; }}
.kid-medidor b {{ font-weight: 700; }}
.kid-medidor span {{ color: var(--tinta-suave); font-variant-numeric: tabular-nums; }}
.kid-barra {{ display: flex; gap: 2px; height: 8px; }}
.kid-barra i {{ border-radius: 4px; }}

.kid-pasos {{ counter-reset: paso; list-style: none; padding: 0; margin: 0; max-width: 760px; }}
.kid-pasos li {{ counter-increment: paso; display: grid; grid-template-columns: 2.4rem 1fr; column-gap: .9rem;
  padding: .9rem 0; border-bottom: 1px solid var(--linea); }}
.kid-pasos li::before {{ content: counter(paso); font-weight: 800; font-size: 1.35rem; color: var(--tinta);
  grid-row: span 2; }}
.kid-pasos b {{ font-weight: 700; }}
.kid-pasos span {{ color: var(--tinta-suave); line-height: 1.5; }}

.kid-pie {{ margin-top: 4.5rem; padding-top: 1rem; border-top: 1px solid var(--linea); font-size: .85rem;
  color: var(--tinta-suave); max-width: 80ch; line-height: 1.6; }}

/* En pantallas estrechas la escalera se apila: un nivel por fila, con sus fondos al lado */
@media (max-width: 640px) {{
  .kid-escalera {{ grid-template-columns: 4.5rem 1fr; min-width: 0; row-gap: 2px; }}
  .kid-escalon {{ grid-column: 1; grid-row: var(--n); height: auto; align-items: stretch; }}
  .kid-escalon div {{ height: auto !important; width: calc(40% + var(--n) * 8.5%); border-radius: 0 4px 4px 0;
    font-size: 1.3rem; }}
  .kid-peldano {{ grid-column: 2; grid-row: var(--n); padding: .55rem 0 .7rem .8rem;
    border-bottom: 1px solid var(--linea); }}
  .kid-eje {{ display: none; }}
}}

@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""


def estilos() -> None:
    st.html(CSS)


# ---------------------------------------------------------------------------------------------
# Piezas de texto
# ---------------------------------------------------------------------------------------------

FLECHA = '<span class="kid-flecha" aria-hidden="true"></span>'

# Iconos de estado dibujados con CSS (st.html no admite SVG): siempre acompañados de texto
ICONO_OK = '<i class="kid-icono kid-icono--ok" aria-hidden="true"></i>'
ICONO_AVISO = '<i class="kid-icono kid-icono--aviso" aria-hidden="true"></i>'


def e(texto) -> str:
    """Escapa texto para insertarlo en HTML."""
    return html.escape("" if texto is None else str(texto))


def pregunta(titulo: str, respuesta: str | None = None) -> None:
    """Cabecera de página: la pregunta del KID que responde y una frase calculada con los datos."""
    cuerpo = f'<h1 class="kid-pregunta">{e(titulo)}</h1>'
    if respuesta:
        cuerpo += f'<p class="kid-respuesta">{e(respuesta)}</p>'
    st.html(cuerpo)


def seccion(titulo: str, respuesta: str | None = None) -> None:
    cuerpo = f'<h2 class="kid-seccion">{e(titulo)}</h2>'
    if respuesta:
        cuerpo += f'<p class="kid-respuesta">{e(respuesta)}</p>'
    st.html(cuerpo)


def nota(texto: str) -> None:
    st.html(f'<p class="kid-nota">{e(texto)}</p>')


def leyenda_gestoras(fuentes) -> str:
    elementos = "".join(
        f'<span><i class="kid-marca" style="background:{color_gestora(f)}"></i>{e(nombre_gestora(f))}</span>'
        for f in sorted(set(fuentes))
    )
    return f'<div class="kid-leyenda">{elementos}</div>'


def enlace_ficha(isin: str) -> str:
    return f"ficha?isin={e(isin)}"


# ---------------------------------------------------------------------------------------------
# Escalas de riesgo
# ---------------------------------------------------------------------------------------------


def escalera(fondos: pd.DataFrame) -> str:
    """Los siete niveles de riesgo como peldaños, con los fondos de cada nivel debajo."""
    escalones, peldanos = [], []
    for nivel in calc.NIVELES_RIESGO:
        grupo = fondos[fondos["sri"] == nivel].sort_values(["fuente", "nombre_corto"])
        alto = 40 + (nivel - 1) * 15
        escalones.append(
            f'<div class="kid-escalon" style="--n:{nivel}"><div style="height:{alto}px;background:{RIESGO[nivel - 1]};'
            f'color:{TEXTO_RIESGO[nivel - 1]}">{nivel}</div></div>'
        )
        # El color del punto ya indica la gestora: se omite su nombre al principio para aligerar la lista
        lista = "".join(
            f'<li><a href="{enlace_ficha(f.isin)}" target="_self" title="{e(f.nombre_producto)} ({e(f.isin)})">'
            f'<i class="kid-marca" style="background:{color_gestora(f.fuente)}"></i>'
            f"{e(calc.sin_gestora(f.nombre_corto, f.gestora_web))}</a></li>"
            for f in grupo.itertuples()
        )
        total = calc.fondos_txt(len(grupo)) if len(grupo) else "Ningún fondo"
        peldanos.append(
            f'<section class="kid-peldano" style="--n:{nivel}" aria-label="Riesgo {nivel}: {total}">'
            f"<p>{total}</p><ul>{lista}</ul></section>"
        )
    eje = f'<div class="kid-eje"><span>Riesgo más bajo</span>{FLECHA}<span>Riesgo más alto</span></div>'
    return (
        f'<div class="kid-escalera-marco"><div class="kid-escalera">{"".join(escalones)}{eje}'
        f"{''.join(peldanos)}</div></div>{leyenda_gestoras(fondos['fuente'])}"
    )


def escala(sri: int) -> str:
    """Escala de 1 a 7 con el nivel del fondo marcado, como la dibuja el KID."""
    casillas = "".join(
        f'<span style="background:{RIESGO[n - 1]};color:{TEXTO_RIESGO[n - 1]}" aria-current="true">{n}</span>'
        if n == sri
        else f"<span>{n}</span>"
        for n in calc.NIVELES_RIESGO
    )
    return (
        f'<div class="kid-escala" role="img" aria-label="Indicador de riesgo {sri} de 7">{casillas}</div>'
        f'<div class="kid-escala-eje"><span>Riesgo más bajo</span>{FLECHA}<span>Riesgo más alto</span></div>'
    )


def mini_escala(sri: int) -> str:
    casillas = "".join(
        f'<i style="background:{RIESGO[n - 1]}"></i>' if n == sri else "<i></i>" for n in calc.NIVELES_RIESGO
    )
    return (
        f'<span class="kid-mini" role="img" aria-label="Riesgo {sri} de 7">{casillas}</span>'
        f'<span class="kid-mini-n" aria-hidden="true">{sri}</span>'
    )


# ---------------------------------------------------------------------------------------------
# Tabla de fondos, citas y medidores
# ---------------------------------------------------------------------------------------------


def tabla_fondos(fondos: pd.DataFrame) -> str:
    filas = []
    for f in fondos.itertuples():
        filas.append(
            "<tr>"
            f"<td>{mini_escala(f.sri)}</td>"
            f'<td><a href="{enlace_ficha(f.isin)}" target="_self">{e(f.nombre_corto)}</a>'
            f"<small>{e(f.isin)}</small></td>"
            f'<td><span class="kid-leyenda"><span><i class="kid-marca" style="background:{color_gestora(f.fuente)}">'
            f"</i>{e(f.gestora_web)}</span></span></td>"
            f'<td class="n">{calc.anios(f.periodo_mantenimiento_anios)}</td>'
            f'<td class="n">{calc.pct(f.gastos_corrientes_pct)}</td>'
            f'<td class="n">{calc.pct(f.costes_entrada_pct)}</td>'
            f'<td class="n">{calc.pct(f.costes_salida_pct)}</td>'
            f'<td class="n">{"" if pd.isna(f.fecha_documento) else f.fecha_documento.strftime("%d/%m/%Y")}</td>'
            "</tr>"
        )
    cabecera = (
        "<tr><th>Riesgo</th><th>Fondo</th><th>Gestora</th><th class='n'>Plazo recomendado</th>"
        "<th class='n'>Gastos corrientes</th><th class='n'>Entrada</th><th class='n'>Salida</th>"
        "<th class='n'>Fecha del KID</th></tr>"
    )
    return (
        f'<div class="kid-tabla-marco"><table class="kid-tabla"><thead>{cabecera}</thead>'
        f"<tbody>{''.join(filas)}</tbody></table></div>"
    )


def cita(texto: str | None, verificada: bool | None) -> str:
    """Fragmento literal del KID que respalda un dato, con el resultado de su verificación."""
    if not texto:
        return '<figure class="kid-cita"><figcaption>El KID no recoge este dato.</figcaption></figure>'
    if verificada:
        estado = f"{ICONO_OK}<span>Cita encontrada en el texto del KID</span>"
    else:
        estado = f"{ICONO_AVISO}<span>Cita no encontrada literalmente en el texto: conviene revisarla en el PDF</span>"
    return f'<figure class="kid-cita"><blockquote>«{e(texto)}»</blockquote><figcaption>{estado}</figcaption></figure>'


def medidor(titulo: str, partes: list[tuple[int, str, str]], detalle: str) -> str:
    """Barra segmentada: cada parte es (cantidad, color, descripción)."""
    total = sum(n for n, _, _ in partes) or 1
    segmentos = "".join(
        f'<i style="flex:{n / total};background:{color}" title="{e(desc)}: {n}"></i>' for n, color, desc in partes if n
    )
    return (
        f'<div class="kid-medidor"><p><b>{e(titulo)}</b><span>{e(detalle)}</span></p>'
        f'<div class="kid-barra" role="img" aria-label="{e(titulo)}: {e(detalle)}">{segmentos}</div></div>'
    )


# ---------------------------------------------------------------------------------------------
# Gráficos (Altair con tema propio; en Streamlit se muestran con theme=None)
# ---------------------------------------------------------------------------------------------


def configurar(grafico: alt.TopLevelMixin) -> alt.TopLevelMixin:
    return (
        grafico.configure(font=FUENTE, locale=LOCALE_ES, background="transparent")
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=TINTA_SUAVE,
            titleColor=TINTA_SUAVE,
            labelFontSize=13,
            titleFontSize=13,
            titleFontWeight=600,
            gridColor=LINEA,
            domainColor=LINEA,
            tickColor=LINEA,
            titlePadding=12,
            labelPadding=6,
        )
        .configure_legend(
            labelColor=TINTA,
            titleColor=TINTA_SUAVE,
            labelFontSize=13,
            titleFontSize=13,
            titleFontWeight=600,
            orient="top",
            symbolSize=110,
        )
        .configure_header(labelColor=TINTA, labelFontSize=14, labelFontWeight=700, titleColor=TINTA_SUAVE)
        .configure_title(color=TINTA, fontSize=14, fontWeight=700, anchor="start", offset=10)
    )


COLUMNAS_NO_GRAFICAS = ["validaciones", "verificacion_evidencias", "evidencias", "historial"]


def _con_textos(fondos: pd.DataFrame) -> pd.DataFrame:
    """Copia para los gráficos, con los textos de los tooltips ya formateados al estilo español."""
    datos = fondos.drop(columns=[c for c in COLUMNAS_NO_GRAFICAS if c in fondos.columns])
    datos["txt_gastos"] = datos["gastos_corrientes_pct"].map(calc.pct)
    datos["txt_plazo"] = datos["periodo_mantenimiento_anios"].map(calc.anios)
    datos["txt_entrada"] = datos["costes_entrada_pct"].map(calc.pct)
    datos["txt_salida"] = datos["costes_salida_pct"].map(calc.pct)
    return datos


TOOLTIP_FONDO = [
    alt.Tooltip("nombre_corto:N", title="Fondo"),
    alt.Tooltip("gestora_web:N", title="Gestora"),
    alt.Tooltip("sri:O", title="Riesgo"),
    alt.Tooltip("txt_gastos:N", title="Gastos corrientes"),
    alt.Tooltip("txt_plazo:N", title="Plazo recomendado"),
]


def _dispersion(isin: str, ancho: float) -> float:
    """Desplazamiento horizontal fijo para cada fondo (derivado del ISIN, sin relación con sus datos)."""
    semilla = sum((i + 1) * ord(c) for i, c in enumerate(isin)) % 1000
    return (semilla / 999 - 0.5) * ancho


def _repartir(valores: pd.Series, ancho: float) -> list[float]:
    """Desplazamientos simétricos para separar puntos que comparten posición (sin azar)."""
    n = len(valores)
    if n == 1:
        return [0.0]
    paso = min(ancho / (n - 1), 0.09)
    return [(i - (n - 1) / 2) * paso for i in range(n)]


def grafico_riesgo_coste(fondos: pd.DataFrame, destacar: str | None = None, alto: int = 380):
    """Gastos corrientes frente al nivel de riesgo, con la mediana de cada nivel."""
    datos = _con_textos(fondos.dropna(subset=["gastos_corrientes_pct"]))
    datos["x"] = datos["sri"] + datos["isin"].map(lambda i: _dispersion(i, 0.56))
    medianas = datos.groupby("sri", as_index=False)["gastos_corrientes_pct"].median()
    medianas["x1"], medianas["x2"] = medianas["sri"] - 0.36, medianas["sri"] + 0.36
    medianas["txt"] = medianas["gastos_corrientes_pct"].map(calc.pct)

    eje_x = alt.X(
        "x:Q",
        title="Indicador de riesgo del KID",
        scale=alt.Scale(domain=[0.4, 7.6], nice=False),
        axis=alt.Axis(values=list(calc.NIVELES_RIESGO), format="d", grid=False, labelFontSize=14),
    )
    eje_y = alt.Y(
        "gastos_corrientes_pct:Q",
        title="Gastos corrientes (% anual)",
        scale=alt.Scale(zero=True),
        axis=alt.Axis(format=".1f", tickCount=6),
    )
    seleccion = alt.selection_point(name="fondo", fields=["isin"], on="click")
    color = color_por_gestora(datos, leyenda=not destacar)
    if destacar:
        color = alt.condition(f"datum.isin == '{destacar}'", color, alt.value(APAGADO))

    mediana = (
        alt.Chart(medianas)
        .mark_rule(color=TINTA, strokeWidth=2, strokeCap="round")
        .encode(
            x="x1:Q",
            x2="x2:Q",
            y="gastos_corrientes_pct:Q",
            tooltip=[alt.Tooltip("sri:O", title="Riesgo"), alt.Tooltip("txt:N", title="Mediana de gastos")],
        )
    )
    puntos = (
        alt.Chart(datos)
        .mark_circle(size=120, opacity=1, stroke="#ffffff", strokeWidth=2, cursor="pointer")
        .encode(x=eje_x, y=eje_y, color=color, tooltip=TOOLTIP_FONDO)
        .add_params(seleccion)
    )
    capas = [mediana, puntos]
    if destacar:
        elegido = datos[datos["isin"] == destacar]
        capas.append(
            alt.Chart(elegido)
            .mark_circle(size=260, opacity=1, stroke="#ffffff", strokeWidth=2)
            .encode(
                x="x:Q",
                y="gastos_corrientes_pct:Q",
                color=color_por_gestora(datos, leyenda=False),
                tooltip=TOOLTIP_FONDO,
            )
        )
        etiqueta = alt.Chart(elegido).encode(x="x:Q", y="gastos_corrientes_pct:Q", text="nombre_corto:N")
        estilo = {"align": "left", "dx": 10, "dy": -14, "fontSize": 13, "fontWeight": 700}
        capas.append(etiqueta.mark_text(**estilo, stroke="#ffffff", strokeWidth=5, strokeJoin="round"))
        capas.append(etiqueta.mark_text(**estilo, color=TINTA))
    return configurar(alt.layer(*capas).properties(height=alto))


def grafico_horizonte(fondos: pd.DataFrame):
    """Periodo de mantenimiento recomendado: un punto por fondo, apilados y coloreados por riesgo."""
    datos = _con_textos(fondos.dropna(subset=["periodo_mantenimiento_anios"]))
    datos = datos.sort_values(["periodo_mantenimiento_anios", "sri", "nombre_corto"])
    datos["fila"] = datos.groupby("periodo_mantenimiento_anios").cumcount() + 1
    maximo = int(datos["periodo_mantenimiento_anios"].max()) + 1 if not datos.empty else 8
    filas = int(datos["fila"].max()) if not datos.empty else 1
    grafico = (
        alt.Chart(datos)
        .mark_circle(size=340, opacity=1, stroke="#ffffff", strokeWidth=2)
        .encode(
            x=alt.X(
                "periodo_mantenimiento_anios:Q",
                title="Periodo de mantenimiento recomendado (años)",
                scale=alt.Scale(domain=[0, maximo], nice=False),
                axis=alt.Axis(values=list(range(0, maximo + 1)), format="d", grid=False),
            ),
            y=alt.Y("fila:Q", title=None, axis=None, scale=alt.Scale(domain=[0, filas + 1])),
            color=alt.Color(
                "sri:O",
                title="Riesgo",
                scale=alt.Scale(domain=list(calc.NIVELES_RIESGO), range=RIESGO),
                legend=alt.Legend(direction="horizontal", symbolType="circle"),
            ),
            tooltip=TOOLTIP_FONDO,
        )
        .properties(height=max(160, 26 * (filas + 1)))
    )
    return configurar(grafico)


def grafico_gestoras(fondos: pd.DataFrame):
    """Bestinver y Azvalor cara a cara en tres medidas: un punto por fondo y la mediana."""
    paneles = []
    medidas = [
        ("sri", "Indicador de riesgo", [1, 7], "d"),
        ("gastos_corrientes_pct", "Gastos corrientes (% anual)", None, ".1f"),
        ("periodo_mantenimiento_anios", "Plazo recomendado (años)", None, "d"),
    ]
    fuentes = sorted(fondos["fuente"].unique())
    orden = {f: i for i, f in enumerate(fuentes)}
    # Etiquetas del eje: la posición 0, 1... de cada gestora se traduce a su nombre
    etiquetas = "[" + ", ".join(f"'{nombre_gestora(f)}'" for f in fuentes) + "][datum.value]"
    for columna, titulo, dominio, formato in medidas:
        datos = _con_textos(fondos.dropna(subset=[columna])).sort_values(["fuente", columna])
        # Fila de cada gestora y separación vertical de los puntos que coinciden
        datos["y"] = datos["fuente"].map(orden).astype(float)
        for (_, _), grupo in datos.groupby(["fuente", columna]):
            datos.loc[grupo.index, "y"] += _repartir(grupo[columna], 0.5)
        medianas = datos.groupby("fuente", as_index=False)[columna].median()
        medianas["y"] = medianas["fuente"].map(orden)
        escala_x = alt.Scale(domain=dominio, nice=False) if dominio else alt.Scale(zero=True, nice=True)
        eje_y = alt.Y(
            "y:Q",
            title=None,
            scale=alt.Scale(domain=[-0.6, len(fuentes) - 0.4], reverse=True),
            axis=alt.Axis(
                values=list(range(len(fuentes))),
                grid=False,
                domain=False,
                ticks=False,
                labelExpr=etiquetas,
                labelFontSize=14,
                labelColor=TINTA,
            ),
        )
        puntos = (
            alt.Chart(datos)
            .mark_circle(size=90, opacity=0.9, stroke="#ffffff", strokeWidth=1.5)
            .encode(
                x=alt.X(f"{columna}:Q", title=titulo, scale=escala_x, axis=alt.Axis(format=formato, tickCount=5)),
                y=eje_y,
                color=color_por_gestora(datos, leyenda=False),
                tooltip=TOOLTIP_FONDO,
            )
        )
        marca = (
            alt.Chart(medianas)
            .mark_tick(color=TINTA, thickness=3, size=34)
            .encode(x=f"{columna}:Q", y="y:Q", tooltip=[alt.Tooltip(f"{columna}:Q", title="Mediana", format=formato)])
        )
        paneles.append((puntos + marca).properties(width=290, height=160))
    return configurar(alt.hconcat(*paneles, spacing=28))


def grafico_costes(tabla: pd.DataFrame):
    """Barras ordenadas: euros que se llevan los costes en cada fondo."""
    datos = _con_textos(tabla)
    datos["txt_impacto"] = datos["impacto"].map(calc.eur)
    datos["txt_final"] = datos["valor_con_costes"].map(calc.eur)
    datos["txt_incidencia"] = datos["incidencia_anual_pct"].map(lambda v: calc.pct(v, 2) + " al año")
    datos["txt_plazo_calculo"] = datos["plazo"].map(calc.anios)
    orden = datos.sort_values("impacto", ascending=False)["nombre_corto"].tolist()
    base = alt.Chart(datos).encode(
        y=alt.Y("nombre_corto:N", sort=orden, title=None, axis=alt.Axis(labelLimit=260, labelFontSize=13)),
        x=alt.X(
            "impacto:Q",
            title="Lo que se llevan los costes (€)",
            axis=alt.Axis(format=",.0f", tickCount=5),
            scale=alt.Scale(nice=True),
        ),
        tooltip=[
            alt.Tooltip("nombre_corto:N", title="Fondo"),
            alt.Tooltip("txt_impacto:N", title="Coste total"),
            alt.Tooltip("txt_final:N", title="Valor final"),
            alt.Tooltip("txt_incidencia:N", title="Incidencia de los costes"),
            alt.Tooltip("txt_plazo_calculo:N", title="Plazo del cálculo"),
            alt.Tooltip("txt_gastos:N", title="Gastos corrientes"),
            alt.Tooltip("txt_entrada:N", title="Entrada"),
            alt.Tooltip("txt_salida:N", title="Salida"),
        ],
    )
    barras = base.mark_bar(size=16, cornerRadiusEnd=4).encode(color=color_por_gestora(datos))
    textos = base.mark_text(align="left", dx=6, fontSize=13, color=TINTA).encode(text="txt_impacto:N")
    return configurar((barras + textos).properties(height=max(180, 28 * len(datos))))


# ---------------------------------------------------------------------------------------------
# Navegación y pie
# ---------------------------------------------------------------------------------------------


def ir_a_ficha(evento) -> None:
    """Abre la ficha del fondo pulsado en un gráfico con selección."""
    seleccion = (evento or {}).get("selection", {}).get("fondo") or []
    if seleccion and seleccion[0].get("isin"):
        st.switch_page("paginas/ficha.py", query_params={"isin": seleccion[0]["isin"]})


def pie(fondos: pd.DataFrame | None) -> None:
    actualizado = ""
    if fondos is not None and not fondos.empty and fondos["ultima_descarga"].notna().any():
        actualizado = f" Última actualización: {fondos['ultima_descarga'].max():%d/%m/%Y}."
    st.html(
        '<footer class="kid-pie">Datos extraídos con IA de los documentos de datos fundamentales (KID) que '
        "Bestinver y Azvalor publican en sus webs. Se actualizan el día 15 de cada mes." + e(actualizado) + " "
        "Es información orientativa, no una recomendación de inversión: antes de invertir, lee el KID original "
        "y el folleto del fondo.</footer>"
    )


# ---------------------------------------------------------------------------------------------
# Trazabilidad (ficha) y comprobaciones
# ---------------------------------------------------------------------------------------------

ICONO_NEUTRO = '<i class="kid-icono kid-icono--neutro" aria-hidden="true"></i>'


def valor_campo(campo: str, valor) -> str:
    if valor is None or valor == "":
        return "No figura en el KID"
    if campo == "periodo_mantenimiento_anios":
        return calc.anios(float(valor))
    if campo.endswith("_pct"):
        return calc.pct(float(valor))
    if campo == "fecha_documento":
        return f"{pd.to_datetime(valor):%d/%m/%Y}"
    return str(valor)


def tabla_trazabilidad(detalle: dict) -> str:
    evidencias = detalle.get("evidencias") or {}
    verificadas = detalle.get("verificacion_evidencias") or {}
    filas = []
    for campo, etiqueta in calc.CAMPOS.items():
        cita_campo = evidencias.get(campo)
        if not cita_campo:
            estado = f'<span class="kid-leyenda"><span>{ICONO_NEUTRO}&nbsp;Sin cita</span></span>'
        elif verificadas.get(campo):
            estado = f'<span class="kid-leyenda"><span>{ICONO_OK}&nbsp;Encontrada</span></span>'
        else:
            estado = f'<span class="kid-leyenda"><span>{ICONO_AVISO}&nbsp;No encontrada</span></span>'
        filas.append(
            f"<tr><td>{e(etiqueta)}</td><td><b>{e(valor_campo(campo, detalle.get(campo)))}</b></td>"
            f'<td class="kid-tabla-cita">{"«" + e(cita_campo) + "»" if cita_campo else ""}</td>'
            f"<td>{estado}</td></tr>"
        )
    cabecera = "<tr><th>Dato</th><th>Valor</th><th>Cita del KID</th><th>Cita en el texto</th></tr>"
    return (
        f'<div class="kid-tabla-marco"><table class="kid-tabla kid-tabla--citas"><thead>{cabecera}</thead>'
        f"<tbody>{''.join(filas)}</tbody></table></div>"
    )


def validaciones(v: dict) -> str:
    def linea(icono: str, texto: str) -> str:
        return f'<li><span class="kid-leyenda"><span>{icono}&nbsp;{e(texto)}</span></span></li>'

    elementos = [
        linea(ICONO_OK, "El ISIN es válido: formato y dígito de control correctos")
        if v.get("isin_valido")
        else linea(ICONO_AVISO, "El ISIN no supera la comprobación del dígito de control"),
    ]
    if v.get("isin_coincide_web") is None:
        elementos.append(linea(ICONO_NEUTRO, "La web de la gestora no publica un ISIN único con el que compararlo"))
    elif v["isin_coincide_web"]:
        elementos.append(linea(ICONO_OK, "Coincide con el ISIN publicado en la web de la gestora"))
    else:
        elementos.append(linea(ICONO_AVISO, "No coincide con el ISIN publicado en la web de la gestora"))
    elementos.append(
        linea(ICONO_OK, "El indicador de riesgo está entre 1 y 7")
        if v.get("sri_en_rango")
        else linea(ICONO_AVISO, "El indicador de riesgo está fuera de la escala de 1 a 7")
    )
    return f'<ul class="kid-comprobaciones">{"".join(elementos)}</ul>'


def tabla_versiones(historial: list[dict]) -> str:
    filas = "".join(
        f"<tr><td>{valor_campo('fecha_documento', v.get('fecha_documento'))}</td>"
        f"<td>{mini_escala(int(v['sri']))}</td>"
        f'<td class="n">{calc.pct(v.get("gastos_corrientes_pct"))}</td>'
        f'<td class="n">{pd.to_datetime(v["primera_descarga"]):%d/%m/%Y}</td>'
        f'<td class="n">{pd.to_datetime(v["ultima_descarga"]):%d/%m/%Y}</td>'
        f"<td>{'Vigente' if v.get('actual') else ''}</td></tr>"
        for v in historial
    )
    cabecera = (
        "<tr><th>Fecha del KID</th><th>Riesgo</th><th class='n'>Gastos corrientes</th>"
        "<th class='n'>Primera descarga</th><th class='n'>Última descarga</th><th></th></tr>"
    )
    return (
        f'<div class="kid-tabla-marco"><table class="kid-tabla"><thead>{cabecera}</thead>'
        f"<tbody>{filas}</tbody></table></div>"
    )


def leyenda_estados() -> str:
    return (
        '<div class="kid-leyenda">'
        f'<span><i class="kid-marca" style="background:{VERIFICADO}"></i>Superada</span>'
        f'<span><i class="kid-marca" style="background:{NO_VERIFICADO}"></i>Para revisar</span>'
        f'<span><i class="kid-marca" style="background:{APAGADO}"></i>Sin referencia con la que comparar</span>'
        "</div>"
    )


def tabla_revision(filas: list[dict]) -> str:
    cuerpo = "".join(
        f'<tr><td><a href="{enlace_ficha(f["isin"])}" target="_self">{e(f["fondo"])}</a></td>'
        f"<td>{e(f['campo'])}</td><td><b>{e(f['valor'])}</b></td>"
        f'<td class="kid-tabla-cita">{"«" + e(f["cita"]) + "»" if f["cita"] else ""}</td></tr>'
        for f in filas
    )
    cabecera = "<tr><th>Fondo</th><th>Dato</th><th>Valor extraído</th><th>Cita del KID</th></tr>"
    return (
        f'<div class="kid-tabla-marco"><table class="kid-tabla kid-tabla--citas"><thead>{cabecera}</thead>'
        f"<tbody>{cuerpo}</tbody></table></div>"
    )
