"""API HTTP de consulta de los KID cargados en PostgreSQL (Aurora).

Es la única vía de acceso a los datos junto con la aplicación web (que a su vez usa esta API).
Solo lectura: las consultas parten de la vista `kid_actual` (versión más reciente de cada ISIN)
y de las tablas `kid` y `documentos` para el historial.

Rutas:
    GET /                    índice de la API
    GET /health              estado del servicio (no consulta la base de datos)
    GET /fondos              fondos con filtros (fuente, SRI, texto) y orden
    GET /fondos/{isin}       detalle: datos, evidencias, validaciones e historial de versiones
    GET /fondos/{isin}/kid   redirige al PDF original mediante un enlace temporal de S3
    GET /gestoras            fondos, SRI medio y gastos medios por gestora
    GET /resumen             totales, distribución del SRI e indicadores de calidad
    GET /docs                documentación interactiva (OpenAPI)

En Lambda la sirve Mangum (app.py); en local, desde la raíz del repo:
    python -m uvicorn api_fondos:app --app-dir api
"""

import json
import os
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, Literal

import boto3
from botocore.config import Config
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from common.base_datos import BaseDatos, BaseDatosNoDisponible, parametro

# Aurora en pausa tarda unos segundos en reanudarse: la API reintenta durante ~40 s
# (la función tiene 60 s de timeout) y, si no responde, devuelve 503 para que el cliente reintente.
REINTENTOS_BD = 8
ESPERA_BD = 5
SEGUNDOS_ENLACE_KID = 300  # validez del enlace temporal al PDF

PATRON_ISIN = r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$"

# Orden admitido en /fondos: lista cerrada, nunca se concatena texto del usuario en el SQL
ORDENES = {
    "nombre": "nombre_producto, nombre_clase NULLS FIRST",
    "sri": "sri, nombre_producto",
    "gastos": "gastos_corrientes_pct NULLS LAST, nombre_producto",
    "isin": "isin",
}

COLUMNAS_FONDO = """
       isin, nombre_producto, nombre_clase, gestora, fuente, fecha_documento, sri,
       periodo_mantenimiento_anios, gastos_corrientes_pct, costes_entrada_pct, costes_salida_pct,
       validaciones, ultima_descarga"""

SQL_DETALLE = f"""
SELECT {COLUMNAS_FONDO},
       evidencias, verificacion_evidencias, modelo, fecha_extraccion,
       documento_id, url_origen, url_ficha, primera_descarga
  FROM kid_actual
 WHERE isin = :isin
"""

SQL_HISTORIAL = """
SELECT k.documento_id, k.fecha_documento, k.sri, k.gastos_corrientes_pct,
       d.primera_descarga, d.ultima_descarga
  FROM kid k
  JOIN documentos d ON d.id = k.documento_id
 WHERE k.isin = :isin
 ORDER BY k.fecha_documento DESC NULLS LAST, d.ultima_descarga DESC
"""

SQL_CLAVE_KID = "SELECT clave_s3 FROM kid_actual WHERE isin = :isin"

# `gestora` en la vista es el productor según el KID; `fuente`, la web de la que se capturó
SQL_GESTORAS = """
SELECT fuente,
       mode() WITHIN GROUP (ORDER BY gestora) AS nombre,
       count(*) AS fondos,
       round(avg(sri), 2) AS sri_medio,
       round(avg(gastos_corrientes_pct), 3) AS gastos_corrientes_medio,
       max(ultima_descarga) AS ultima_descarga
  FROM kid_actual
 GROUP BY fuente
 ORDER BY fuente
"""

# `->>` devuelve NULL cuando el valor JSON es null (ISIN sin referencia en la web)
SQL_TOTALES = """
SELECT count(*) AS fondos,
       count(DISTINCT fuente) AS gestoras,
       (SELECT count(*) FROM documentos) AS documentos,
       max(ultima_descarga) AS ultima_actualizacion,
       count(*) FILTER (WHERE validaciones->>'isin_valido' = 'true') AS isin_validos,
       count(validaciones->>'isin_coincide_web') AS isin_comparables_web,
       count(*) FILTER (WHERE validaciones->>'isin_coincide_web' = 'true') AS isin_coinciden_web
  FROM kid_actual
"""

