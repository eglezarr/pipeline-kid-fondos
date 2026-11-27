"""Utilidades comunes para leer y escribir en S3 las distintas etapas del pipeline.

Estructura del bucket (misma ruta <gestora>/<AAAAMMDD>/<slug>_<tipo> en cada etapa):

    download/<gestora>/<AAAAMMDD>/<slug>_<tipo>.pdf     etapa 1: PDF descargados
    download/<gestora>/<AAAAMMDD>/manifiesto.json       etapa 1: origen de cada PDF
    markdown/<gestora>/<AAAAMMDD>/<slug>_<tipo>.md      etapa 2: PDF convertidos a Markdown
    extraction/<gestora>/<AAAAMMDD>/<slug>_<tipo>.json  etapa 3: datos extraídos

El bucket se toma de la variable de entorno BUCKET_DATOS (en Lambda la define Terraform).

Encadenamiento: cada etapa devuelve un resumen con `bucket`, `gestora`, `fecha`, `claves`
(claves de S3 que ha dejado listas) y `fallos`. Ese resumen es un evento válido para la etapa
siguiente, que procesa solo esas `claves`.
"""

import argparse
import os
import re
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError

VARIABLE_BUCKET = "BUCKET_DATOS"

CARPETA_DESCARGA = "download"
CARPETA_MARKDOWN = "markdown"
CARPETA_EXTRACCION = "extraction"

TIPO_KID = "datos_fundamentales"
NOMBRE_MANIFIESTO = "manifiesto.json"


class ErrorEtapa(RuntimeError):
    """Error que impide ejecutar una etapa (bucket inaccesible, nada que procesar...).

    Los scripts lo muestran y terminan con código 1; en Lambda hace fallar la invocación.
    """


def bucket_por_defecto() -> str | None:
    """Bucket de datos configurado en la variable de entorno BUCKET_DATOS (o None)."""
    return os.environ.get(VARIABLE_BUCKET) or None


def resolver_bucket(bucket: str | None) -> str:
    """Devuelve el bucket indicado o el de BUCKET_DATOS; si no hay ninguno, lanza ErrorEtapa."""
    bucket = bucket or bucket_por_defecto()
    if not bucket:
        raise ErrorEtapa(f"no se ha indicado bucket: usa --bucket o define la variable {VARIABLE_BUCKET}")
    return bucket


def evento_lambda(event) -> dict:
    """Parámetros de entrada de un handler a partir del evento de Lambda.

    Las etapas se encadenan pasando la salida de una como evento de la siguiente. El evento
    puede llegar tal cual (invocación directa o Step Functions) o dentro del sobre de Lambda
    Destinations ({"requestPayload": ..., "responsePayload": <salida de la etapa anterior>}).
    """
    event = event or {}
    if isinstance(event.get("responsePayload"), dict):
        return event["responsePayload"]
    return event


def fallos_acumulados(event: dict, etapa_anterior: str) -> list[dict]:
    """Fallos de las etapas anteriores, para que lleguen al resumen final del pipeline.

    Cada etapa devuelve sus `fallos`; la siguiente los añade (con el nombre de la etapa) a
    `fallos_previos`, de modo que la respuesta de la última etapa los incluye todos.
    """
    return list(event.get("fallos_previos", [])) + [
        {"etapa": etapa_anterior, **fallo} for fallo in event.get("fallos", [])
    ]


def comprobar_fecha(texto: str) -> str:
    """Devuelve la fecha si tiene el formato AAAAMMDD; si no, lanza ValueError."""
    try:
        datetime.strptime(texto, "%Y%m%d")
    except (TypeError, ValueError) as e:
        raise ValueError(f"fecha no válida '{texto}', formato AAAAMMDD") from e
    return texto


def fecha_valida(texto: str) -> str:
    """Valida el formato AAAAMMDD para argparse."""
    try:
        return comprobar_fecha(texto)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def carpeta(etapa: str, gestora: str, fecha: str) -> str:
    """Ruta de la carpeta de una etapa, sin barra final: <etapa>/<gestora>/<fecha>."""
    return f"{etapa}/{gestora.strip('/')}/{fecha}"


def conectar(bucket: str):
    """Crea el cliente de S3 y comprueba que el bucket es accesible (si no, lanza ErrorEtapa)."""
    s3 = boto3.client("s3")
    try:
        s3.head_bucket(Bucket=bucket)
    except (BotoCoreError, ClientError) as e:
        raise ErrorEtapa(f"no se puede acceder al bucket '{bucket}': {e}") from e
    return s3


def listar_claves(s3, bucket: str, carpeta_s3: str, extension: str) -> list[str]:
    """Claves de la carpeta (sin recursión) que terminan en la extensión dada, ordenadas."""
    claves = []
    paginador = s3.get_paginator("list_objects_v2")
    for pagina in paginador.paginate(Bucket=bucket, Prefix=f"{carpeta_s3}/", Delimiter="/"):
        for obj in pagina.get("Contents", []):
            if obj["Key"].lower().endswith(extension):
                claves.append(obj["Key"])
    return sorted(claves)


def ultima_fecha(s3, bucket: str, etapa: str, gestora: str) -> str | None:
    """Fecha (AAAAMMDD) más reciente con carpeta en <etapa>/<gestora>/, o None si no hay."""
    fechas = []
    paginador = s3.get_paginator("list_objects_v2")
    raiz = f"{etapa}/{gestora.strip('/')}/"
    for pagina in paginador.paginate(Bucket=bucket, Prefix=raiz, Delimiter="/"):
        for comun in pagina.get("CommonPrefixes", []):
            nombre = comun["Prefix"][len(raiz) :].strip("/")
            if re.fullmatch(r"\d{8}", nombre):
                fechas.append(nombre)
    return max(fechas) if fechas else None


def leer(s3, bucket: str, clave: str) -> bytes:
    return s3.get_object(Bucket=bucket, Key=clave)["Body"].read()


def existe(s3, bucket: str, clave: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=clave)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def escribir(s3, bucket: str, clave: str, contenido: bytes, content_type: str, metadatos: dict | None = None) -> None:
    """Sube un objeto a S3. Los metadatos de S3 solo admiten caracteres ASCII."""
    s3.put_object(
        Bucket=bucket,
        Key=clave,
        Body=contenido,
        ContentType=content_type,
        Metadata=metadatos or {},
    )


def resolver_fecha(s3, bucket: str, etapa: str, gestora: str, fecha: str | None) -> str:
    """Devuelve la fecha indicada o, si no se indica, la más reciente disponible en la etapa."""
    if fecha:
        return comprobar_fecha(fecha)
    fecha = ultima_fecha(s3, bucket, etapa, gestora)
    if not fecha:
        raise ErrorEtapa(f"no hay ninguna carpeta de fecha en s3://{bucket}/{etapa}/{gestora}/")
    return fecha
