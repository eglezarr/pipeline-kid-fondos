"""Capturas de pantalla de cada página de la aplicación desplegada (Playwright con Chromium).

Sirven para revisar el diseño con los datos reales y para la documentación y la presentación.

Uso: python scripts/capturar_app.py https://<url-de-la-app> capturas/
"""

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

ANCHOS = {"escritorio": 1440, "movil": 390}


async def capturar(url: str, destino: Path, isin: str | None) -> None:
    rutas = {"panorama": "/", "buscador": "/buscador", "costes": "/costes", "fiabilidad": "/fiabilidad"}
    if isin:
        rutas["ficha"] = f"/ficha?isin={isin}"
    destino.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        navegador = await p.chromium.launch()
        for dispositivo, ancho in ANCHOS.items():
            pagina = await navegador.new_page(viewport={"width": ancho, "height": 900})
            for nombre, ruta in rutas.items():
                await pagina.goto(url + ruta, wait_until="networkidle", timeout=120_000)
                # La primera visita puede esperar a que la base de datos se reanude
                await pagina.wait_for_selector(".kid-pregunta", timeout=120_000)
                await pagina.wait_for_timeout(4000)  # gráficos y tipografía
                # Streamlit desplaza un contenedor interno: se amplía la ventana a la altura del contenido
                alto = await pagina.evaluate("document.querySelector('[data-testid=stMain]').scrollHeight")
                await pagina.set_viewport_size({"width": ancho, "height": min(alto + 40, 12000)})
                await pagina.wait_for_timeout(1500)
                fichero = destino / f"{nombre}_{dispositivo}.png"
                await pagina.screenshot(path=fichero, full_page=True)
                await pagina.set_viewport_size({"width": ancho, "height": 900})
                print(f"{fichero}  ({ancho} px)")
            await pagina.close()
        await navegador.close()


def primer_isin(url_api: str | None) -> str | None:
    """ISIN del primer fondo de la API, para capturar una ficha real."""
    if not url_api:
        return None
    with urllib.request.urlopen(f"{url_api.rstrip('/')}/fondos?orden=sri", timeout=90) as respuesta:
        fondos = json.load(respuesta)
    return fondos[len(fondos) // 2]["isin"] if fondos else None


if __name__ == "__main__":
    url_app, carpeta = sys.argv[1].rstrip("/"), Path(sys.argv[2])
    asyncio.run(capturar(url_app, carpeta, primer_isin(sys.argv[3] if len(sys.argv) > 3 else None)))
