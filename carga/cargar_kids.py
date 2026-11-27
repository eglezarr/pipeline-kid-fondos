"""Etapa 4: carga de los datos extraídos de los KID en PostgreSQL (Aurora) con la RDS Data API.

Lee los JSON de  s3://<bucket>/extraction/<gestora>/<AAAAMMDD>/<slug>_datos_fundamentales.json
y, por cada uno, en una transacción:
  1. Inserta el documento en `documentos` (único por sha256). Si ya existía, solo actualiza la
     fecha de la última descarga.
  2. Inserta o actualiza sus datos en `kid` (único por documento).

Procesar dos veces el mismo documento no crea filas nuevas. Antes de cargar se aplica
`esquema.sql` (sentencias idempotentes), así que la base de datos no requiere preparación manual.

La Data API se usa por HTTPS con el rol de IAM de la función: no hay conexiones que gestionar ni
contraseñas en el código (las credenciales están en Secrets Manager). Si Aurora está en pausa, la
primera petición la reanuda y se reintenta hasta que responde.

Configuración (variables de entorno, las define Terraform en Lambda):
    AURORA_CLUSTER_ARN, AURORA_SECRETO_ARN, AURORA_BASE_DATOS (por defecto "fondos"), BUCKET_DATOS

Uso:
    python carga/cargar_kids.py bestinver                      # última fecha extraída
    python carga/cargar_kids.py azvalor --fecha 20261127
    python carga/cargar_kids.py bestinver --claves extraction/bestinver/20261127/x.json
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path, PurePosixPath

import boto3
from botocore.exceptions import ClientError

# Raíz del repo en el path para importar el paquete común al ejecutar el script directamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import almacenamiento_s3 as alm  # noqa: E402

FICHERO_ESQUEMA = Path(__file__).resolve().parent / "esquema.sql"

CAMPOS_KID = [
    "isin",
    "nombre_producto",
    "nombre_clase",
    "gestora",
    "fecha_documento",
    "sri",
    "periodo_mantenimiento_anios",
    "gastos_corrientes_pct",
    "costes_entrada_pct",
    "costes_salida_pct",
]

SQL_DOCUMENTO = """
INSERT INTO documentos (sha256, gestora, slug, fondo_web, url_ficha, url_origen, isin_web, clave_s3,
                        tamano_bytes, primera_descarga, ultima_descarga)
VALUES (:sha256, :gestora, :slug, :fondo_web, :url_ficha, :url_origen, :isin_web, :clave_s3,
        :tamano_bytes, :fecha_descarga, :fecha_descarga)
ON CONFLICT (sha256) DO UPDATE
   SET ultima_descarga = GREATEST(documentos.ultima_descarga, EXCLUDED.ultima_descarga)
RETURNING id
"""

SQL_KID = """
INSERT INTO kid (documento_id, isin, nombre_producto, nombre_clase, gestora, fecha_documento, sri,
                 periodo_mantenimiento_anios, gastos_corrientes_pct, costes_entrada_pct, costes_salida_pct,
                 modelo, fecha_extraccion, evidencias, verificacion_evidencias, validaciones)
VALUES (:documento_id, :isin, :nombre_producto, :nombre_clase, :gestora, :fecha_documento, :sri,
        :periodo_mantenimiento_anios, :gastos_corrientes_pct, :costes_entrada_pct, :costes_salida_pct,
        :modelo, :fecha_extraccion, :evidencias, :verificacion_evidencias, :validaciones)
ON CONFLICT (documento_id) DO UPDATE
   SET isin = EXCLUDED.isin,
       nombre_producto = EXCLUDED.nombre_producto,
       nombre_clase = EXCLUDED.nombre_clase,
       gestora = EXCLUDED.gestora,
       fecha_documento = EXCLUDED.fecha_documento,
       sri = EXCLUDED.sri,
       periodo_mantenimiento_anios = EXCLUDED.periodo_mantenimiento_anios,
       gastos_corrientes_pct = EXCLUDED.gastos_corrientes_pct,
       costes_entrada_pct = EXCLUDED.costes_entrada_pct,
       costes_salida_pct = EXCLUDED.costes_salida_pct,
       modelo = EXCLUDED.modelo,
       fecha_extraccion = EXCLUDED.fecha_extraccion,
       evidencias = EXCLUDED.evidencias,
       verificacion_evidencias = EXCLUDED.verificacion_evidencias,
       validaciones = EXCLUDED.validaciones,
       cargado = now()
