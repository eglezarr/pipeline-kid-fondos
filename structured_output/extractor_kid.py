"""Etapa 3: extracción de los datos del KID con un modelo de Amazon Bedrock y salida estructurada.

Lee el Markdown de  s3://<bucket>/markdown/<gestora>/<AAAAMMDD>/<slug>_datos_fundamentales.md
y guarda el JSON en s3://<bucket>/extraction/<gestora>/<AAAAMMDD>/<slug>_datos_fundamentales.json

Salida estructurada: el esquema JSON del modelo `DatosKID` se envía a Bedrock en el campo
`outputConfig.textFormat` de la Converse API (LangChain, método "json_schema"), de modo que la
respuesta cumple el esquema por construcción; no se pide "devuelve JSON" ni se parsea texto libre.

El esquema respeta los límites de Bedrock para salidas estructuradas: todos los campos están en
`required` (los que pueden faltar admiten null), como máximo 16 campos con tipo unión y sin
restricciones numéricas (minimum/maximum), que no admite. Los rangos se comprueban después en Python.

Cada campo va acompañado de su evidencia: el fragmento literal del documento del que sale. Tras la
extracción se comprueba que cada evidencia aparece en el texto, que el ISIN tiene un dígito de
control válido, que coincide con el publicado en la web (manifiesto de la etapa 1) y que el SRI está
entre 1 y 7. Es el control de que el modelo no inventa datos.

Uso:
    python structured_output/extractor_kid.py bestinver                  # todos los KID, última fecha
    python structured_output/extractor_kid.py azvalor --fecha 20261127
    python structured_output/extractor_kid.py bestinver --fondos bestinfond bestvalue
    python structured_output/extractor_kid.py bestinver --claves markdown/bestinver/20261127/x.md
"""

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath

from botocore.config import Config
from pydantic import BaseModel, Field

# Raíz del repo en el path para importar el paquete común al ejecutar el script directamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import almacenamiento_s3 as alm  # noqa: E402
from common.validaciones import isin_valido  # noqa: E402

MODELO = os.environ.get("MODELO_BEDROCK", "global.moonshotai.kimi-k3.1")
REGION_BEDROCK = os.environ.get("AWS_REGION", "eu-west-3")
# KID que se procesan a la vez (llamadas simultáneas a Bedrock)
CONCURRENCIA = int(os.environ.get("EXTRACCION_CONCURRENCIA", "2"))

DESCRIPCION_EVIDENCIA = (
    "Fragmento LITERAL del documento del que se ha extraído el campo anterior, copiado exactamente "
    "como aparece en el texto (mismas palabras, números y signos, sin traducir, resumir ni corregir). "
    "Breve: la frase o línea mínima que contiene el dato. null si el campo no aparece en el documento."
)


def evidencia(campo: str):
    """Campo de evidencia asociado a otro campo extraído (obligatorio en el esquema, admite null)."""
    return Field(..., description=f"Evidencia de '{campo}'. {DESCRIPCION_EVIDENCIA}")


class DatosKID(BaseModel):
    """Campos mínimos de un KID (Anexo A del enunciado), cada uno con su evidencia literal."""

    isin: str = Field(
        ...,
        description="Código ISIN de la clase (12 caracteres)",
        pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$",
    )
    isin_evidencia: str | None = evidencia("isin")

    nombre_producto: str = Field(..., description="Nombre del fondo tal y como aparece en el KID")
    nombre_producto_evidencia: str | None = evidencia("nombre_producto")

    nombre_clase: str | None = Field(
        ..., description="Clase o serie del fondo (p. ej. «Clase C», «P Acc EUR»); null si no se indica"
    )
    nombre_clase_evidencia: str | None = evidencia("nombre_clase")

    gestora: str = Field(..., description="Productor del PRIIP / sociedad gestora")
    gestora_evidencia: str | None = evidencia("gestora")

    fecha_documento: date | None = Field(
        ..., description="Fecha de validez o elaboración del KID (formato AAAA-MM-DD); null si no aparece"
    )
    fecha_documento_evidencia: str | None = evidencia("fecha_documento")

    sri: int = Field(..., description="Indicador resumido de riesgo (SRI), número entero de 1 a 7")
    sri_evidencia: str | None = evidencia("sri")

    periodo_mantenimiento_anios: float | None = Field(
        ..., description="Período de mantenimiento recomendado, en años; null si no aparece"
    )
    periodo_mantenimiento_anios_evidencia: str | None = evidencia("periodo_mantenimiento_anios")

    gastos_corrientes_pct: float | None = Field(
        ...,
        description=(
            "Comisiones de gestión y otros costes administrativos o de funcionamiento, en % anual "
            "(p. ej. 1.78 para un 1,78 %); null si no aparece"
        ),
    )
    gastos_corrientes_pct_evidencia: str | None = evidencia("gastos_corrientes_pct")

    costes_entrada_pct: float | None = Field(
        ..., description="Costes de entrada, en % (p. ej. 0 si se indica que no se cobran); null si no aparece"
    )
    costes_entrada_pct_evidencia: str | None = evidencia("costes_entrada_pct")

    costes_salida_pct: float | None = Field(
        ..., description="Costes de salida, en % (p. ej. 0 si se indica que no se cobran); null si no aparece"
    )
    costes_salida_pct_evidencia: str | None = evidencia("costes_salida_pct")


