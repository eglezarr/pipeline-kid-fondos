"""Validaciones compartidas por varias etapas del pipeline."""

import re


def isin_valido(isin: str | None) -> bool:
    """Comprueba el formato y el dígito de control (algoritmo de Luhn) de un ISIN."""
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin or ""):
        return False
    # Cada letra se sustituye por su valor (A=10 ... Z=35) y se aplica Luhn a los dígitos resultantes
    digitos = "".join(str(int(c, 36)) for c in isin)
    total = 0
    for posicion, caracter in enumerate(reversed(digitos)):
        n = int(caracter)
        if posicion % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0
