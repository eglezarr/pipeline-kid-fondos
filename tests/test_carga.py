"""Tests de la etapa 4: parámetros de la Data API, esquema y carga transaccional."""

import json

import pytest

import cargar_kids
from cargar_kids import BaseDatos, marca_temporal, parametro, sentencias_esquema
from common import almacenamiento_s3 as alm

EXTRACCION = {
    "gestora": "bestinver",
    "fecha": "20261127",
    "documento": {
        "fondo": "Bestinfond, F.I.",
        "slug": "bestinfond",
        "url_ficha": "https://www.bestinver.es/fondos-de-inversion/bestinfond/",
        "url_origen": "https://www.bestinver.es/wp-content/uploads/bestinfond_fi_datos_fundamentales.pdf?h=1",
        "isin_web": "ES0114673033",
        "clave_s3": "download/bestinver/20261127/bestinfond_datos_fundamentales.pdf",
        "fecha_descarga": "2026-11-27T16:29:30Z",
        "sha256": "a" * 64,
        "tamano_bytes": 436559,
    },
    "modelo": "global.moonshotai.kimi-k3.1",
    "fecha_extraccion": "2026-11-27T16:40:00Z",
    "datos": {
        "isin": "ES0114673033",
        "isin_evidencia": "ISIN: ES0114673033",
        "nombre_producto": "BESTINFOND, F.I.",
        "nombre_clase": None,
        "gestora": "BESTINVER GESTION SGIIC, S.A.",
        "fecha_documento": "2025-12-31",
        "sri": 4,
        "periodo_mantenimiento_anios": 5,
        "gastos_corrientes_pct": 1.8,
        "costes_entrada_pct": 0,
        "costes_salida_pct": 0.0,
    },
    "verificacion_evidencias": {"isin": True},
    "validaciones": {"isin_valido": True, "isin_coincide_web": True, "sri_en_rango": True},
}


def test_parametro_tipos():
    assert parametro("x", None) == {"name": "x", "value": {"isNull": True}}
    assert parametro("x", 4) == {"name": "x", "value": {"longValue": 4}}
    assert parametro("x", 1.8) == {"name": "x", "value": {"doubleValue": 1.8}}
    assert parametro("x", "2025-12-31", "DATE") == {
        "name": "x",
        "value": {"stringValue": "2025-12-31"},
        "typeHint": "DATE",
    }
    # Un diccionario se envía como JSON
    assert parametro("x", {"a": "ñ"}) == {"name": "x", "value": {"stringValue": '{"a": "ñ"}'}, "typeHint": "JSON"}
    # Un nulo no lleva typeHint
    assert "typeHint" not in parametro("x", None, "DATE")


def test_marca_temporal():
    assert marca_temporal("2026-11-27T16:29:30Z") == "2026-11-27 16:29:30"


def test_esquema_sin_comentarios_ni_parametros_accidentales():
    sentencias = sentencias_esquema(cargar_kids.FICHERO_ESQUEMA.read_text(encoding="utf-8"))
    assert any(s.startswith("CREATE TABLE IF NOT EXISTS documentos") for s in sentencias)
    assert any(s.startswith("CREATE VIEW kid_actual") for s in sentencias)
    for sentencia in sentencias:
        assert "--" not in sentencia
        assert ":" not in sentencia  # la Data API tomaría ':palabra' por un parámetro


class DataApiFalsa:
    """Simula el cliente rds-data: registra las sentencias y asigna ids a los documentos."""

    def __init__(self):
        self.sentencias, self.documentos, self.confirmadas = [], {}, 0

    def begin_transaction(self, **_):
        return {"transactionId": "t1"}

    def commit_transaction(self, **_):
        self.confirmadas += 1
        return {}

    def rollback_transaction(self, **_):
        return {}

    def execute_statement(self, sql, parameters, **argumentos):
        self.sentencias.append((sql, parameters, argumentos.get("transactionId")))
        if "INSERT INTO documentos" in sql:
            sha = next(p["value"]["stringValue"] for p in parameters if p["name"] == "sha256")
            identificador = self.documentos.setdefault(sha, len(self.documentos) + 1)
            return {"records": [[{"longValue": identificador}]]}
        if "count(*)" in sql:
            n = len(self.documentos)
            return {"records": [[{"longValue": n}, {"longValue": n}, {"longValue": n}]]}
        return {}


@pytest.fixture
def s3_simulado(monkeypatch):
    clave = "extraction/bestinver/20261127/bestinfond_datos_fundamentales.json"
    objetos = {clave: json.dumps(EXTRACCION).encode("utf-8")}
    monkeypatch.setattr(alm, "conectar", lambda bucket: object())
    monkeypatch.setattr(alm, "listar_claves", lambda s3, b, carpeta, ext: [c for c in objetos if c.endswith(ext)])
    monkeypatch.setattr(alm, "leer", lambda s3, b, c: objetos[c])
    return objetos


def test_cargar_dos_veces_no_duplica(s3_simulado):
    api = DataApiFalsa()
    bd = BaseDatos("arn:cluster", "arn:secreto", "fondos", cliente=api)

    primera = cargar_kids.cargar_kids("bestinver", bucket="b", fecha="20261127", bd=bd)
    segunda = cargar_kids.cargar_kids("bestinver", bucket="b", fecha="20261127", bd=bd)

    assert primera["filas_despues"] == segunda["filas_despues"] == {"documentos": 1, "kid": 1, "kid_actual": 1}
    assert api.confirmadas == 2  # una transacción por documento y carga

    # El documento y sus datos se escriben dentro de la misma transacción
    escrituras = [(sql, t) for sql, _, t in api.sentencias if "INSERT" in sql]
    assert escrituras and all(t == "t1" for _, t in escrituras)

    # Los datos del KID llegan con el tipo correcto
    _, parametros, _ = next(s for s in api.sentencias if "INSERT INTO kid" in s[0])
    por_nombre = {p["name"]: p for p in parametros}
    assert por_nombre["sri"]["value"] == {"longValue": 4}
    assert por_nombre["costes_entrada_pct"]["value"] == {"doubleValue": 0.0}
    assert por_nombre["nombre_clase"]["value"] == {"isNull": True}
    assert por_nombre["fecha_documento"]["typeHint"] == "DATE"
    assert json.loads(por_nombre["evidencias"]["value"]["stringValue"])["isin"] == "ISIN: ES0114673033"
