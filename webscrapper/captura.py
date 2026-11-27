"""Etapa 1: captura de los KID de una gestora y almacenamiento en S3 con su manifiesto.

Para la gestora indicada:
  1. Localiza los KID publicados en su web (módulo gestora_<nombre>.py).
  2. Descarga cada PDF, comprueba que es un PDF y calcula su huella sha256.
  3. Lo sube a  s3://<bucket>/download/<gestora>/<AAAAMMDD>/<slug>_datos_fundamentales.pdf
  4. Guarda   s3://<bucket>/download/<gestora>/<AAAAMMDD>/manifiesto.json  con, por documento,
     de dónde viene (ficha y URL del PDF) y cuándo se descargó, más la huella y el tamaño.

Devuelve un resumen cuyo campo `claves` (PDF subidos) es la entrada de la etapa 2.

Uso:
    python webscrapper/captura.py bestinver                  # bucket de la variable BUCKET_DATOS
    python webscrapper/captura.py azvalor --fecha 20261127
    python webscrapper/captura.py bestinver --localizar      # solo lista los KID, sin descargar
    python webscrapper/captura.py azvalor --bucket otro-bucket --delay 2
"""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import requests
from botocore.exceptions import BotoCoreError, ClientError

# Raíz del repo en el path para importar el paquete común al ejecutar el script directamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gestora_azvalor  # noqa: E402
import gestora_bestinver  # noqa: E402
from common import almacenamiento_s3 as alm  # noqa: E402
from utilidades_web import Navegador  # noqa: E402

# Gestoras disponibles: nombre -> módulo con localizar_kids(nav)
GESTORAS = {
    gestora_bestinver.NOMBRE: gestora_bestinver,
    gestora_azvalor.NOMBRE: gestora_azvalor,
}


def ahora_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def capturar(
    gestora: str,
    bucket: str | None = None,
    fecha: str | None = None,
    delay: float = 1.0,
    navegador: Navegador | None = None,
) -> dict:
    """Descarga los KID de la gestora, los sube a S3 y guarda el manifiesto de la ejecución.

    `fecha` (AAAAMMDD) es la carpeta de destino; por defecto, el día de hoy en UTC.
    Lanza ErrorEtapa si no se ha podido guardar ningún KID.
    """
    if gestora not in GESTORAS:
        raise ValueError(f"gestora desconocida '{gestora}', opciones: {', '.join(GESTORAS)}")
    bucket = alm.resolver_bucket(bucket)
    fecha = alm.comprobar_fecha(fecha) if fecha else datetime.now(UTC).strftime("%Y%m%d")
    carpeta_s3 = alm.carpeta(alm.CARPETA_DESCARGA, gestora, fecha)
    s3 = alm.conectar(bucket)
    print(f"Destino: s3://{bucket}/{carpeta_s3}/\n")

    inicio = ahora_utc()
    nav = navegador or Navegador(delay)
    kids, incidencias = GESTORAS[gestora].localizar_kids(nav)
    print(f"{len(kids)} KID localizados\n")

    documentos, fallos = [], []
    for kid in kids:
        clave = f"{carpeta_s3}/{kid.slug}_{alm.TIPO_KID}.pdf"
        try:
            contenido = nav.descargar_pdf(kid.url_origen)
        except (requests.RequestException, PermissionError, ValueError) as e:
            print(f"  [error] {kid.fondo}: {e}")
            fallos.append({"fondo": kid.fondo, "url": kid.url_origen, "error": str(e)})
            continue

        descargado = ahora_utc()
        huella = hashlib.sha256(contenido).hexdigest()
        try:
            alm.escribir(
                s3,
                bucket,
                clave,
                contenido,
                "application/pdf",
                {  # los metadatos de S3 solo admiten ASCII
                    "url-origen": quote(kid.url_origen, safe=":/?=&%#"),
                    "fecha-descarga": descargado,
                    "sha256": huella,
                },
            )
        except (BotoCoreError, ClientError) as e:
            print(f"  [error] {kid.fondo}: subida a S3: {e}")
            fallos.append({"fondo": kid.fondo, "url": kid.url_origen, "error": f"subida a S3: {e}"})
            continue

        print(f"  [ok] {kid.fondo} -> s3://{bucket}/{clave}")
        documentos.append(
            {
                **asdict(kid),
                "clave_s3": clave,
                "fecha_descarga": descargado,
                "sha256": huella,
                "tamano_bytes": len(contenido),
            }
        )

    clave_manifiesto = f"{carpeta_s3}/{alm.NOMBRE_MANIFIESTO}"
    manifiesto = {
        "gestora": gestora,
        "fecha": fecha,
        "inicio": inicio,
        "fin": ahora_utc(),
        "documentos": documentos,
        "incidencias": incidencias,
        "fallos": fallos,
    }
    alm.escribir(
        s3,
        bucket,
        clave_manifiesto,
        json.dumps(manifiesto, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json; charset=utf-8",
    )

    print(f"\nResumen: {len(documentos)} KID guardados, {len(incidencias)} fichas sin KID, {len(fallos)} fallos")
    for incidencia in incidencias:
        print(f"  - {incidencia['fondo']}: {incidencia['detalle']}")
    print(f"Manifiesto: s3://{bucket}/{clave_manifiesto}")

    if not documentos:
        raise alm.ErrorEtapa(f"no se ha guardado ningún KID de {gestora}: revisa si ha cambiado la web")
    return {
        "bucket": bucket,
        "gestora": gestora,
        "fecha": fecha,
        "carpeta": carpeta_s3,
        "manifiesto": clave_manifiesto,
        "claves": [d["clave_s3"] for d in documentos],
        "incidencias": incidencias,
        "fallos": fallos,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gestora", choices=GESTORAS, help="Gestora cuyos KID se capturan")
    parser.add_argument("--bucket", help=f"Bucket de S3 (por defecto, la variable {alm.VARIABLE_BUCKET})")
    parser.add_argument("--fecha", type=alm.fecha_valida, help="Carpeta de fecha AAAAMMDD (por defecto, hoy)")
    parser.add_argument("--delay", type=float, default=1.0, help="Segundos entre peticiones (por defecto 1)")
    parser.add_argument("--localizar", action="store_true", help="Solo lista los KID publicados, sin descargarlos")
    args = parser.parse_args()

    if args.localizar:
        kids, incidencias = GESTORAS[args.gestora].localizar_kids(Navegador(args.delay))
        for kid in kids:
            print(f"- {kid.fondo} [{kid.isin_web or 'ISIN no encontrado'}]\n    {kid.url_origen}")
        for incidencia in incidencias:
            print(f"* {incidencia['fondo']}: {incidencia['detalle']}")
        return 0 if kids else 1

    try:
        resumen = capturar(args.gestora, args.bucket, args.fecha, args.delay)
    except alm.ErrorEtapa as e:
        print(f"[error] {e}")
        return 1
    return 1 if resumen["fallos"] else 0


if __name__ == "__main__":
    sys.exit(main())
