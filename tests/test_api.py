"""Tests de la API: rutas, validación de parámetros, consultas generadas y acceso a la Data API.

La base de datos se sustituye por una falsa que devuelve filas con el formato de la Data API
(formatRecordsAs=JSON: numéricos como texto, JSONB como texto, fechas sin zona horaria).
"""

import importlib.util
import json
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

import api_fondos
from api_fondos import Repositorio, app, obtener_repositorio, obtener_s3
from common.base_datos import BaseDatos, BaseDatosNoDisponible

ISIN = "ES0114673033"

FILA_FONDO = {
    "isin": ISIN,
    "nombre_producto": "BESTINFOND, F.I.",
    "nombre_clase": None,
    "gestora": "BESTINVER GESTION SGIIC, S.A.",
    "fuente": "bestinver",
    "fecha_documento": "2025-12-31",
    "sri": 4,
    "periodo_mantenimiento_anios": "5.00",
    "gastos_corrientes_pct": "1.800",
    "costes_entrada_pct": "0.000",
    "costes_salida_pct": None,
    "validaciones": json.dumps({"isin_valido": True, "isin_coincide_web": None, "sri_en_rango": True}),
    "verificacion_evidencias": json.dumps({"isin": True, "sri": False}),
    "modelo": "global.moonshotai.kimi-k3.1",
    "ultima_descarga": "2026-11-27 16:29:30",
}

FILA_DETALLE = FILA_FONDO | {
    "evidencias": json.dumps({"isin": "ISIN: ES0114673033", "nombre_clase": None}),
    "fecha_extraccion": "2026-11-27 16:40:00.123",
    "documento_id": 7,
    "url_origen": "https://www.bestinver.es/x.pdf",
    "url_ficha": "https://www.bestinver.es/fondos-de-inversion/bestinfond/",
    "primera_descarga": "2026-11-27 16:29:30",
}


class BaseDatosFalsa:
    """Sustituye a BaseDatos: guarda las consultas y responde según el texto del SQL."""

    def __init__(self, respuestas: dict[str, list[dict]] | None = None):
        self.respuestas = respuestas or {}
        self.consultas = []

    def consultar(self, sql, parametros=None):
        self.consultas.append((sql, parametros or []))
        for fragmento, filas in self.respuestas.items():
            if fragmento in sql:
                return [dict(f) for f in filas]
        return []


class S3Falso:
    def generate_presigned_url(self, operacion, Params, ExpiresIn):
        return f"https://s3.example/{Params['Bucket']}/{Params['Key']}?expira={ExpiresIn}"


@pytest.fixture
def cliente():
    """Devuelve una función que crea un cliente de pruebas con la base de datos falsa indicada."""

    def crear(bd: BaseDatosFalsa | None = None) -> TestClient:
        app.dependency_overrides[obtener_repositorio] = lambda: Repositorio(bd or BaseDatosFalsa())
        app.dependency_overrides[obtener_s3] = S3Falso
        return TestClient(app)

    yield crear
    app.dependency_overrides.clear()


def test_health_no_consulta_la_base_de_datos(cliente):
    bd = BaseDatosFalsa()
    respuesta = cliente(bd).get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}
    assert bd.consultas == []


def test_fondos_convierte_los_tipos_de_la_data_api(cliente):
    bd = BaseDatosFalsa({"FROM kid_actual": [FILA_FONDO]})
    respuesta = cliente(bd).get("/fondos")
    assert respuesta.status_code == 200
    fondo = respuesta.json()[0]
    assert fondo["gastos_corrientes_pct"] == 1.8
    assert fondo["periodo_mantenimiento_anios"] == 5.0
    assert fondo["costes_salida_pct"] is None
    assert fondo["validaciones"] == {"isin_valido": True, "isin_coincide_web": None, "sri_en_rango": True}
    assert fondo["verificacion_evidencias"] == {"isin": True, "sri": False}
    # Sin filtros no hay WHERE y el orden por defecto es el nombre
    sql, parametros = bd.consultas[0]
    assert "WHERE" not in sql and "ORDER BY nombre_producto" in sql and parametros == []