INSTRUCCIONES = (
    "Extrae los datos de este documento KID (Documento de Datos Fundamentales de un fondo de inversión), "
    "que está en formato Markdown. Reglas:\n"
    "- Usa solo información que aparezca en el documento. Si un dato no aparece, devuelve null: no lo "
    "deduzcas ni lo inventes.\n"
    "- Los porcentajes se devuelven como número (1,78 % -> 1.78).\n"
    "- Para cada campo, rellena su campo '_evidencia' con el fragmento copiado literalmente del texto "
    "(sin la marca Markdown) del que sale el dato.\n\n"
)


def normalizar(texto: str) -> str:
    """Quita la marca Markdown y todos los espacios para comparar fragmentos con el documento.

    Se eliminan los espacios porque el OCR y el formato Markdown parten a veces las palabras.
    """
    texto = re.sub(r"[*_~`#|>]", "", texto)
    return re.sub(r"\s+", "", texto).lower()


def verificar_evidencias(datos: dict, texto: str) -> dict[str, bool]:
    """Para cada campo con evidencia, indica si el fragmento aparece en el texto del documento."""
    texto_norm = normalizar(texto)
    resultado = {}
    for nombre, valor in datos.items():
        if nombre.endswith("_evidencia") and valor:
            resultado[nombre.removesuffix("_evidencia")] = normalizar(valor) in texto_norm
    return resultado


def validar(datos: dict, isin_web: str | None) -> dict:
    """Comprobaciones de coherencia de los datos extraídos."""
    sri = datos.get("sri")
    return {
        "isin_valido": isin_valido(datos.get("isin")),
        # None cuando la web no publica un ISIN único con el que comparar
        "isin_coincide_web": None if not isin_web else datos.get("isin") == isin_web,
        "sri_en_rango": isinstance(sri, int) and 1 <= sri <= 7,
    }


def documentos_manifiesto(s3, bucket: str, gestora: str, fecha: str) -> dict[str, dict]:
    """Documentos del manifiesto de la etapa 1, indexados por la clave del PDF ({} si no existe)."""
    clave = f"{alm.carpeta(alm.CARPETA_DESCARGA, gestora, fecha)}/{alm.NOMBRE_MANIFIESTO}"
    if not alm.existe(s3, bucket, clave):
        print(f"AVISO: no existe el manifiesto s3://{bucket}/{clave}")
        return {}
    manifiesto = json.loads(alm.leer(s3, bucket, clave))
    return {d["clave_s3"]: d for d in manifiesto.get("documentos", [])}


def crear_extractor():
    """Modelo de Bedrock con salida estructurada según el esquema DatosKID."""
    from langchain_aws import ChatBedrockConverse

    modelo = ChatBedrockConverse(
        model=MODELO,
        region_name=REGION_BEDROCK,
        max_tokens=4096,
        # La primera llamada con un esquema nuevo puede tardar hasta ~90 s (Bedrock compila la gramática)
        # Modo adaptativo: ante ThrottlingException reintenta con espera creciente y limita el ritmo
        config=Config(read_timeout=180, retries={"max_attempts": 10, "mode": "adaptive"}),
    )
    return modelo.with_structured_output(DatosKID, method="json_schema")


