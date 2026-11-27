"""Tests de la aplicación web: cálculos, cliente de la API y ejecución de cada página.

Las páginas se ejecutan con AppTest de Streamlit y la API se sustituye por respuestas simuladas
(con el mismo formato que la API real), así que no hace falta red ni AWS.
"""

import math
from pathlib import Path

import pandas as pd
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

import calculos as calc
import cliente_api
import datos

APP = Path(__file__).resolve().parent.parent / "app" / "kid_app.py"


def fondo(isin, nombre, fuente, sri, plazo, gastos, entrada=0.0, salida=0.0, clase=None, verificacion=None):
    return {
        "isin": isin,
        "nombre_producto": nombre,
        "nombre_clase": clase,
        "gestora": "BESTINVER GESTIÓN" if fuente == "bestinver" else "AZVALOR ASSET MANAGEMENT",
        "fuente": fuente,
        "fecha_documento": "2025-02-14",
        "sri": sri,
        "periodo_mantenimiento_anios": plazo,
        "gastos_corrientes_pct": gastos,
        "costes_entrada_pct": entrada,
        "costes_salida_pct": salida,
        "validaciones": {"isin_valido": True, "isin_coincide_web": True, "sri_en_rango": True},
        "verificacion_evidencias": verificacion or {"isin": True, "sri": True},
        "modelo": "global.moonshotai.kimi-k3.1",
        "ultima_descarga": "2026-11-27T17:37:57",
    }


FONDOS = [
    fondo("ES0114638036", "BESTINVER MONETARIO, F.I.", "bestinver", 1, 0.5, 0.25),
    fondo("ES0114631007", "Bestinver Renta, F.I.", "bestinver", 2, 2, 0.6),
    fondo("ES0112601002", "Azvalor Capital FI", "azvalor", 2, 3, 0.57),
    fondo("ES0114673033", "BESTINFOND, F.I.", "bestinver", 4, 5, 1.76, verificacion={"isin": True, "sri": False}),
    fondo("ES0112611001", "Azvalor Internacional FI", "azvalor", 5, 5, 1.89, salida=None),
    fondo("ES0114633003", "Bestinver Small Caps, F.I.", "bestinver", 5, 7, 1.8, clase="Clase R"),
]


def detalle(isin):
    base = next(f for f in FONDOS if f["isin"] == isin)
    return base | {
        "evidencias": {"isin": f"ISIN: {isin}", "sri": "clase de riesgo en una escala de 7"},
        "fecha_extraccion": "2026-11-27T17:40:00",
        "documento_id": 7,
        "url_origen": "https://example.com/kid.pdf",
        "url_ficha": "https://example.com/fondo",
        "primera_descarga": "2026-11-27T16:29:30",
        "historial": [
            {
                "documento_id": 7,
                "fecha_documento": "2025-02-14",
                "sri": base["sri"],
                "gastos_corrientes_pct": base["gastos_corrientes_pct"],
                "primera_descarga": "2026-11-27T16:29:30",
                "ultima_descarga": "2026-11-27T17:37:57",
                "actual": True,
            }
        ],
    }


RESUMEN = {
    "fondos": 6,
    "documentos": 6,
    "gestoras": 2,
    "ultima_actualizacion": "2026-11-27T17:37:57",
    "distribucion_sri": [{"sri": n, "fondos": sum(f["sri"] == n for f in FONDOS)} for n in range(1, 8)],
    "calidad": {
        "isin_validos": 6,
        "isin_comparables_web": 6,
        "isin_coinciden_web": 6,
        "evidencias_total": 12,
        "evidencias_verificadas": 11,
    },
}


class Respuesta:
    def __init__(self, estado, cuerpo=None, cabeceras=None):
        self.status_code, self.cuerpo, self.headers = estado, cuerpo, cabeceras or {}

    def json(self):
        return self.cuerpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def api_simulada(url, params=None, timeout=None):
    ruta = url.removeprefix("https://api.example")
    if ruta == "/fondos":
        return Respuesta(200, FONDOS)
    if ruta == "/resumen":
        return Respuesta(200, RESUMEN)
    if ruta.startswith("/fondos/"):
        isin = ruta.removeprefix("/fondos/")
        return Respuesta(200, detalle(isin)) if any(f["isin"] == isin for f in FONDOS) else Respuesta(404)
    return Respuesta(404)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("API_URL", "https://api.example/")
    monkeypatch.setattr(cliente_api.requests, "get", api_simulada)
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def textos_html(at: AppTest) -> str:
    return " ".join(h.proto.body for h in at.get("html"))