def test_fondos_filtros_como_parametros(cliente):
    bd = BaseDatosFalsa()
    respuesta = cliente(bd).get("/fondos", params={"fuente": "azvalor", "sri_min": 3, "texto": "50%", "orden": "sri"})
    assert respuesta.status_code == 200
    sql, parametros = bd.consultas[0]
    assert "fuente = :fuente" in sql and "sri >= :sri_min" in sql and "sri <= :sri_max" not in sql
    assert sql.rstrip().endswith("ORDER BY sri, nombre_producto")
    valores = {p["name"]: p["value"] for p in parametros}
    assert valores["fuente"] == {"stringValue": "azvalor"}
    assert valores["sri_min"] == {"longValue": 3}
    # Los comodines del texto se escapan: se busca el texto literal
    assert valores["texto"] == {"stringValue": "%50\\%%"}
    # Ningún valor del usuario aparece en el SQL
    assert "azvalor" not in sql and "50" not in sql


@pytest.mark.parametrize(
    "params",
    [
        {"orden": "nombre; DROP TABLE kid"},
        {"fuente": "Azvalor'--"},
        {"sri_min": 0},
        {"sri_max": 8},
        {"sri_min": 5, "sri_max": 2},
    ],
)
def test_fondos_rechaza_parametros_no_validos(cliente, params):
    bd = BaseDatosFalsa()
    assert cliente(bd).get("/fondos", params=params).status_code == 422
    assert bd.consultas == []


def test_detalle_con_historial(cliente):
    historial = [
        {
            "documento_id": 7,
            "fecha_documento": "2025-12-31",
            "sri": 4,
            "gastos_corrientes_pct": "1.800",
            "primera_descarga": "2026-11-27 16:29:30",
            "ultima_descarga": "2026-11-27 16:29:30",
        },
        {
            "documento_id": 3,
            "fecha_documento": "2024-12-31",
            "sri": 4,
            "gastos_corrientes_pct": "1.780",
            "primera_descarga": "2025-11-15 09:00:00",
            "ultima_descarga": "2025-11-15 09:00:00",
        },
    ]
    bd = BaseDatosFalsa({"FROM kid_actual": [FILA_DETALLE], "FROM kid k": historial})
    respuesta = cliente(bd).get(f"/fondos/{ISIN}")
    assert respuesta.status_code == 200
    fondo = respuesta.json()
    assert fondo["evidencias"]["isin"] == "ISIN: ES0114673033"
    assert fondo["verificacion_evidencias"] == {"isin": True, "sri": False}
    assert [v["actual"] for v in fondo["historial"]] == [True, False]
    assert all(p["value"] == {"stringValue": ISIN} for _, ps in bd.consultas for p in ps)


def test_detalle_no_encontrado_e_isin_no_valido(cliente):
    bd = BaseDatosFalsa()
    assert cliente(bd).get(f"/fondos/{ISIN}").status_code == 404
    assert cliente(bd).get("/fondos/ES01146730").status_code == 422
    assert cliente(bd).get("/fondos/es0114673033").status_code == 422


def test_kid_redirige_a_enlace_temporal(cliente, monkeypatch):
    monkeypatch.setenv("BUCKET_DATOS", "bucket-datos")
    clave = "download/bestinver/20261127/bestinfond_datos_fundamentales.pdf"
    bd = BaseDatosFalsa({"SELECT clave_s3": [{"clave_s3": clave}]})
    respuesta = cliente(bd).get(f"/fondos/{ISIN}/kid", follow_redirects=False)
    assert respuesta.status_code == 307
    assert respuesta.headers["location"] == f"https://s3.example/bucket-datos/{clave}?expira=300"
    assert cliente(BaseDatosFalsa()).get(f"/fondos/{ISIN}/kid", follow_redirects=False).status_code == 404


