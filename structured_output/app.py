"""Handler de AWS Lambda para la etapa 3 (extracción de los datos del KID con Bedrock).

Evento (la salida de la etapa 2 es un evento válido: se procesan los KID de su "claves"):
    {"gestora": "bestinver", "fecha": "AAAAMMDD", "claves": ["markdown/bestinver/AAAAMMDD/x.md", ...]}
Opcionales: "fondos" (slugs, en lugar de "claves"), "bucket" (por defecto, la variable BUCKET_DATOS).
Sin "claves" ni "fondos" se procesan todos los KID de la carpeta.

Devuelve el resumen de `extraer_kids`, que es el evento de entrada de la etapa 4:
    {"bucket": ..., "gestora": ..., "fecha": ...,
     "claves": ["extraction/<gestora>/<fecha>/x.json", ...], "fallos": [...]}
"""

from common import almacenamiento_s3 as alm
from extractor_kid import extraer_kids


def handler(event, context):
    event = alm.evento_lambda(event)
    if not event.get("gestora"):
        raise ValueError('el evento debe indicar la gestora, p. ej. {"gestora": "bestinver"}')
    return extraer_kids(
        gestora=event["gestora"],
        bucket=event.get("bucket"),
        fecha=event.get("fecha"),
        fondos=event.get("fondos"),
        claves=event.get("claves"),
    )
