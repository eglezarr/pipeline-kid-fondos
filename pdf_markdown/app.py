"""Handler de AWS Lambda para la etapa 2 (PDF -> Markdown).

Evento (la salida de la etapa 1 es un evento válido: se convierten solo los PDF de su "claves"):
    {"gestora": "bestinver", "fecha": "AAAAMMDD", "claves": ["download/bestinver/AAAAMMDD/x.pdf", ...]}
Opcionales: "ficheros" (en lugar de "claves"), "ocr" (auto | siempre | nunca), "idioma",
"sobrescribir", "bucket" (por defecto, la variable BUCKET_DATOS).

Devuelve el resumen de `convertir_pdfs`, que es el evento de entrada de la etapa 3:
    {"bucket": ..., "gestora": ..., "fecha": ..., "claves": ["markdown/<gestora>/<fecha>/x.md", ...],
     "convertidos": [...], "omitidos": [...], "fallos": [...]}
"""

from common import almacenamiento_s3 as alm
from pdf_a_markdown import convertir_pdfs


def handler(event, context):
    event = alm.evento_lambda(event)
    if not event.get("gestora"):
        raise ValueError('el evento debe indicar la gestora, p. ej. {"gestora": "bestinver"}')
    resumen = convertir_pdfs(
        gestora=event["gestora"],
        bucket=event.get("bucket"),
        fecha=event.get("fecha"),
        ficheros=event.get("ficheros"),
        modo_ocr=event.get("ocr", "auto"),
        idioma=event.get("idioma", "spa"),
        sobrescribir=bool(event.get("sobrescribir", False)),
        claves=event.get("claves"),
    )
    resumen["fallos_previos"] = alm.fallos_acumulados(event, "descarga")
    return resumen
