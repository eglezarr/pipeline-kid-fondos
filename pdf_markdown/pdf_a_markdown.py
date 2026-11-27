"""Etapa 2: transformación de los KID descargados (PDF) a Markdown con PyMuPDF.

Lee los PDF de  s3://<bucket>/download/<gestora>/<AAAAMMDD>/<slug>_<tipo>.pdf
y guarda en     s3://<bucket>/markdown/<gestora>/<AAAAMMDD>/<slug>_<tipo>.md

Usa pymupdf4llm, que conserva la estructura del documento (títulos, listas y tablas: las de
costes y escenarios salen como tablas Markdown) y aplica OCR (RapidOCR) solo en las páginas que
lo necesitan. El Markdown es la entrada del modelo de lenguaje en la etapa 3: un texto limpio y
con las tablas preservadas facilita una extracción fiable.

Uso:
    python pdf_markdown/pdf_a_markdown.py bestinver                       # última fecha descargada
    python pdf_markdown/pdf_a_markdown.py azvalor --fecha 20261127
    python pdf_markdown/pdf_a_markdown.py bestinver bestinfond_datos_fundamentales.pdf
    python pdf_markdown/pdf_a_markdown.py bestinver --claves download/bestinver/20261127/x.pdf
    python pdf_markdown/pdf_a_markdown.py bestinver --ocr siempre --sobrescribir
"""

import argparse
import sys
from pathlib import Path, PurePosixPath

import pymupdf
import pymupdf4llm

# Raíz del repo en el path para importar el paquete común al ejecutar el script directamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import almacenamiento_s3 as alm  # noqa: E402

# Modos de OCR de la línea de comandos -> argumentos de pymupdf4llm.to_markdown
MODOS_OCR = {
    "auto": {"use_ocr": True, "force_ocr": False},  # OCR solo en las páginas que lo necesitan
    "siempre": {"use_ocr": True, "force_ocr": True},
    "nunca": {"use_ocr": False, "force_ocr": False},
}


def pdf_a_markdown(contenido_pdf: bytes, modo_ocr: str = "auto", idioma: str = "spa") -> str:
    """Convierte un PDF (en memoria) a texto Markdown."""
    with pymupdf.open(stream=contenido_pdf, filetype="pdf") as doc:
        return pymupdf4llm.to_markdown(
            doc,
            ocr_language=idioma,
            show_progress=False,
            **MODOS_OCR[modo_ocr],
        )