SQL_DISTRIBUCION_SRI = "SELECT sri, count(*) AS fondos FROM kid_actual GROUP BY sri"

SQL_EVIDENCIAS = """
SELECT count(*) AS total,
       count(*) FILTER (WHERE e.value = 'true') AS verificadas
  FROM kid_actual k
 CROSS JOIN LATERAL jsonb_each_text(k.verificacion_evidencias) AS e
"""


# ---------------------------------------------------------------------------------------------
# Modelos de respuesta (definen el contrato de la API y la documentación de /docs)
# ---------------------------------------------------------------------------------------------


class Validaciones(BaseModel):
    isin_valido: bool | None = Field(None, description="El ISIN cumple el formato y el dígito de control")
    isin_coincide_web: bool | None = Field(
        None, description="Coincide con el ISIN publicado en la web (null si la web no lo publica)"
    )
    sri_en_rango: bool | None = Field(None, description="SRI entre 1 y 7")


class Fondo(BaseModel):
    isin: str
    nombre_producto: str
    nombre_clase: str | None
    gestora: str = Field(description="Productor del PRIIP según el KID")
    fuente: str = Field(description="Web de la gestora de la que se capturó el KID")
    fecha_documento: date | None
    sri: int = Field(description="Indicador resumido de riesgo (1 a 7)")
    periodo_mantenimiento_anios: float | None
    gastos_corrientes_pct: float | None
    costes_entrada_pct: float | None
    costes_salida_pct: float | None
    validaciones: Validaciones
    ultima_descarga: datetime


class VersionKID(BaseModel):
    documento_id: int
    fecha_documento: date | None
    sri: int
    gastos_corrientes_pct: float | None
    primera_descarga: datetime
    ultima_descarga: datetime
    actual: bool = Field(description="Es la versión que se muestra en /fondos")


class FondoDetalle(Fondo):
    evidencias: dict[str, str | None] = Field(description="Fragmento literal del KID que respalda cada campo")
    verificacion_evidencias: dict[str, bool] = Field(description="Si cada fragmento aparece en el documento")
    modelo: str = Field(description="Modelo de Bedrock que hizo la extracción")
    fecha_extraccion: datetime
    documento_id: int
    url_origen: str = Field(description="URL del PDF en la web de la gestora")
    url_ficha: str | None = Field(description="Página del fondo en la web de la gestora")
    primera_descarga: datetime
    historial: list[VersionKID]


class Gestora(BaseModel):
    fuente: str
    nombre: str = Field(description="Nombre de la gestora según los KID")
    fondos: int
    sri_medio: float
    gastos_corrientes_medio: float | None
    ultima_descarga: datetime


class ConteoSRI(BaseModel):
    sri: int
    fondos: int


class Calidad(BaseModel):
    isin_validos: int
    isin_comparables_web: int = Field(description="Fondos cuya web publica un ISIN único")
    isin_coinciden_web: int
    evidencias_total: int
    evidencias_verificadas: int


class Resumen(BaseModel):
    fondos: int
    documentos: int
    gestoras: int
    ultima_actualizacion: datetime | None
    distribucion_sri: list[ConteoSRI]
    calidad: Calidad


# ---------------------------------------------------------------------------------------------
# Acceso a datos
# ---------------------------------------------------------------------------------------------


def _json(valor):
    """La Data API devuelve las columnas JSONB como texto."""
    return json.loads(valor) if isinstance(valor, str) else valor


def _fila_fondo(fila: dict) -> dict:
    for columna in ("validaciones", "evidencias", "verificacion_evidencias"):
        if columna in fila:
            fila[columna] = _json(fila[columna]) or {}
    return fila


