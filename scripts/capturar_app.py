"""Capturas de pantalla de cada página de la aplicación desplegada (Playwright con Chromium).

Sirven para revisar el diseño con los datos reales y para la documentación y la presentación.
También comprueba que ninguna página muestra errores y escribe en el log el titular de cada una.

Uso: python scripts/capturar_app.py https://<url-de-la-app> capturas/
"""

import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

ANCHOS = {"escritorio": 1440, "movil": 390}


async def revisar(pagina, nombre: str) -> int:
    """Muestra el titular y la primera frase de la página, y cuenta los errores visibles."""
    titular = await pagina.locator(".kid-pregunta").first.inner_text()
    respuestas = pagina.locator(".kid-respuesta")
    frase = await respuestas.first.inner_text() if await respuestas.count() else ""
    errores = await pagina.locator('[data-testid="stException"], [data-testid="stAlertContentError"]').count()
    graficos = await pagina.locator('[data-testid="stVegaLiteChart"]').count()
    print(f"[{nombre}] {titular} | {frase[:160]} | gráficos: {graficos} | errores: {errores}")
    return errores


async def capturar(url: str, destino: Path, isin: str | None) -> int:
    rutas = {"panorama": "/", "buscador": "/buscador", "costes": "/costes", "fiabilidad": "/fiabilidad"}
    if isin:
        rutas["ficha"] = f"/ficha?isin={isin}"
    destino.mkdir(parents=True, exist_ok=True)
    errores = 0
    async with async_playwright() as p:
        # CHROME_PATH (opcional): usar un Chrome ya instalado en lugar del Chromium de Playwright
        navegador = await p.chromium.launch(executable_path=os.environ.get("CHROME_PATH"))
        for dispositivo, ancho in ANCHOS.items():
            pagina = await navegador.new_page(viewport={"width": ancho, "height": 900})
            for nombre, ruta in rutas.items():
                await pagina.goto(url + ruta, wait_until="networkidle", timeout=120_000)
                # La primera visita puede esperar a que la base de datos se reanude
                await pagina.wait_for_selector(".kid-pregunta", timeout=120_000)
                await pagina.wait_for_timeout(4000)  # gráficos y tipografía
                if dispositivo == "escritorio":
                    errores += await revisar(pagina, nombre)
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
    return errores


def primer_isin(url_api: str | None) -> str | None:
    """ISIN del primer fondo de la API, para capturar una ficha real."""
    if not url_api:
        return None
    with urllib.request.urlopen(f"{url_api.rstrip('/')}/fondos?orden=sri", timeout=90) as respuesta:
        fondos = json.load(respuesta)
    return fondos[len(fondos) // 2]["isin"] if fondos else None


if __name__ == "__main__":
    url_app, carpeta = sys.argv[1].rstrip("/"), Path(sys.argv[2])
    total = asyncio.run(capturar(url_app, carpeta, primer_isin(sys.argv[3] if len(sys.argv) > 3 else None)))
    sys.exit(1 if total else 0)  # el workflow falla si alguna página muestra un error
