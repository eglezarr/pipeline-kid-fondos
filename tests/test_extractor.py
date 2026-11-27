"""Tests de la etapa 3: esquema compatible con Bedrock, validaciones y JSON de salida."""

import json

import pytest

import extractor_kid
from common import almacenamiento_s3 as alm
from extractor_kid import DatosKID, validar, verificar_evidencias

DATOS = {
    "isin": "ES0114673033",
    "isin_evidencia": "ISIN: ES0114673033",
    "nombre_producto": "Bestinfond, F.I.",
    "nombre_producto_evidencia": "Producto: **Bestinfond, F.I.**",
    "nombre_clase": None,
    "nombre_clase_evidencia": None,
    "gestora": "Bestinver Gestión, S.A., SGIIC",
    "gestora_evidencia": "Bestinver Gestión, S.A., SGIIC",
    "fecha_documento": "2026-02-13",
    "fecha_documento_evidencia": "13/02/2026",
    "sri": 4,
    "sri_evidencia": "en la clase de riesgo 4",
    "periodo_mantenimiento_anios": 5.0,
    "periodo_mantenimiento_anios_evidencia": "Período de mantenimiento recomendado: 5 años",
    "gastos_corrientes_pct": 1.78,
    "gastos_corrientes_pct_evidencia": "1,78 % del valor de su inversión por año",
    "costes_entrada_pct": 0.0,
    "costes_entrada_pct_evidencia": "No cobramos comisión de entrada",
    "costes_salida_pct": 0.0,
    "costes_salida_pct_evidencia": "No cobramos una comisión de salida",
}

MARKDOWN = """# Documento de datos fundamentales
Producto: **Bestinfond, F.I.** | ISIN: ES0114673033 | Bestinver Gestión, S.A., SGIIC
Fecha: 13/02/2026. Hemos clasificado este producto en la clase de riesgo 4.
Período de mantenimiento recomendado: 5 años
| Costes de entrada | No cobramos comisión de entrada |
| Costes de salida | No cobramos una   comisión de salida |
Costes corrientes: 1,78 % del valor de su inversión por año
"""


def _recorrer(nodo):
    """Recorre todos los diccionarios anidados de un esquema JSON."""
    if isinstance(nodo, dict):
        yield nodo
        for valor in nodo.values():
            yield from _recorrer(valor)
    elif isinstance(nodo, list):
        for valor in nodo:
            yield from _recorrer(valor)


def test_esquema_dentro_de_los_limites_de_bedrock():
    esquema = DatosKID.model_json_schema()
    propiedades = esquema["properties"]
    # Todos los campos en "required": 0 opcionales (el límite de Bedrock es 12)
    assert set(esquema["required"]) == set(propiedades)
    # Campos con tipo unión (anyOf / lista de tipos): como máximo 16
    uniones = [p for p in propiedades.values() if "anyOf" in p or isinstance(p.get("type"), list)]
    assert len(uniones) <= 16
    # Bedrock no admite restricciones numéricas ni de longitud
    no_admitidas = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength"}
    assert not any(no_admitidas & set(nodo) for nodo in _recorrer(esquema))


def test_campos_del_anexo_a():
    obligatorios = {
        "isin", "nombre_producto", "nombre_clase", "gestora", "fecha_documento", "sri",
        "periodo_mantenimiento_anios", "gastos_corrientes_pct", "costes_entrada_pct", "costes_salida_pct",
    }  # fmt: skip
    assert obligatorios <= set(DatosKID.model_fields)


def test_verificar_evidencias_ignora_markdown_y_espacios():
    verificacion = verificar_evidencias(DATOS, MARKDOWN)
    assert verificacion["nombre_producto"] and verificacion["costes_salida_pct"]
    assert "nombre_clase" not in verificacion  # sin evidencia (null): no se comprueba
    inventada = dict(DATOS, sri_evidencia="clase de riesgo 6")
    assert verificar_evidencias(inventada, MARKDOWN)["sri"] is False


def test_validar():
    assert validar(DATOS, "ES0114673033") == {"isin_valido": True, "isin_coincide_web": True, "sri_en_rango": True}
    assert validar(DATOS, None)["isin_coincide_web"] is None
    assert validar(DATOS, "ES0112611001")["isin_coincide_web"] is False
    assert validar(dict(DATOS, isin="ES0114673034", sri=9), None) == {
        "isin_valido": False,
        "isin_coincide_web": None,
        "sri_en_rango": False,
    }


class ExtractorFalso:
    """Sustituye al modelo de Bedrock: devuelve siempre los mismos datos."""

    def invoke(self, texto):
        return DatosKID(**DATOS)


@pytest.fixture
def s3_simulado(monkeypatch):
    clave_md = "markdown/bestinver/20261127/bestinfond_datos_fundamentales.md"
    clave_pdf = "download/bestinver/20261127/bestinfond_datos_fundamentales.pdf"
    manifiesto = {"documentos": [{"clave_s3": clave_pdf, "isin_web": "ES0114673033", "sha256": "abc"}]}
    objetos = {
        clave_md: MARKDOWN.encode("utf-8"),
        "download/bestinver/20261127/manifiesto.json": json.dumps(manifiesto).encode("utf-8"),
    }

    def escribir(s3, bucket, clave, contenido, tipo, metadatos=None):
        objetos[clave] = contenido

    monkeypatch.setattr(alm, "conectar", lambda bucket: object())
    monkeypatch.setattr(alm, "listar_claves", lambda s3, b, carpeta, ext: [c for c in objetos if c.endswith(ext)])
    monkeypatch.setattr(alm, "existe", lambda s3, b, clave: clave in objetos)
    monkeypatch.setattr(alm, "leer", lambda s3, b, clave: objetos[clave])
    monkeypatch.setattr(alm, "escribir", escribir)
    return objetos


def test_extraer_kids_guarda_json_enriquecido(s3_simulado):
    resumen = extractor_kid.extraer_kids(
        "bestinver", bucket="bucket-prueba", fecha="20261127", extractor=ExtractorFalso()
    )
    clave_json = "extraction/bestinver/20261127/bestinfond_datos_fundamentales.json"
    assert resumen["claves"] == [clave_json] and not resumen["fallos"]

    resultado = json.loads(s3_simulado[clave_json])
    assert resultado["datos"]["isin"] == "ES0114673033"
    assert resultado["documento"]["sha256"] == "abc"  # datos de origen del manifiesto
    assert resultado["validaciones"] == {"isin_valido": True, "isin_coincide_web": True, "sri_en_rango": True}
    assert all(resultado["verificacion_evidencias"].values())
