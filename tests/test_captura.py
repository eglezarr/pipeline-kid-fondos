"""Tests de la captura con webs simuladas: localización de KID por gestora, manifiesto y S3."""

import hashlib
import json

import pytest
from lxml import html

import captura
import gestora_azvalor
import gestora_bestinver
from common import almacenamiento_s3 as alm

PDF = b"%PDF-1.7 contenido de prueba"


class NavegadorFalso:
    """Sustituye a utilidades_web.Navegador: sirve páginas y PDF desde diccionarios."""

    def __init__(self, paginas: dict[str, str], pdfs: dict[str, bytes]):
        self.paginas, self.pdfs = paginas, pdfs

    def arbol(self, url):
        if url not in self.paginas:
            raise PermissionError(f"página no simulada: {url}")
        return html.fromstring(self.paginas[url])

    def descargar_pdf(self, url):
        contenido = self.pdfs.get(url)
        if contenido is None or not contenido.startswith(b"%PDF"):
            raise ValueError("la respuesta no es un PDF")
        return contenido


WEB_BESTINVER = {
    gestora_bestinver.URL_LISTADO: """
        <html><body><footer><ul>
          <li><a href="/fondos-de-inversion/bestinfond/">Bestinfond</a></li>
          <li><a href="/fondos-de-inversion/otros/">Otros</a></li>
          <li><a href="/contacto/">Contacto</a></li>
        </ul></footer></body></html>""",
    "https://www.bestinver.es/fondos-de-inversion/bestinfond/": """
        <html><body><main>
          <p>ISIN: ES0114673033</p>
          <a href="/wp-content/uploads/bestinfond_fi_datos_fundamentales.pdf?h=1">Datos fundamentales</a>
          <a href="/wp-content/uploads/bestinfond_fi_ficha_fondo.pdf?h=2">Ficha del Fondo</a>
        </main></body></html>""",
    "https://www.bestinver.es/fondos-de-inversion/otros/": "<html><body><main>Sin documentos</main></body></html>",
}

WEB_AZVALOR = {
    gestora_azvalor.URL_LISTADO: """
        <html><body>
          <a href="https://www.azvalor.com/fondos-de-inversion/azvalor-internacional/">Saber Más</a>
          <a href="https://www.azvalor.com/fondos-de-inversion/azvalor-internacional/">Azvalor Internacional FI</a>
          <a href="https://www.azvalor.com/fondos-de-pensiones/global-value-fp/">Azvalor Global Value FP</a>
        </body></html>""",
    "https://www.azvalor.com/fondos-de-inversion/azvalor-internacional/": """
        <html><body><h1>Azvalor Internacional</h1><p>ISIN ES0112611001</p>
          <a href="https://www.azvalor.com/wp-content/uploads/2026/06/Folleto-completo.pdf">Folleto completo</a>
          <a href="https://www.azvalor.com/wp-content/uploads/2026/01/DFP-Internacional-09.01.2026.pdf">
            Folleto simplificado (DFP)</a>
        </body></html>""",
}


def test_localizar_kids_bestinver():
    kids, incidencias = gestora_bestinver.localizar_kids(NavegadorFalso(WEB_BESTINVER, {}))
    assert [k.slug for k in kids] == ["bestinfond"]
    kid = kids[0]
    assert kid.url_origen.endswith("bestinfond_fi_datos_fundamentales.pdf?h=1")
    assert kid.isin_web == "ES0114673033"
    # "Otros" no publica KID: es una incidencia, no un fallo; "Contacto" no es una ficha
    assert [i["fondo"] for i in incidencias] == ["Otros"]


def test_localizar_kids_azvalor():
    kids, incidencias = gestora_azvalor.localizar_kids(NavegadorFalso(WEB_AZVALOR, {}))
    assert len(kids) == 1 and not incidencias
    kid = kids[0]
    # El nombre útil prevalece sobre "Saber Más"; los planes de pensiones quedan fuera
    assert kid.fondo == "Azvalor Internacional FI"
    assert kid.slug == "azvalor-internacional"
    assert kid.url_origen.endswith("DFP-Internacional-09.01.2026.pdf")
    assert kid.isin_web == "ES0112611001"


@pytest.fixture
def s3_simulado(monkeypatch):
    """Sustituye el acceso a S3 por un diccionario {clave: (contenido, content_type, metadatos)}."""
    objetos = {}
    monkeypatch.setattr(alm, "conectar", lambda bucket: object())

    def escribir(s3, bucket, clave, contenido, tipo, metadatos=None):
        objetos[clave] = (contenido, tipo, metadatos)

    monkeypatch.setattr(alm, "escribir", escribir)
    return objetos


def test_capturar_sube_pdf_y_manifiesto(s3_simulado):
    url_kid = "https://www.bestinver.es/wp-content/uploads/bestinfond_fi_datos_fundamentales.pdf?h=1"
    nav = NavegadorFalso(WEB_BESTINVER, {url_kid: PDF})

    resumen = captura.capturar("bestinver", bucket="bucket-prueba", fecha="20261127", navegador=nav)

    clave_pdf = "download/bestinver/20261127/bestinfond_datos_fundamentales.pdf"
    assert resumen["claves"] == [clave_pdf]
    assert s3_simulado[clave_pdf][0] == PDF
    assert s3_simulado[clave_pdf][2]["sha256"] == hashlib.sha256(PDF).hexdigest()

    manifiesto = json.loads(s3_simulado["download/bestinver/20261127/manifiesto.json"][0])
    documento = manifiesto["documentos"][0]
    assert documento["url_origen"] == url_kid
    assert documento["isin_web"] == "ES0114673033"
    assert documento["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert documento["tamano_bytes"] == len(PDF)
    assert documento["fecha_descarga"].endswith("Z")


def test_capturar_sin_kids_falla_pero_guarda_manifiesto(s3_simulado):
    # El enlace devuelve HTML en lugar de un PDF: no se guarda nada y la etapa falla
    url_kid = "https://www.bestinver.es/wp-content/uploads/bestinfond_fi_datos_fundamentales.pdf?h=1"
    nav = NavegadorFalso(WEB_BESTINVER, {url_kid: b"<html>error</html>"})

    with pytest.raises(alm.ErrorEtapa):
        captura.capturar("bestinver", bucket="bucket-prueba", fecha="20261127", navegador=nav)

    manifiesto = json.loads(s3_simulado["download/bestinver/20261127/manifiesto.json"][0])
    assert manifiesto["documentos"] == [] and len(manifiesto["fallos"]) == 1


def test_capturar_gestora_desconocida():
    with pytest.raises(ValueError):
        captura.capturar("otra", bucket="bucket-prueba")
