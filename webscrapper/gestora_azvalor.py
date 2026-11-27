"""Azvalor: localización de los KID ("Folleto simplificado (DFP)") publicados en su web.

Cómo es la web:
1. En https://www.azvalor.com/fondos/ el menú y el cuerpo enlazan las fichas de los fondos de
   inversión, con URL /fondos-de-inversion/<slug>/ (los planes de pensiones y las SICAV tienen
   otras rutas y otro tipo de documento, y quedan fuera del alcance).
2. En cada ficha, el KID es el enlace "Folleto simplificado (DFP)". El nombre del PDF incluye la
   fecha del documento (p. ej. DFP-Internacional-09.01.2026.pdf), así que la URL no se puede
   construir: hay que leerla del HTML en cada ejecución. La ficha publica también el ISIN.

Las páginas son HTML estático: basta con requests + lxml.
"""

import re
from urllib.parse import urljoin, urlparse

import requests

from utilidades_web import DocumentoKID, Navegador, isin_unico, normalizar

NOMBRE = "azvalor"
URL_LISTADO = "https://www.azvalor.com/fondos/"

PATRON_FICHA = re.compile(r"^/fondos-de-inversion/([^/]+)/?$")
# Textos (normalizados) con los que la web enlaza el KID
TEXTOS_KID = ("folleto simplificado", "datos fundamentales")
# Textos genéricos de enlace que no sirven como nombre del fondo
TEXTOS_GENERICOS = {"", "saber mas", "ver mas", "mas informacion"}


def _es_azvalor(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == "azvalor.com" or host.endswith(".azvalor.com")


def _fichas(nav: Navegador) -> list[tuple[str, str, str]]:
    """[(slug, nombre, url)] de las fichas de fondos de inversión enlazadas en el listado."""
    arbol = nav.arbol(URL_LISTADO)
    fichas: dict[str, tuple[str, str]] = {}
    for a in arbol.xpath("//a[@href]"):
        url = urljoin(URL_LISTADO, a.get("href"))
        coincidencia = PATRON_FICHA.match(urlparse(url).path)
        if not (_es_azvalor(url) and coincidencia):
            continue
        slug = coincidencia.group(1)
        nombre = " ".join(a.text_content().split())
        anterior = fichas.get(slug)
        # Se conserva el primer texto que sea un nombre de fondo, no un "Saber más"
        mejora_nombre = anterior is not None and (
            normalizar(anterior[0]) in TEXTOS_GENERICOS and normalizar(nombre) not in TEXTOS_GENERICOS
        )
        if anterior is None or mejora_nombre:
            fichas[slug] = (nombre, url)
    return [(slug, nombre, url) for slug, (nombre, url) in fichas.items()]


def localizar_kids(nav: Navegador) -> tuple[list[DocumentoKID], list[dict]]:
    """KID publicados en la web y lista de incidencias (fichas sin KID o inaccesibles)."""
    fichas = _fichas(nav)
    if not fichas:
        print("[aviso] Azvalor: el listado no enlaza ninguna ficha /fondos-de-inversion/<slug>/")
    print(f"Azvalor: {len(fichas)} fichas de fondos de inversión en el listado")

    kids, incidencias = [], []
    for slug, nombre, url in fichas:
        try:
            arbol = nav.arbol(url)
        except (requests.RequestException, PermissionError) as e:
            incidencias.append({"fondo": nombre or slug, "url": url, "detalle": f"ficha inaccesible: {e}"})
            continue

        if normalizar(nombre) in TEXTOS_GENERICOS:
            titulos = [" ".join(h.text_content().split()) for h in arbol.xpath("//h1")]
            nombre = next((t for t in titulos if t), slug)

        url_kid = next(
            (
                urljoin(url, a.get("href"))
                for a in arbol.xpath("//a[@href]")
                if any(t in normalizar(a.text_content()) for t in TEXTOS_KID) and ".pdf" in a.get("href").lower()
            ),
            None,
        )
        if not url_kid:
            incidencias.append({"fondo": nombre, "url": url, "detalle": "la ficha no publica KID"})
            continue

        kids.append(
            DocumentoKID(
                gestora=NOMBRE,
                fondo=nombre,
                slug=slug,
                url_ficha=url,
                url_origen=url_kid,
                isin_web=isin_unico(arbol.text_content()),
            )
        )
    return kids, incidencias