def test_gestoras(cliente):
    fila = {
        "fuente": "azvalor",
        "nombre": "AZVALOR ASSET MANAGEMENT SGIIC, S.A.",
        "fondos": 5,
        "sri_medio": "4.20",
        "gastos_corrientes_medio": "1.718",
        "ultima_descarga": "2026-11-27 16:30:00",
    }
    respuesta = cliente(BaseDatosFalsa({"GROUP BY fuente": [fila]})).get("/gestoras")
    assert respuesta.status_code == 200
    assert respuesta.json()[0]["sri_medio"] == 4.2


def test_resumen_incluye_todos_los_niveles_de_riesgo(cliente):
    bd = BaseDatosFalsa(
        {
            "count(DISTINCT fuente)": [
                {
                    "fondos": 27,
                    "gestoras": 2,
                    "documentos": 27,
                    "ultima_actualizacion": "2026-11-27 16:30:00",
                    "isin_validos": 27,
                    "isin_comparables_web": 21,
                    "isin_coinciden_web": 21,
                }
            ],
            "GROUP BY sri": [{"sri": 3, "fondos": 15}, {"sri": 4, "fondos": 12}],
            "jsonb_each_text": [{"total": 270, "verificadas": 267}],
        }
    )
    respuesta = cliente(bd).get("/resumen")
    assert respuesta.status_code == 200
    resumen = respuesta.json()
    assert [n["fondos"] for n in resumen["distribucion_sri"]] == [0, 0, 15, 12, 0, 0, 0]
    assert resumen["calidad"]["evidencias_verificadas"] == 267


def test_base_datos_no_disponible_devuelve_503(cliente):
    class BaseDatosPausada(BaseDatosFalsa):
        def consultar(self, sql, parametros=None):
            raise BaseDatosNoDisponible("la base de datos se está reanudando tras una pausa")

    respuesta = cliente(BaseDatosPausada()).get("/fondos")
    assert respuesta.status_code == 503
    assert respuesta.headers["retry-after"] == "30"


class DataApiFalsa:
    """Cliente rds-data falso: falla con DatabaseResumingException las primeras `pausas` veces."""

    def __init__(self, pausas: int = 0):
        self.pausas = pausas
        self.llamadas = []

    def execute_statement(self, **argumentos):
        self.llamadas.append(argumentos)
        if len(self.llamadas) <= self.pausas:
            error = {"Error": {"Code": "DatabaseResumingException", "Message": "resuming"}}
            raise ClientError(error, "ExecuteStatement")
        return {"formattedRecords": json.dumps([{"isin": ISIN, "sri": 4}])}


def test_consultar_reintenta_mientras_aurora_se_reanuda():
    api = DataApiFalsa(pausas=2)
    bd = BaseDatos("arn:cluster", "arn:secreto", cliente=api, reintentos=3, espera=0)
    assert bd.consultar("SELECT 1") == [{"isin": ISIN, "sri": 4}]
    assert len(api.llamadas) == 3
    assert api.llamadas[-1]["formatRecordsAs"] == "JSON"
    assert api.llamadas[-1]["resourceArn"] == "arn:cluster"


def test_consultar_agota_los_reintentos():
    bd = BaseDatos("arn:cluster", "arn:secreto", cliente=DataApiFalsa(pausas=5), reintentos=2, espera=0)
    with pytest.raises(BaseDatosNoDisponible):
        bd.consultar("SELECT 1")


def test_handler_lambda_con_evento_de_function_url():
    # api/app.py se carga por ruta: cada etapa tiene su propio app.py
    ruta = Path(api_fondos.__file__).with_name("app.py")
    especificacion = importlib.util.spec_from_file_location("api_handler", ruta)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    evento = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": "/health",
        "rawQueryString": "",
        "headers": {"host": "abc.lambda-url.eu-west-3.on.aws"},
        "requestContext": {
            "http": {"method": "GET", "path": "/health", "protocol": "HTTP/1.1", "sourceIp": "1.2.3.4"},
            "domainName": "abc.lambda-url.eu-west-3.on.aws",
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }
    respuesta = modulo.handler(evento, None)
    assert respuesta["statusCode"] == 200
    assert json.loads(respuesta["body"]) == {"estado": "ok"}
