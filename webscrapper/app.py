"""Handler de AWS Lambda para la etapa 1 (captura de los KID de una gestora).

Evento:
    {"gestora": "bestinver"}                         # obligatorio: bestinver | azvalor
    {"gestora": "azvalor", "fecha": "AAAAMMDD", "delay": 1.0}

También admite el evento de un horario (EventBridge Scheduler con {"time": "<aws.scheduler.scheduled-time>"}
o regla programada de EventBridge, con los parámetros en "detail"): sin "fecha", la carpeta de fecha
es el día UTC de la hora programada, de modo que un reintento escribe en la misma carpeta.

Devuelve el resumen de `capturar`, que es el evento de entrada de la etapa 2:
    {"bucket": ..., "gestora": ..., "fecha": ..., "manifiesto": ...,
     "claves": ["download/<gestora>/<fecha>/<slug>_datos_fundamentales.pdf", ...], "fallos": [...]}
"""

from datetime import UTC, datetime

from captura import capturar
from common import almacenamiento_s3 as alm


def fecha_de_hora(hora: str) -> str:
    """Convierte una hora ISO 8601 ("2026-11-26T06:00:00Z") en la fecha AAAAMMDD en UTC."""
    try:
        momento = datetime.fromisoformat(hora)
    except (TypeError, ValueError) as e:
        raise ValueError(f"hora programada no válida '{hora}', se espera ISO 8601") from e
    if momento.tzinfo is None:  # sin zona horaria: se asume UTC, como envía AWS
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC).strftime("%Y%m%d")


def parametros_evento(event) -> dict:
    """Parámetros de la etapa a partir de un evento directo, de Scheduler o de una regla de EventBridge."""
    event = alm.evento_lambda(event)
    parametros = dict(event)
    if isinstance(event.get("detail"), dict):  # regla programada de EventBridge
        parametros.update(event["detail"])
    if not parametros.get("fecha") and parametros.get("time"):
        parametros["fecha"] = fecha_de_hora(parametros["time"])
    return parametros


def handler(event, context):
    parametros = parametros_evento(event)
    if not parametros.get("gestora"):
        raise ValueError('el evento debe indicar la gestora, p. ej. {"gestora": "bestinver"}')
    return capturar(
        gestora=parametros["gestora"],
        bucket=parametros.get("bucket"),
        fecha=parametros.get("fecha"),
        delay=float(parametros.get("delay", 1.0)),
    )
