"""Acceso a Aurora PostgreSQL mediante la RDS Data API (compartido por la carga y la API).

La Data API se usa por HTTPS con el rol de IAM de cada función: no hay conexiones que gestionar
ni contraseñas en el código (las credenciales están en Secrets Manager y la Data API las usa en
nombre de la función). Si Aurora está en pausa (0 ACU), la primera petición la reanuda y devuelve
DatabaseResumingException: se espera y se reintenta.

Configuración por variables de entorno (las define Terraform en Lambda):
    AURORA_CLUSTER_ARN, AURORA_SECRETO_ARN, AURORA_BASE_DATOS (por defecto "fondos")
"""

import json
import os
import time

import boto3
from botocore.exceptions import ClientError


class BaseDatosNoDisponible(RuntimeError):
    """Aurora sigue reanudándose tras agotar los reintentos, o falta la configuración."""


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


class BaseDatos:
    """Cliente de la Data API para un clúster y una base de datos."""

    def __init__(
        self,
        cluster_arn: str,
        secreto_arn: str,
        base_datos: str = "fondos",
        cliente=None,
        reintentos: int = 12,
        espera: float = 10,
    ):
        self.cluster_arn = cluster_arn
        self.secreto_arn = secreto_arn
        self.base_datos = base_datos
        self.cliente = cliente or boto3.client("rds-data")
        self.reintentos = reintentos  # intentos mientras Aurora se reanuda
        self.espera = espera  # segundos entre intentos

    @classmethod
    def desde_entorno(cls, **opciones) -> "BaseDatos":
        try:
            return cls(
                os.environ["AURORA_CLUSTER_ARN"],
                os.environ["AURORA_SECRETO_ARN"],
                os.environ.get("AURORA_BASE_DATOS", "fondos"),
                **opciones,
            )
        except KeyError as e:
            raise BaseDatosNoDisponible(f"falta la variable de entorno {e}") from e

    def _llamar(self, operacion: str, **argumentos) -> dict:
        """Llama a la Data API; si Aurora se está reanudando tras una pausa, espera y reintenta."""
        argumentos |= {"resourceArn": self.cluster_arn, "secretArn": self.secreto_arn}
        for intento in range(1, self.reintentos + 1):
            try:
                return getattr(self.cliente, operacion)(**argumentos)
            except ClientError as e:
                if e.response["Error"]["Code"] != "DatabaseResumingException":
                    raise
                if intento == self.reintentos:
                    raise BaseDatosNoDisponible("la base de datos se está reanudando tras una pausa") from e
                print(f"Aurora se está reanudando (intento {intento}); nuevo intento en {self.espera} s")
                time.sleep(self.espera)
        raise AssertionError("inalcanzable")

    def ejecutar(self, sql: str, parametros: list[dict] | None = None, transaccion: str | None = None) -> dict:
        argumentos = {"sql": sql, "database": self.base_datos, "parameters": parametros or []}
        if transaccion:
            argumentos["transactionId"] = transaccion
        return self._llamar("execute_statement", **argumentos)

    def consultar(self, sql: str, parametros: list[dict] | None = None) -> list[dict]:
        """Ejecuta una consulta y devuelve las filas como diccionarios {columna: valor}."""
        respuesta = self._llamar(
            "execute_statement",
            sql=sql,
            database=self.base_datos,
            parameters=parametros or [],
            formatRecordsAs="JSON",
        )
        return json.loads(respuesta.get("formattedRecords") or "[]")

    def transaccion(self) -> str:
        return self._llamar("begin_transaction", database=self.base_datos)["transactionId"]

    def confirmar(self, transaccion: str) -> None:
        self._llamar("commit_transaction", transactionId=transaccion)

    def deshacer(self, transaccion: str) -> None:
        self._llamar("rollback_transaction", transactionId=transaccion)