def extraer_kids(
    gestora: str,
    bucket: str | None = None,
    fecha: str | None = None,
    fondos: list[str] | None = None,
    claves: list[str] | None = None,
    extractor=None,
) -> dict:
    """Extrae los datos de los KID en Markdown de markdown/<gestora>/<fecha>/ y guarda los JSON en extraction/.

    `fecha` por defecto es la más reciente en markdown/. Se procesan todos los KID de la carpeta,
    los de los `fondos` indicados (slugs) o, con `claves`, los de esa lista de claves de S3 (la salida
    de la etapa 2). Devuelve un resumen con los JSON guardados (`claves`) y los fallos.
    """
    if claves is not None and fondos:
        raise ValueError("indica 'claves' o 'fondos', no los dos")

    bucket = alm.resolver_bucket(bucket)
    s3 = alm.conectar(bucket)
    fecha = alm.resolver_fecha(s3, bucket, alm.CARPETA_MARKDOWN, gestora, fecha)
    origen = alm.carpeta(alm.CARPETA_MARKDOWN, gestora, fecha)
    destino = alm.carpeta(alm.CARPETA_EXTRACCION, gestora, fecha)
    print(f"Origen:  s3://{bucket}/{origen}/")
    print(f"Destino: s3://{bucket}/{destino}/")
    print(f"Modelo:  {MODELO}\n")

    sufijo_kid = f"_{alm.TIPO_KID}"
    if claves is not None:
        claves_md = [
            c
            for c in claves
            if str(PurePosixPath(c).parent) == origen
            and c.endswith(".md")
            and PurePosixPath(c).stem.endswith(sufijo_kid)
        ]
    elif fondos:
        claves_md = [f"{origen}/{slug}{sufijo_kid}.md" for slug in fondos]
    else:
        claves_md = [
            c for c in alm.listar_claves(s3, bucket, origen, ".md") if PurePosixPath(c).stem.endswith(sufijo_kid)
        ]
    if not claves_md:
        raise alm.ErrorEtapa(f"no hay ningún KID en Markdown que procesar en s3://{bucket}/{origen}/")

    manifiesto = documentos_manifiesto(s3, bucket, gestora, fecha)
    extractor = extractor or crear_extractor()

    def procesar(clave_md: str) -> tuple[str, str]:
        """Extrae un KID y guarda su JSON. Devuelve la clave del JSON y una línea de resumen."""
        stem = PurePosixPath(clave_md).stem
        clave_json = f"{destino}/{stem}.json"
        clave_pdf = f"{alm.carpeta(alm.CARPETA_DESCARGA, gestora, fecha)}/{stem}.pdf"
        documento = manifiesto.get(clave_pdf)
        texto = alm.leer(s3, bucket, clave_md).decode("utf-8")
        datos = extractor.invoke(INSTRUCCIONES + texto).model_dump(mode="json")
        verificacion = verificar_evidencias(datos, texto)
        validaciones = validar(datos, (documento or {}).get("isin_web"))
        resultado = {
            "gestora": gestora,
            "fecha": fecha,
            "markdown_origen": clave_md,
            "documento": documento,
            "modelo": MODELO,
            "fecha_extraccion": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "datos": datos,
            "verificacion_evidencias": verificacion,
            "validaciones": validaciones,
        }
        alm.escribir(
            s3,
            bucket,
            clave_json,
            json.dumps(resultado, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json; charset=utf-8",
            {"markdown-origen": clave_md},
        )
        no_verificadas = [campo for campo, ok in verificacion.items() if not ok]
        fallidas = [nombre for nombre, ok in validaciones.items() if ok is False]
        linea = (
            f"{stem}: {datos['nombre_producto']} ({datos['isin']}), SRI {datos['sri']}"
            f" | evidencias no encontradas: {no_verificadas or 'ninguna'}"
            f" | validaciones fallidas: {fallidas or 'ninguna'}"
        )
        return clave_json, linea

    # Varios KID en paralelo: cada llamada a Bedrock tarda varios segundos
    extraidos, fallos = [], []
    with ThreadPoolExecutor(max_workers=CONCURRENCIA) as ejecutor:
        futuros = {ejecutor.submit(procesar, clave_md): clave_md for clave_md in claves_md}
        for futuro in as_completed(futuros):
            clave_md = futuros[futuro]
            try:
                clave_json, linea = futuro.result()
            except Exception as error:  # un KID que falle no debe parar el resto
                print(f"[error] {PurePosixPath(clave_md).name}: {error}")
                fallos.append({"fichero": PurePosixPath(clave_md).name, "error": str(error)})
                continue
            print(f"[ok] {linea}")
            extraidos.append(clave_json)
    extraidos.sort()

    print(f"\nResumen: {len(extraidos)} extraídos, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo['fichero']}: {fallo['error']}")
    if not extraidos:
        raise alm.ErrorEtapa("no se ha podido extraer ningún KID")
    return {
        "bucket": bucket,
        "gestora": gestora,
        "fecha": fecha,
        "origen": origen,
        "destino": destino,
        "claves": extraidos,
        "fallos": fallos,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gestora", help="Gestora (carpeta dentro de markdown/)")
    parser.add_argument("--fondos", nargs="+", help="Slugs de los fondos a procesar (por defecto, todos)")
    parser.add_argument("--claves", nargs="+", help="Claves de S3 de los Markdown a procesar")
    parser.add_argument("--bucket", help=f"Bucket de S3 (por defecto, la variable {alm.VARIABLE_BUCKET})")
    parser.add_argument("--fecha", type=alm.fecha_valida, help="Carpeta AAAAMMDD (por defecto, la más reciente)")
    args = parser.parse_args()
    if args.claves and args.fondos:
        parser.error("indica --claves o --fondos, no los dos")

    try:
        resumen = extraer_kids(args.gestora, args.bucket, args.fecha, args.fondos, args.claves)
    except alm.ErrorEtapa as e:
        print(f"[error] {e}")
        return 1
    return 1 if resumen["fallos"] else 0


if __name__ == "__main__":
    sys.exit(main())
