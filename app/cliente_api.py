"""Cliente HTTP de la API de KIDs. La aplicación solo accede a los datos a través de la API.

La URL de la API llega en la variable de entorno API_URL (la define Terraform).
Si Aurora está en pausa, la API responde 503 mientras se reanuda: se espera y se reintenta.
"""

import os
import time

import requests

TIEMPO_MAXIMO = 70  # segundos por petición: la API puede tardar ~40 s si Aurora se reanuda
INTENTOS = 4


class ApiNoDisponible(RuntimeError):
    """La API no responde o la base de datos sigue sin estar disponible tras los reintentos."""


def url_api(ruta: str = "") -> str:
    base = os.environ.get("API_URL", "").rstrip("/")
    if not base:
        raise ApiNoDisponible("falta la variable de entorno API_URL con la dirección de la API")
    return f"{base}{ruta}"


def pedir(ruta: str, params: dict | None = None, espera: float = 15):
    """GET a la API. Devuelve el JSON, o None si el recurso no existe (404)."""
    motivo = ""
    for intento in range(1, INTENTOS + 1):
        try:
            respuesta = requests.get(url_api(ruta), params=params, timeout=TIEMPO_MAXIMO)
        except requests.RequestException as e:
            motivo = f"no se ha podido conectar con la API ({e.__class__.__name__})"
            pausa = espera / 3
        else:
            if respuesta.status_code == 404:
                return None
            if respuesta.status_code != 503:
                respuesta.raise_for_status()
                return respuesta.json()
            motivo = "la base de datos se está reanudando"
            pausa = min(float(respuesta.headers.get("Retry-After", espera)), espera)
        if intento < INTENTOS:
            time.sleep(pausa)
    raise ApiNoDisponible(motivo)
