"""Tests de las utilidades de navegación: ISIN, normalización y robots.txt."""

import pytest

from common.validaciones import isin_valido
from utilidades_web import Robots, codificacion_html, isin_unico, normalizar

ROBOTS_BESTINVER = """
User-agent: *
User-agent: Googlebot
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php
Disallow: /xmlrpc.php
Disallow: /*.pdf$
Allow: /*.css$

User-agent: HTTrack
Disallow: /
"""


@pytest.mark.parametrize("isin", ["ES0114673033", "ES0112611001", "US0378331005", "IE00B4L5Y983"])
def test_isin_valido(isin):
    assert isin_valido(isin)


@pytest.mark.parametrize("isin", ["ES0114673034", "ES011467303", "es0114673033", "", None])
def test_isin_no_valido(isin):
    assert not isin_valido(isin)


def test_isin_unico():
    assert isin_unico("Fondo X. ISIN: ES0114673033. Gestora...") == "ES0114673033"
    # Repetido: sigue siendo uno solo
    assert isin_unico("ES0114673033 ... ES0114673033") == "ES0114673033"
    # Dos ISIN distintos (varias clases): ambiguo
    assert isin_unico("ES0114673033 y ES0112611001") is None
    # Cadena con forma de ISIN pero dígito de control incorrecto: se ignora
    assert isin_unico("ABCDEFGHIJK1") is None


def test_normalizar():
    assert normalizar("  Folleto   Simplificado (DFP) ") == "folleto simplificado (dfp)"
    assert normalizar("Saber Más") == "saber mas"


def test_robots_grupo_compartido_y_otros_agentes():
    reglas = Robots.parsear(ROBOTS_BESTINVER)
    # Las reglas del grupo "*" (compartido con Googlebot) sí; las de HTTrack no
    assert ("disallow", "/*.pdf$") in reglas
    assert ("disallow", "/") not in reglas


def test_robots_comodines():
    robots = Robots(Robots.parsear(ROBOTS_BESTINVER))
    assert not robots.permite("https://www.bestinver.es/wp-admin/opciones.php")
    assert robots.permite("https://www.bestinver.es/wp-admin/admin-ajax.php")
    assert not robots.permite("https://www.bestinver.es/wp-content/uploads/kid.pdf")
    # "$" ancla el final de la URL: con parámetros ya no coincide
    assert robots.permite("https://www.bestinver.es/wp-content/uploads/kid.pdf?h=123")
    assert robots.permite("https://www.bestinver.es/fondos-de-inversion/bestinfond/")


def test_robots_sin_reglas_permite_todo():
    assert Robots([]).permite("https://www.ejemplo.com/cualquier/cosa.pdf")


class RespuestaFalsa:
    def __init__(self, encoding, apparent_encoding="utf-8"):
        self.encoding, self.apparent_encoding = encoding, apparent_encoding


def test_codificacion_html():
    # Cabecera con charset: se respeta
    assert codificacion_html(RespuestaFalsa("utf-8")) == "utf-8"
    # Sin charset, requests asigna ISO-8859-1 por defecto: se usa la detectada en el contenido
    assert codificacion_html(RespuestaFalsa("ISO-8859-1", "utf-8")) == "utf-8"
    assert codificacion_html(RespuestaFalsa(None, "utf-8")) == "utf-8"
