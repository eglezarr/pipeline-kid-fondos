"""Tests de las utilidades comunes a todas las etapas."""

import pytest

from common import almacenamiento_s3 as alm


def test_fallos_acumulados():
    # Respuesta de la etapa 3 que ya traía un fallo de la etapa 1
    evento = {
        "fallos_previos": [{"etapa": "descarga", "fondo": "X", "error": "timeout"}],
        "fallos": [{"fichero": "y.md", "error": "ThrottlingException"}],
    }
    assert alm.fallos_acumulados(evento, "extraccion") == [
        {"etapa": "descarga", "fondo": "X", "error": "timeout"},
        {"etapa": "extraccion", "fichero": "y.md", "error": "ThrottlingException"},
    ]
    assert alm.fallos_acumulados({}, "descarga") == []


def test_evento_lambda_destinations():
    # Con Lambda Destinations la salida de la etapa anterior llega dentro de responsePayload
    assert alm.evento_lambda({"responsePayload": {"gestora": "azvalor"}}) == {"gestora": "azvalor"}
    assert alm.evento_lambda({"gestora": "azvalor"}) == {"gestora": "azvalor"}


def test_comprobar_fecha():
    assert alm.comprobar_fecha("20261127") == "20261127"
    with pytest.raises(ValueError):
        alm.comprobar_fecha("2026-11-27")


def test_resolver_bucket(monkeypatch):
    monkeypatch.setenv(alm.VARIABLE_BUCKET, "bucket-entorno")
    assert alm.resolver_bucket(None) == "bucket-entorno"
    assert alm.resolver_bucket("otro") == "otro"
    monkeypatch.delenv(alm.VARIABLE_BUCKET)
    with pytest.raises(alm.ErrorEtapa):
        alm.resolver_bucket(None)
