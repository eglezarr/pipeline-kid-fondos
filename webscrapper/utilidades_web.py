"""Utilidades de navegación responsable, comunes a los scrapers de todas las gestoras.

- `Navegador`: sesión HTTP con User-Agent de navegador, pausa entre peticiones y comprobación
  de robots.txt antes de cada petición.
- `Robots`: reglas de robots.txt del grupo `User-agent: *`, con los comodines `*` y `$`
  (la librería estándar `urllib.robotparser` no los interpreta).
- `DocumentoKID`: un KID localizado en la web de una gestora, antes de descargarlo.
- ISIN publicado en una página (con dígito de control válido) y normalización de textos.
"""

import re
import time
import unicodedata
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from lxml import html

from common.validaciones import isin_valido

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}

PATRON_ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")


@dataclass
class DocumentoKID:
    """KID localizado en la web de una gestora (todavía sin descargar)."""

    gestora: str
    fondo: str  # nombre del fondo tal y como aparece en la web
    slug: str  # identificador del fondo en la URL de su ficha; da nombre al fichero
    url_ficha: str  # página del fondo donde está publicado el enlace
    url_origen: str  # enlace al PDF del KID
    isin_web: str | None = None  # ISIN publicado en la ficha, si hay uno solo


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados (para comparar textos de enlaces)."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


def codificacion_html(resp: requests.Response) -> str:
    """Codificación con la que leer una página HTML.

    requests asigna ISO-8859-1 por defecto cuando la cabecera Content-Type no indica charset;
    en ese caso (o si no hay ninguna) se usa la codificación detectada en el propio contenido.
    """
    declarada = (resp.encoding or "").lower()
    if declarada and declarada != "iso-8859-1":
        return resp.encoding
    return resp.apparent_encoding or "utf-8"


def isin_unico(texto: str) -> str | None:
    """ISIN válido presente en el texto, si hay exactamente uno distinto; si no, None."""
    candidatos = {c for c in PATRON_ISIN.findall(texto) if isin_valido(c)}
    return candidatos.pop() if len(candidatos) == 1 else None


class Robots:
    """Reglas de robots.txt aplicables a cualquier agente (grupo `User-agent: *`)."""

    def __init__(self, reglas: list[tuple[str, str]]):
        self.reglas = reglas  # [("allow" | "disallow", patrón)]

    @staticmethod
    def parsear(texto: str) -> list[tuple[str, str]]:
        """Reglas Allow/Disallow de los grupos cuyo User-agent incluye '*'."""
        reglas, agentes, leyendo_reglas = [], [], False
        for linea in texto.splitlines():
            linea = linea.split("#", 1)[0].strip()
            if ":" not in linea:
                continue
            campo, valor = (parte.strip() for parte in linea.split(":", 1))
            campo = campo.lower()
            if campo == "user-agent":
                if leyendo_reglas:  # empieza un grupo nuevo
                    agentes, leyendo_reglas = [], False
                agentes.append(valor)
            elif campo in ("allow", "disallow"):
                leyendo_reglas = True
                if "*" in agentes and valor:
                    reglas.append((campo, valor))
        return reglas

    @staticmethod
    def _coincide(patron: str, ruta: str) -> bool:
        """El patrón admite '*' (cualquier secuencia) y '$' final (fin de la URL)."""
        expresion = re.escape(patron).replace(r"\*", ".*")
        if expresion.endswith(r"\$"):
            expresion = expresion[:-2] + "$"
        return re.match(expresion, ruta) is not None

    def permite(self, url: str) -> bool:
        """Aplica la regla más específica (patrón más largo); a igualdad, gana Allow."""
        partes = urlparse(url)
        ruta = (partes.path or "/") + (f"?{partes.query}" if partes.query else "")
        mejor = None
        for tipo, patron in self.reglas:
            if self._coincide(patron, ruta):
                candidata = (len(patron), tipo == "allow")
                if mejor is None or candidata > mejor:
                    mejor = candidata
        return True if mejor is None else mejor[1]


class Navegador:
    """Sesión HTTP responsable: User-Agent de navegador, pausa entre peticiones y robots.txt."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.sesion = requests.Session()
        self.sesion.headers.update(CABECERAS)
        self._robots: dict[str, Robots] = {}
        self._ultima_peticion = 0.0

    def _esperar(self) -> None:
        pausa = self.delay - (time.monotonic() - self._ultima_peticion)
        if pausa > 0:
            time.sleep(pausa)
        self._ultima_peticion = time.monotonic()

    def robots(self, url: str) -> Robots:
        """Reglas de robots.txt del sitio de la URL (se descargan una vez por sitio)."""
        partes = urlparse(url)
        sitio = f"{partes.scheme}://{partes.netloc}"
        if sitio not in self._robots:
            self._esperar()
            try:
                resp = self.sesion.get(urljoin(sitio, "/robots.txt"), timeout=15)
            except requests.RequestException as e:
                print(f"[aviso] no se pudo leer {sitio}/robots.txt ({e}); se continúa sin restricciones")
                reglas = []
            else:
                if resp.status_code >= 500:
                    # Servidor con errores: se interpreta de forma conservadora (todo prohibido)
                    print(f"[aviso] {sitio}/robots.txt devolvió {resp.status_code}; no se accede al sitio")
                    reglas = [("disallow", "/")]
                elif resp.status_code >= 400:
                    reglas = []  # no existe robots.txt: no hay restricciones
                else:
                    reglas = Robots.parsear(resp.text)
            self._robots[sitio] = Robots(reglas)
        return self._robots[sitio]

    def obtener(self, url: str, timeout: int = 30) -> requests.Response:
        """GET respetando robots.txt y la pausa entre peticiones."""
        if not self.robots(url).permite(url):
            raise PermissionError(f"robots.txt no permite acceder a {url}")
        self._esperar()
        resp = self.sesion.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp

    def arbol(self, url: str) -> html.HtmlElement:
        """Página HTML parseada con lxml, con la codificación correcta (acentos y eñes)."""
        resp = self.obtener(url)
        return html.fromstring(resp.content, parser=html.HTMLParser(encoding=codificacion_html(resp)))

    def descargar_pdf(self, url: str) -> bytes:
        """Descarga un PDF y comprueba que lo es (algunas webs devuelven HTML de error)."""
        contenido = self.obtener(url, timeout=60).content
        if not contenido.startswith(b"%PDF"):
            raise ValueError("la respuesta no es un PDF")
        return contenido