# ---------------------------------------------------------------------------------------------
# Cálculos y formato
# ---------------------------------------------------------------------------------------------


def test_formato_espanol():
    assert calc.pct(1.8) == "1,8 %"
    assert calc.pct(0.57) == "0,57 %"
    assert calc.pct(2.0) == "2 %"
    assert calc.pct(None) == "sin dato"
    assert calc.eur(1103.4) == "1.103 €"
    assert calc.anios(1) == "1 año"
    assert calc.anios(0.5) == "0,5 años"
    assert calc.num(12345.678, 2) == "12.345,68"


def test_nombre_corto():
    assert calc.nombre_corto("BESTINFOND, F.I.") == "Bestinfond"
    assert calc.nombre_corto("Azvalor Capital FI") == "Azvalor Capital"
    assert calc.nombre_corto("BESTINVER RENTA DE LA CASA, F.I.") == "Bestinver Renta de la Casa"
    assert calc.nombre_corto("Bestinver Small Caps, F.I.", "Clase R") == "Bestinver Small Caps (Clase R)"
    assert calc.nombre_corto("Fondo X, FI", float("nan")) == "Fondo X"
    assert calc.sin_gestora("Bestinver Bolsa", "Bestinver") == "Bolsa"
    assert calc.sin_gestora("Bestinfond", "Bestinver") == "Bestinfond"


def test_impacto_costes_sin_rentabilidad():
    r = calc.impacto_costes(10_000, 5, 1.8, 0, 0)
    assert r["valor_con_costes"] == pytest.approx(10_000 * 0.982**5)
    assert r["impacto"] == pytest.approx(10_000 - 10_000 * 0.982**5)
    # Sin rentabilidad, la incidencia anual coincide con los gastos corrientes
    assert r["incidencia_anual_pct"] == pytest.approx(1.8)


def test_impacto_costes_con_entrada_salida_y_rentabilidad():
    r = calc.impacto_costes(10_000, 3, 1.0, 2.0, 1.0, rentabilidad_pct=5)
    esperado = 10_000 * 0.98 * (1.05 * 0.99) ** 3 * 0.99
    assert r["valor_con_costes"] == pytest.approx(esperado)
    assert r["valor_sin_costes"] == pytest.approx(10_000 * 1.05**3)
    assert r["incidencia_anual_pct"] == pytest.approx((1.05 - (esperado / 10_000) ** (1 / 3)) * 100)
    # Comisiones no indicadas en el KID cuentan como cero
    assert calc.impacto_costes(10_000, 3, 1.0, None, math.nan)["impacto"] == pytest.approx(
        calc.impacto_costes(10_000, 3, 1.0, 0, 0)["impacto"]
    )


def test_tabla_impacto_ordena_y_excluye_sin_datos():
    fondos = datos.preparar_fondos(FONDOS + [fondo("ES0000000001", "Sin gastos FI", "azvalor", 3, 3, None)])
    tabla = calc.tabla_impacto(fondos, 10_000, 0, plazo_fijo=5)
    assert len(tabla) == len(FONDOS)
    assert tabla["impacto"].is_monotonic_decreasing
    assert set(tabla["plazo"]) == {5}
    # Con el plazo recomendado, cada fondo usa el suyo
    assert calc.tabla_impacto(fondos, 10_000, 0).set_index("isin").loc["ES0114638036", "plazo"] == 0.5


def test_correlacion_de_spearman():
    datos_ = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [10, 20, 30, 40, 50]})
    assert calc.correlacion(datos_, "x", "y") == (pytest.approx(1.0), 5)
    datos_["y"] = [5, 4, 3, 2, 1]
    assert calc.correlacion(datos_, "x", "y")[0] == pytest.approx(-1.0)
    assert calc.correlacion(datos_.head(3), "x", "y") == (None, 3)


def test_frases_a_partir_de_los_datos():
    fondos = datos.preparar_fondos(FONDOS)
    assert calc.frase_escala(fondos) == (
        "Los 6 fondos van del riesgo 1 al 5; el nivel más habitual es el 2, con 2 fondos."
    )
    assert calc.frase_riesgo_coste(fondos).startswith("A más riesgo, más gastos")
    assert "Spearman" in calc.frase_horizonte(fondos)
    assert calc.posicion_en_nivel(fondos, "ES0112601002").startswith(
        "De los 2 fondos con riesgo 2, es el de menores gastos corrientes"
    )


