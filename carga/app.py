"""Handler de AWS Lambda para la etapa 4 (carga en PostgreSQL).

Evento (la salida de la etapa 3 es un evento válido: se cargan los JSON de su "claves"):
    {"gestora": "bestinver", "fecha": "AAAAMMDD", "claves": ["extraction/bestinver/AAAAMMDD/x.json", ...]}
Sin "claves" se cargan todos los JSON de la carpeta. Opcional: "bucket" (por defecto, BUCKET_DATOS).

Devuelve un resumen con los JSON cargados, los fallos y el número de filas antes y después de la
carga (documentos, kid y kid_actual), que permite comprobar que no se crean duplicados.
"""

from cargar_kids import cargar_kids
from common import almacenamiento_s3 as alm


def handler(event, context):
    event = alm.evento_lambda(event)
    if not event.get("gestora"):
        raise ValueError('el evento debe indicar la gestora, p. ej. {"gestora": "bestinver"}')
    return cargar_kids(
        gestora=event["gestora"],
        bucket=event.get("bucket"),
        fecha=event.get("fecha"),
        claves=event.get("claves"),
    )