def convertir_pdfs(
    gestora: str,
    bucket: str | None = None,
    fecha: str | None = None,
    ficheros: list[str] | None = None,
    modo_ocr: str = "auto",
    idioma: str = "spa",
    sobrescribir: bool = False,
    claves: list[str] | None = None,
) -> dict:
    """Convierte a Markdown los PDF de download/<gestora>/<fecha>/ y los sube a markdown/.

    `fecha` por defecto es la más reciente en download/. Para no convertir toda la carpeta,
    `ficheros` limita la conversión a esos nombres de PDF y `claves` a esas claves de S3
    (la salida de la etapa 1); no se pueden usar los dos a la vez.
    Devuelve un resumen con los convertidos, omitidos y fallos, y en `claves` los .md listos
    (convertidos y omitidos), que es el evento de entrada de la etapa 3.
    """
    if modo_ocr not in MODOS_OCR:
        raise ValueError(f"modo de OCR no válido '{modo_ocr}', opciones: {', '.join(MODOS_OCR)}")
    if ficheros and claves is not None:
        raise ValueError("indica 'ficheros' o 'claves', no los dos")

    bucket = alm.resolver_bucket(bucket)
    s3 = alm.conectar(bucket)
    fecha = alm.resolver_fecha(s3, bucket, alm.CARPETA_DESCARGA, gestora, fecha)
    origen = alm.carpeta(alm.CARPETA_DESCARGA, gestora, fecha)
    destino = alm.carpeta(alm.CARPETA_MARKDOWN, gestora, fecha)
    print(f"Origen:  s3://{bucket}/{origen}/")
    print(f"Destino: s3://{bucket}/{destino}/\n")

    claves_pdf = alm.listar_claves(s3, bucket, origen, ".pdf")
    if claves is not None:
        pedidas = set(claves)
        claves_pdf = [c for c in claves_pdf if c in pedidas]
        for falta in sorted(pedidas - set(claves_pdf)):
            print(f"AVISO: no existe '{falta}' en s3://{bucket}/{origen}/")
    elif ficheros:
        pedidos = set(ficheros)
        claves_pdf = [c for c in claves_pdf if PurePosixPath(c).name in pedidos]
        for falta in sorted(pedidos - {PurePosixPath(c).name for c in claves_pdf}):
            print(f"AVISO: no existe '{falta}' en s3://{bucket}/{origen}/")
    if not claves_pdf:
        raise alm.ErrorEtapa(f"no se ha encontrado ningún PDF que convertir en s3://{bucket}/{origen}/")

    ya_existentes = set() if sobrescribir else set(alm.listar_claves(s3, bucket, destino, ".md"))

    convertidos, omitidos, fallos = [], [], []
    for i, clave_pdf in enumerate(claves_pdf, 1):
        nombre = PurePosixPath(clave_pdf).name
        clave_md = f"{destino}/{PurePosixPath(clave_pdf).stem}.md"
        if clave_md in ya_existentes:
            print(f"[{i}/{len(claves_pdf)}] {nombre}: ya existe el .md, se omite")
            omitidos.append(clave_md)
            continue
        print(f"[{i}/{len(claves_pdf)}] {nombre} -> s3://{bucket}/{clave_md}")
        try:
            markdown = pdf_a_markdown(alm.leer(s3, bucket, clave_pdf), modo_ocr, idioma)
            alm.escribir(
                s3,
                bucket,
                clave_md,
                markdown.encode("utf-8"),
                "text/markdown; charset=utf-8",
                {"pdf-origen": clave_pdf},
            )
            convertidos.append(clave_md)
        except Exception as error:  # un PDF corrupto o un fallo de S3 no debe parar el resto
            print(f"    ERROR: {error}")
            fallos.append({"fichero": nombre, "error": str(error)})

    print("\nResumen:")
    print(f"  Convertidos y subidos: {len(convertidos)}")
    print(f"  Omitidos (ya existían): {len(omitidos)}")
    print(f"  Fallos: {len(fallos)}")
    for fallo in fallos:
        print(f"    - {fallo['fichero']}: {fallo['error']}")
    if not convertidos and not omitidos:
        raise alm.ErrorEtapa("no se ha podido convertir ningún PDF")
    return {
        "bucket": bucket,
        "gestora": gestora,
        "fecha": fecha,
        "origen": origen,
        "destino": destino,
        "claves": sorted(convertidos + omitidos),
        "convertidos": convertidos,
        "omitidos": omitidos,
        "fallos": fallos,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gestora", help="Gestora (carpeta dentro de download/)")
    parser.add_argument("ficheros", nargs="*", help="Nombres de PDF de la carpeta a convertir (por defecto, todos)")
    parser.add_argument("--claves", nargs="+", help="Claves de S3 de los PDF a convertir")
    parser.add_argument("--bucket", help=f"Bucket de S3 (por defecto, la variable {alm.VARIABLE_BUCKET})")
    parser.add_argument("--fecha", type=alm.fecha_valida, help="Carpeta AAAAMMDD (por defecto, la más reciente)")
    parser.add_argument("--ocr", choices=MODOS_OCR, default="auto", help="Uso del OCR (por defecto auto)")
    parser.add_argument("--idioma", default="spa", help="Idioma del OCR (por defecto spa)")
    parser.add_argument("--sobrescribir", action="store_true", help="Regenera los .md aunque ya existan")
    args = parser.parse_args()
    if args.ficheros and args.claves:
        parser.error("indica nombres de fichero o --claves, no los dos")

    try:
        resumen = convertir_pdfs(
            args.gestora,
            args.bucket,
            args.fecha,
            args.ficheros,
            args.ocr,
            args.idioma,
            args.sobrescribir,
            args.claves,
        )
    except alm.ErrorEtapa as e:
        print(f"[error] {e}")
        return 1
    return 1 if resumen["fallos"] else 0


if __name__ == "__main__":
    sys.exit(main())