def test_proxima_ejecucion():
    antes = calc.proxima_ejecucion(pd.Timestamp("2026-11-27 12:00", tz="Europe/Madrid"))
    assert antes == pd.Timestamp("2026-12-15 09:00", tz="Europe/Madrid")
    assert calc.proxima_ejecucion(pd.Timestamp("2026-12-03", tz="Europe/Madrid")).day == 15
    assert calc.proxima_ejecucion(pd.Timestamp("2026-12-03", tz="Europe/Madrid")).month == 12


def test_citas_no_encontradas():
    assert calc.citas_no_encontradas(datos.preparar_fondos(FONDOS)) == [("ES0114673033", "sri")]


# ---------------------------------------------------------------------------------------------
# Cliente de la API
# ---------------------------------------------------------------------------------------------


def test_cliente_reintenta_mientras_la_base_de_datos_se_reanuda(monkeypatch):
    monkeypatch.setenv("API_URL", "https://api.example")
    respuestas = [Respuesta(503, cabeceras={"Retry-After": "30"}), Respuesta(200, [1, 2])]
    monkeypatch.setattr(cliente_api.requests, "get", lambda *a, **k: respuestas.pop(0))
    monkeypatch.setattr(cliente_api.time, "sleep", lambda s: None)
    assert cliente_api.pedir("/fondos") == [1, 2]


def test_cliente_avisa_si_la_api_no_responde(monkeypatch):
    monkeypatch.setenv("API_URL", "https://api.example")

    def sin_conexion(*a, **k):
        raise requests.ConnectionError("sin red")

    monkeypatch.setattr(cliente_api.requests, "get", sin_conexion)
    monkeypatch.setattr(cliente_api.time, "sleep", lambda s: None)
    with pytest.raises(cliente_api.ApiNoDisponible):
        cliente_api.pedir("/fondos")
    monkeypatch.delenv("API_URL")
    with pytest.raises(cliente_api.ApiNoDisponible):
        cliente_api.url_api("/fondos")


# ---------------------------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------------------------


def ejecutar(pagina: str | None = None, **query) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=30)
    for clave, valor in query.items():
        at.query_params[clave] = valor
    at.run()
    if pagina:
        at.switch_page(pagina).run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def test_panorama(api):
    at = ejecutar()
    html = textos_html(at)
    assert "¿Cuánto riesgo declara cada fondo?" in html
    assert "Los 6 fondos van del riesgo 1 al 5" in html
    # La escalera enlaza cada fondo con su ficha y muestra los siete niveles
    assert html.count('href="ficha?isin=') == len(FONDOS)
    assert html.count("<p>Ningún fondo</p>") == 3  # niveles 3, 6 y 7


def test_buscador_filtra_por_riesgo_y_texto(api):
    at = ejecutar("paginas/buscador.py")
    assert "6 de 6 fondos cumplen estos criterios" in textos_html(at)
    at.select_slider[0].set_value((4, 7)).run()
    assert "3 de 6 fondos cumplen estos criterios" in textos_html(at)
    at.text_input[0].input("internacional").run()
    assert "1 de 6 fondos cumplen estos criterios" in textos_html(at)
    at.text_input[0].input("ningun fondo asi").run()
    assert "Ningún fondo cumple" in textos_html(at)


def test_costes(api):
    at = ejecutar("paginas/costes.py")
    assert "Invirtiendo 10.000 € durante 5 años y sin rentabilidad" in textos_html(at)
    at.radio[0].set_value("El recomendado en cada KID").run()
    assert "durante el periodo recomendado de cada fondo" in textos_html(at)


def test_ficha_desde_la_url(api):
    at = ejecutar("paginas/ficha.py", isin="ES0114673033")
    html = textos_html(at)
    assert "Bestinfond" in html
    assert "Indicador de riesgo 4 de 7" in html
    assert "Cita no encontrada literalmente" in html  # la cita del SRI de este fondo no se verificó
    assert at.link_button[0].proto.url == "https://api.example/fondos/ES0114673033/kid"


def test_fiabilidad(api):
    at = ejecutar("paginas/fiabilidad.py")
    html = textos_html(at)
    assert "De 12 citas, 11 aparecen literalmente" in html
    assert "Bestinfond" in html  # su cita pendiente de revisar


def test_api_caida_muestra_un_aviso(monkeypatch):
    monkeypatch.setenv("API_URL", "https://api.example")
    monkeypatch.setattr(cliente_api.requests, "get", lambda *a, **k: Respuesta(503))
    monkeypatch.setattr(cliente_api.time, "sleep", lambda s: None)
    st.cache_data.clear()
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert "No se han podido cargar los datos" in at.error[0].value
