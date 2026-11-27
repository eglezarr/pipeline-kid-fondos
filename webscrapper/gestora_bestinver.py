"""Bestinver: localización de los KID ("Datos fundamentales") publicados en su web.

Cómo es la web:
1. En https://www.bestinver.es/fondos-de-inversion/ el pie de página contiene la lista de todos
   los productos (XPATH_LISTA_FONDOS). Cada enlace lleva a la ficha /fondos-de-inversion/<slug>/.
2. En cada ficha hay una lista de documentos (XPATH_LISTA_DOCUMENTOS): el KID es el enlace cuyo
   texto es "Datos fundamentales" y apunta a un PDF en /wp-content/uploads/. La ficha publica
   también el ISIN del fondo.

Las páginas son HTML estático: basta con requests + lxml. Si un XPath deja de encontrar nada
(cambio de maquetación), se usa un selector más general y se avisa por consola.
"""

from urllib.parse import urljoin, urlparse

import requests

from utilidades_web import DocumentoKID, Navegador, isin_unico, normalizar

NOMBRE = "bestinver"
URL_LISTADO = "https://www.bestinver.es/fondos-de-inversion/"

XPATH_LISTA_FONDOS = "/html/body/div[1]/footer/div[2]/div/div[1]/div/ul"
XPATH_LISTA_DOCUMENTOS = "/html/body/div[1]/div/main/section[4]/div[1]/div[2]/ul"
TEXTO_KID = "datos fundamentales"


def _slug(url: str) -> str:
    return [p for p in urlparse(url).path.split("/") if p][-1]


def _fichas(nav: Navegador) -> list[tuple[str, str]]:
    """[(nombre, url)] de las fichas de fondos listadas en el pie de página."""
    arbol = nav.arbol(URL_LISTADO)
    listas = arbol.xpath(XPATH_LISTA_FONDOS)
    if listas:
        enlaces = listas[0].xpath(".//a[@href]")
    else:
        print("[aviso] XPath de la lista de fondos no encontrado, se usa el selector de respaldo")
        enlaces = arbol.xpath("//footer//a[contains(@href, '/fondos-de-inversion/')]")

    fichas, vistas = [], set()
    for a in enlaces:
        url = urljoin(URL_LISTADO, a.get("href"))
        partes = [p for p in urlparse(url).path.split("/") if p]
        # Solo fichas concretas: /fondos-de-inversion/<slug>/
        if len(partes) != 2 or partes[0] != "fondos-de-inversion" or url in vistas:
            continue
        vistas.add(url)
        fichas.append((" ".join(a.text_content().split()), url))
    return fichas


def localizar_kids(nav: Navegador) -> tuple[list[DocumentoKID], list[dict]]:
    """KID publicados en la web y lista de incidencias (fichas sin KID o inaccesibles)."""
    fichas = _fichas(nav)
    print(f"Bestinver: {len(fichas)} fichas de fondos en el listado")

    kids, incidencias = [], []
    for nombre, url in fichas:
        try:
            arbol = nav.arbol(url)
        except (requests.RequestException, PermissionError) as e:
            incidencias.append({"fondo": nombre, "url": url, "detalle": f"ficha inaccesible: {e}"})
            continue

        listas = arbol.xpath(XPATH_LISTA_DOCUMENTOS)
        if listas:
            enlaces = listas[0].xpath(".//a[@href]")
        else:
            print(f"[aviso] {nombre}: XPath de documentos no encontrado, se usa el selector de respaldo")
            enlaces = arbol.xpath("//main//a[contains(@href, '.pdf')]")

        url_kid = next(
            (urljoin(url, a.get("href")) for a in enlaces if normalizar(a.text_content()) == TEXTO_KID),
            None,
        )
        if not url_kid:
            incidencias.append({"fondo": nombre, "url": url, "detalle": "la ficha no publica KID"})
            continue

        kids.append(
            DocumentoKID(
                gestora=NOMBRE,
                fondo=nombre,
                slug=_slug(url),
                url_ficha=url,
                url_origen=url_kid,
                isin_web=isin_unico(arbol.text_content()),
            )
        )
    return kids, incidencias