def _patron_like(texto: str) -> str:
    """Patrón ILIKE que busca el texto literal (escapa los comodines % y _)."""
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


class Repositorio:
    """Consultas de solo lectura sobre la base de datos de los KID."""

    def __init__(self, bd: BaseDatos):
        self.bd = bd

    def fondos(
        self,
        fuente: str | None = None,
        sri_min: int | None = None,
        sri_max: int | None = None,
        texto: str | None = None,
        orden: str = "nombre",
    ) -> list[dict]:
        # Solo se añaden las condiciones de los filtros indicados; los valores van siempre como parámetros
        condiciones, parametros = [], []
        if fuente:
            condiciones.append("fuente = :fuente")
            parametros.append(parametro("fuente", fuente))
        if sri_min is not None:
            condiciones.append("sri >= :sri_min")
            parametros.append(parametro("sri_min", sri_min))
        if sri_max is not None:
            condiciones.append("sri <= :sri_max")
            parametros.append(parametro("sri_max", sri_max))
        if texto:
            # un único parámetro: se busca en el ISIN y en los nombres concatenados
            condiciones.append("concat_ws(' ', isin, nombre_producto, nombre_clase) ILIKE :texto")
            parametros.append(parametro("texto", _patron_like(texto)))
        where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""
        sql = f"SELECT {COLUMNAS_FONDO}\n  FROM kid_actual{where}\n ORDER BY {ORDENES[orden]}"
        return [_fila_fondo(f) for f in self.bd.consultar(sql, parametros)]

    def detalle(self, isin: str) -> dict | None:
        filas = self.bd.consultar(SQL_DETALLE, [parametro("isin", isin)])
        if not filas:
            return None
        fondo = _fila_fondo(filas[0])
        historial = self.bd.consultar(SQL_HISTORIAL, [parametro("isin", isin)])
        fondo["historial"] = [v | {"actual": v["documento_id"] == fondo["documento_id"]} for v in historial]
        return fondo

    def clave_kid(self, isin: str) -> str | None:
        filas = self.bd.consultar(SQL_CLAVE_KID, [parametro("isin", isin)])
        return filas[0]["clave_s3"] if filas else None

    def gestoras(self) -> list[dict]:
        return self.bd.consultar(SQL_GESTORAS)

    def resumen(self) -> dict:
        totales = self.bd.consultar(SQL_TOTALES)[0]
        conteos = {f["sri"]: f["fondos"] for f in self.bd.consultar(SQL_DISTRIBUCION_SRI)}
        evidencias = self.bd.consultar(SQL_EVIDENCIAS)[0]
        return {
            "fondos": totales["fondos"],
            "documentos": totales["documentos"],
            "gestoras": totales["gestoras"],
            "ultima_actualizacion": totales["ultima_actualizacion"],
            # todos los niveles del 1 al 7, también los que no tienen fondos
            "distribucion_sri": [{"sri": n, "fondos": conteos.get(n, 0)} for n in range(1, 8)],
            "calidad": {
                "isin_validos": totales["isin_validos"],
                "isin_comparables_web": totales["isin_comparables_web"],
                "isin_coinciden_web": totales["isin_coinciden_web"],
                "evidencias_total": evidencias["total"],
                "evidencias_verificadas": evidencias["verificadas"],
            },
        }


@lru_cache
def obtener_repositorio() -> Repositorio:
    return Repositorio(BaseDatos.desde_entorno(reintentos=REINTENTOS_BD, espera=ESPERA_BD))


@lru_cache
def obtener_s3():
    # Firma v4 y endpoint regional: los enlaces temporales funcionan en cualquier región
    return boto3.client("s3", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))


RepositorioDep = Annotated[Repositorio, Depends(obtener_repositorio)]
S3Dep = Annotated[object, Depends(obtener_s3)]
IsinPath = Annotated[str, Path(pattern=PATRON_ISIN, description="ISIN en mayúsculas", examples=["ES0116567035"])]