"""

SQL_RECUENTO = """
SELECT (SELECT count(*) FROM documentos), (SELECT count(*) FROM kid), (SELECT count(*) FROM kid_actual)
"""


def parametro(nombre: str, valor, tipo: str | None = None) -> dict:
    """Parámetro de la Data API con el tipo adecuado al valor de Python.

    `tipo` es el typeHint de la Data API para textos que PostgreSQL debe interpretar como
    DATE, TIMESTAMP o JSON.
    """
    if valor is None:
        campo = {"isNull": True}
    elif isinstance(valor, bool):
        campo = {"booleanValue": valor}
    elif isinstance(valor, int):
        campo = {"longValue": valor}
    elif isinstance(valor, float):
        campo = {"doubleValue": valor}
    elif isinstance(valor, (dict, list)):
        campo, tipo = {"stringValue": json.dumps(valor, ensure_ascii=False)}, "JSON"
    else:
        campo = {"stringValue": str(valor)}
    resultado = {"name": nombre, "value": campo}
    if tipo and valor is not None:
        resultado["typeHint"] = tipo
    return resultado


def marca_temporal(texto_iso: str) -> str:
    """'2026-11-27T16:29:30Z' -> '2026-11-27 16:29:30' (formato TIMESTAMP de la Data API, en UTC)."""
    return datetime.strptime(texto_iso, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M:%S")


def sentencias_esquema(texto: str) -> list[str]:
    """Sentencias SQL del esquema, sin comentarios ni líneas vacías.

    Primero se quitan los comentarios (la Data API interpretaría ':palabra' como un parámetro)
    y después se separan las sentencias por ';'.
    """
    sin_comentarios = "\n".join(re.sub(r"--.*$", "", linea).rstrip() for linea in texto.splitlines())
    sentencias = []
    for bloque in sin_comentarios.split(";"):
        sentencia = "\n".join(linea for linea in bloque.splitlines() if linea.strip()).strip()
        if sentencia:
            sentencias.append(sentencia)
    return sentencias


class BaseDatos:
    """Acceso a Aurora PostgreSQL mediante la RDS Data API."""

    def __init__(self, cluster_arn: str, secreto_arn: str, base_datos: str, cliente=None):
        self.cluster_arn = cluster_arn
        self.secreto_arn = secreto_arn
        self.base_datos = base_datos
        self.cliente = cliente or boto3.client("rds-data")

    @classmethod
    def desde_entorno(cls) -> "BaseDatos":
        try:
            return cls(
                os.environ["AURORA_CLUSTER_ARN"],
                os.environ["AURORA_SECRETO_ARN"],
                os.environ.get("AURORA_BASE_DATOS", "fondos"),
            )
        except KeyError as e:
            raise alm.ErrorEtapa(f"falta la variable de entorno {e}") from e

    def _llamar(self, operacion: str, **argumentos) -> dict:
        """Llama a la Data API; si Aurora se está reanudando tras una pausa, espera y reintenta."""
        argumentos |= {"resourceArn": self.cluster_arn, "secretArn": self.secreto_arn}
        for intento in range(1, 13):
            try:
                return getattr(self.cliente, operacion)(**argumentos)
            except ClientError as e:
                if e.response["Error"]["Code"] != "DatabaseResumingException" or intento == 12:
                    raise
                print(f"Aurora se está reanudando (intento {intento}); nuevo intento en 10 s")
                time.sleep(10)
        raise AssertionError("inalcanzable")

    def ejecutar(self, sql: str, parametros: list[dict] | None = None, transaccion: str | None = None) -> dict:
        argumentos = {"sql": sql, "database": self.base_datos, "parameters": parametros or []}
        if transaccion:
            argumentos["transactionId"] = transaccion
        return self._llamar("execute_statement", **argumentos)

    def transaccion(self) -> str:
        return self._llamar("begin_transaction", database=self.base_datos)["transactionId"]

    def confirmar(self, transaccion: str) -> None:
        self._llamar("commit_transaction", transactionId=transaccion)

    def deshacer(self, transaccion: str) -> None:
        self._llamar("rollback_transaction", transactionId=transaccion)

    def aplicar_esquema(self) -> None:
        for sentencia in sentencias_esquema(FICHERO_ESQUEMA.read_text(encoding="utf-8")):
            self.ejecutar(sentencia)

    def recuento(self) -> dict:
        fila = self.ejecutar(SQL_RECUENTO)["records"][0]
        return dict(zip(["documentos", "kid", "kid_actual"], (c["longValue"] for c in fila), strict=True))


def parametros_documento(documento: dict, gestora: str) -> list[dict]:
    return [
        parametro("sha256", documento["sha256"]),
        parametro("gestora", gestora),
        parametro("slug", documento["slug"]),
        parametro("fondo_web", documento.get("fondo")),
        parametro("url_ficha", documento.get("url_ficha")),
        parametro("url_origen", documento["url_origen"]),
        parametro("isin_web", documento.get("isin_web")),
        parametro("clave_s3", documento["clave_s3"]),
        parametro("tamano_bytes", documento.get("tamano_bytes")),
        parametro("fecha_descarga", marca_temporal(documento["fecha_descarga"]), "TIMESTAMP"),
    ]


def parametros_kid(extraccion: dict, documento_id: int) -> list[dict]:
    datos = extraccion["datos"]
    evidencias = {campo: datos.get(f"{campo}_evidencia") for campo in CAMPOS_KID}
    numericos = {"periodo_mantenimiento_anios", "gastos_corrientes_pct", "costes_entrada_pct", "costes_salida_pct"}
    parametros = [parametro("documento_id", documento_id)]
    for campo in CAMPOS_KID:
        valor = datos.get(campo)
        if campo in numericos and valor is not None:
            valor = float(valor)
        parametros.append(parametro(campo, valor, "DATE" if campo == "fecha_documento" else None))
    return parametros + [
        parametro("modelo", extraccion["modelo"]),
        parametro("fecha_extraccion", marca_temporal(extraccion["fecha_extraccion"]), "TIMESTAMP"),
        parametro("evidencias", evidencias),
        parametro("verificacion_evidencias", extraccion.get("verificacion_evidencias") or {}),
        parametro("validaciones", extraccion.get("validaciones") or {}),
    ]


def cargar_kids(
    gestora: str,
    bucket: str | None = None,
    fecha: str | None = None,
    claves: list[str] | None = None,
    bd: BaseDatos | None = None,
) -> dict:
    """Carga en PostgreSQL los JSON de extraction/<gestora>/<fecha>/ (o los de `claves`)."""
    bucket = alm.resolver_bucket(bucket)
    s3 = alm.conectar(bucket)
    fecha = alm.resolver_fecha(s3, bucket, alm.CARPETA_EXTRACCION, gestora, fecha)
    origen = alm.carpeta(alm.CARPETA_EXTRACCION, gestora, fecha)
    print(f"Origen: s3://{bucket}/{origen}/\n")

    if claves is not None:
        claves_json = [c for c in claves if str(PurePosixPath(c).parent) == origen and c.endswith(".json")]
    else:
        claves_json = alm.listar_claves(s3, bucket, origen, ".json")
    if not claves_json:
        raise alm.ErrorEtapa(f"no hay ningún JSON que cargar en s3://{bucket}/{origen}/")

    bd = bd or BaseDatos.desde_entorno()
    bd.aplicar_esquema()
    antes = bd.recuento()

    cargados, fallos = [], []
    for clave in claves_json:
        nombre = PurePosixPath(clave).name
        try:
            extraccion = json.loads(alm.leer(s3, bucket, clave))
            documento = extraccion.get("documento")
            if not documento:
                raise ValueError("el JSON no incluye los datos de origen del documento (manifiesto)")
            transaccion = bd.transaccion()
            try:
                respuesta = bd.ejecutar(SQL_DOCUMENTO, parametros_documento(documento, gestora), transaccion)
                documento_id = respuesta["records"][0][0]["longValue"]
                bd.ejecutar(SQL_KID, parametros_kid(extraccion, documento_id), transaccion)
                bd.confirmar(transaccion)
            except Exception:
                bd.deshacer(transaccion)
                raise
            print(f"[ok] {nombre} -> documento {documento_id} ({extraccion['datos']['isin']})")
            cargados.append(clave)
        except Exception as error:  # un documento que falle no debe parar el resto
            print(f"[error] {nombre}: {error}")
            fallos.append({"fichero": nombre, "error": str(error)})

    despues = bd.recuento()
    print(f"\nResumen: {len(cargados)} cargados, {len(fallos)} fallos")
    print(f"Filas antes:   {antes}")
    print(f"Filas después: {despues}")
    if not cargados:
        raise alm.ErrorEtapa("no se ha podido cargar ningún KID")
    return {
        "bucket": bucket,
        "gestora": gestora,
        "fecha": fecha,
        "claves": cargados,
        "filas_antes": antes,
        "filas_despues": despues,
        "fallos": fallos,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gestora", help="Gestora (carpeta dentro de extraction/)")
    parser.add_argument("--claves", nargs="+", help="Claves de S3 de los JSON a cargar")
    parser.add_argument("--bucket", help=f"Bucket de S3 (por defecto, la variable {alm.VARIABLE_BUCKET})")
    parser.add_argument("--fecha", type=alm.fecha_valida, help="Carpeta AAAAMMDD (por defecto, la más reciente)")
    args = parser.parse_args()
    try:
        resumen = cargar_kids(args.gestora, args.bucket, args.fecha, args.claves)
    except alm.ErrorEtapa as e:
        print(f"[error] {e}")
        return 1
    return 1 if resumen["fallos"] else 0


if __name__ == "__main__":
    sys.exit(main())