# ---------------------------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------------------------

app = FastAPI(
    title="API de KIDs de fondos",
    description=(
        "Datos extraídos de los documentos de datos fundamentales (KID) de los fondos de Bestinver "
        "y Azvalor: indicador de riesgo, periodo de mantenimiento y costes, con la evidencia literal "
        "de cada dato y sus validaciones. Se actualiza el día 15 de cada mes."
    ),
    version="1.0.0",
)


@app.exception_handler(BaseDatosNoDisponible)
def base_datos_no_disponible(request: Request, exc: BaseDatosNoDisponible) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": f"Base de datos no disponible: {exc}. Vuelve a intentarlo en unos segundos."},
        headers={"Retry-After": "30"},
    )


@app.get("/", include_in_schema=False)
def indice() -> dict:
    return {
        "api": app.title,
        "documentacion": "/docs",
        "rutas": ["/health", "/fondos", "/fondos/{isin}", "/fondos/{isin}/kid", "/gestoras", "/resumen"],
    }


@app.get("/health", summary="Estado del servicio")
def health() -> dict[str, str]:
    # No consulta la base de datos: no la despierta si está en pausa
    return {"estado": "ok"}


@app.get("/fondos", response_model=list[Fondo], summary="Fondos con su último KID")
def listar_fondos(
    repo: RepositorioDep,
    fuente: Annotated[
        str | None, Query(pattern=r"^[a-z0-9-]+$", max_length=40, description="bestinver, azvalor...")
    ] = None,
    sri_min: Annotated[int | None, Query(ge=1, le=7)] = None,
    sri_max: Annotated[int | None, Query(ge=1, le=7)] = None,
    texto: Annotated[str | None, Query(max_length=100, description="Busca en el ISIN y en el nombre")] = None,
    orden: Literal["nombre", "sri", "gastos", "isin"] = "nombre",
):
    if sri_min is not None and sri_max is not None and sri_min > sri_max:
        raise HTTPException(status_code=422, detail="sri_min no puede ser mayor que sri_max")
    return repo.fondos(fuente=fuente, sri_min=sri_min, sri_max=sri_max, texto=texto, orden=orden)


@app.get("/fondos/{isin}", response_model=FondoDetalle, summary="Detalle de un fondo")
def detalle_fondo(isin: IsinPath, repo: RepositorioDep):
    fondo = repo.detalle(isin)
    if fondo is None:
        raise HTTPException(status_code=404, detail=f"No hay ningún KID con ISIN {isin}")
    return fondo


@app.get(
    "/fondos/{isin}/kid",
    status_code=307,
    response_class=RedirectResponse,
    summary="PDF original del KID",
    description=f"Redirige a un enlace temporal de S3 (válido {SEGUNDOS_ENLACE_KID} s) al PDF capturado.",
)
def documento_kid(isin: IsinPath, repo: RepositorioDep, s3: S3Dep):
    bucket = os.environ.get("BUCKET_DATOS")
    if not bucket:
        raise HTTPException(status_code=500, detail="Falta la variable de entorno BUCKET_DATOS")
    clave = repo.clave_kid(isin)
    if clave is None:
        raise HTTPException(status_code=404, detail=f"No hay ningún KID con ISIN {isin}")
    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": clave,
            "ResponseContentType": "application/pdf",
            "ResponseContentDisposition": f'inline; filename="{isin}.pdf"',
        },
        ExpiresIn=SEGUNDOS_ENLACE_KID,
    )
    return RedirectResponse(url, status_code=307)


@app.get("/gestoras", response_model=list[Gestora], summary="Resumen por gestora")
def listar_gestoras(repo: RepositorioDep):
    return repo.gestoras()


@app.get("/resumen", response_model=Resumen, summary="Totales e indicadores de calidad")
def resumen(repo: RepositorioDep):
    return repo.resumen()
