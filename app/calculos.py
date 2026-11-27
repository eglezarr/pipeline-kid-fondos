"""Cálculos y textos de la aplicación, sin dependencias de Streamlit (se prueban por separado).

- Formato de números al estilo español (coma decimal, punto de miles).
- Nombres cortos de los fondos para las etiquetas.
- Impacto de los costes en euros a lo largo de un plazo.
- Frases que resumen cada gráfico a partir de los datos (nunca texto fijo sobre los datos).
"""

import math
import re
import unicodedata

import pandas as pd

NIVELES_RIESGO = range(1, 8)

NOMBRES_FUENTE = {"bestinver": "Bestinver", "azvalor": "Azvalor"}

# Etiquetas legibles de los campos del Anexo A (para la ficha y la página de fiabilidad)
CAMPOS = {
    "isin": "ISIN",
    "nombre_producto": "Nombre del producto",
    "nombre_clase": "Clase",
    "gestora": "Gestora",
    "fecha_documento": "Fecha del documento",
    "sri": "Indicador de riesgo",
    "periodo_mantenimiento_anios": "Periodo de mantenimiento recomendado",
    "gastos_corrientes_pct": "Gastos corrientes",
    "costes_entrada_pct": "Costes de entrada",
    "costes_salida_pct": "Costes de salida",
}


# ---------------------------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------------------------


def _es(texto: str) -> str:
    """Convierte un número formateado en inglés (1,234.5) al estilo español (1.234,5)."""
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def falta(valor) -> bool:
    return valor is None or (isinstance(valor, float) and math.isnan(valor))


def num(valor, decimales: int = 0) -> str:
    if falta(valor):
        return "sin dato"
    return _es(f"{valor:,.{decimales}f}")


def pct(valor, decimales: int = 2) -> str:
    """Porcentaje con decimales justos: 1,8 %, 0,57 %, 2 %."""
    if falta(valor):
        return "sin dato"
    texto = f"{valor:.{decimales}f}".rstrip("0").rstrip(".")
    return f"{_es(texto)}\u00a0%"  # espacio de no separación: la cifra y su unidad no se parten


def eur(valor) -> str:
    return "sin dato" if falta(valor) else f"{num(round(valor))}\u00a0€"


def anios(valor) -> str:
    if falta(valor):
        return "sin dato"
    texto = num(valor, 1).removesuffix(",0")
    return f"{texto}\u00a0año" if valor == 1 else f"{texto}\u00a0años"


def fondos_txt(n: int) -> str:
    return f"{n} fondo" if n == 1 else f"{n} fondos"


# ---------------------------------------------------------------------------------------------
# Nombres
# ---------------------------------------------------------------------------------------------

_SUFIJOS = re.compile(r"[,\s]+(F\.?\s?I\.?|FI|FONDO DE INVERSI[OÓ]N)\.?$", re.IGNORECASE)
_MINUSCULAS = {"de", "del", "la", "las", "los", "y", "e", "en", "a"}


def _tipo_titulo(texto: str) -> str:
    """Pasa a tipo título los nombres escritos en mayúsculas en el KID."""
    if texto != texto.upper():
        return texto
    palabras = texto.lower().split()
    return " ".join(p if (i and p in _MINUSCULAS) else p.capitalize() for i, p in enumerate(palabras))


def nombre_corto(nombre_producto: str, nombre_clase: str | None = None) -> str:
    """'BESTINFOND, F.I.' -> 'Bestinfond'; añade la clase si el KID la indica."""
    nombre = _tipo_titulo(_SUFIJOS.sub("", nombre_producto.strip()))
    if isinstance(nombre_clase, str) and nombre_clase.strip():
        clase = _tipo_titulo(nombre_clase.strip())
        if clase.lower() not in nombre.lower():
            nombre = f"{nombre} ({clase})"
    return nombre


MODELOS = {"kimi-k3.1": "Kimi K3.1 (Moonshot AI)"}


def nombre_modelo(identificador: str) -> str:
    """'global.moonshotai.kimi-k3.1' -> 'Kimi K3.1 (Moonshot AI)' (o el identificador si no se conoce)."""
    for clave, nombre in MODELOS.items():
        if identificador and identificador.endswith(clave):
            return nombre
    return identificador


def sin_gestora(nombre: str, gestora: str) -> str:
    """'Bestinver Bolsa' -> 'Bolsa' (cuando el contexto ya indica la gestora)."""
    if nombre.lower().startswith(gestora.lower() + " "):
        resto = nombre[len(gestora) + 1 :]
        return resto[0].upper() + resto[1:]
    return nombre


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


# ---------------------------------------------------------------------------------------------
# Costes
# ---------------------------------------------------------------------------------------------


def impacto_costes(
    importe: float,
    plazo: float,
    gastos_corrientes_pct: float,
    costes_entrada_pct: float | None = 0,
    costes_salida_pct: float | None = 0,
    rentabilidad_pct: float = 0,
) -> dict:
    """Efecto de los costes del KID sobre una inversión mantenida `plazo` años.

    Supuestos (simplificados, se explican en la aplicación):
      - la comisión de entrada se descuenta del importe invertido al principio;
      - los gastos corrientes se descuentan cada año sobre el valor de la inversión;
      - la comisión de salida se descuenta del valor final al reembolsar;
      - la rentabilidad bruta anual es constante.

    Devuelve el valor final con y sin costes, la diferencia (lo que se pierde por costes,
    incluida la rentabilidad que deja de generar el dinero cobrado) y la incidencia anual de los
    costes: cuánto rebajan los costes la rentabilidad anual, como en el apartado de costes del KID.
    """
    r = rentabilidad_pct / 100
    g = gastos_corrientes_pct / 100
    e = 0 if falta(costes_entrada_pct) else costes_entrada_pct / 100
    s = 0 if falta(costes_salida_pct) else costes_salida_pct / 100
    sin_costes = importe * (1 + r) ** plazo
    con_costes = importe * (1 - e) * ((1 + r) * (1 - g)) ** plazo * (1 - s)
    rentabilidad_neta = (con_costes / importe) ** (1 / plazo) - 1 if plazo > 0 else 0
    return {
        "valor_sin_costes": sin_costes,
        "valor_con_costes": con_costes,
        "impacto": sin_costes - con_costes,
        "incidencia_anual_pct": (r - rentabilidad_neta) * 100,
    }


def tabla_impacto(
    fondos: pd.DataFrame,
    importe: float,
    rentabilidad_pct: float,
    plazo_fijo: float | None = None,
) -> pd.DataFrame:
    """Impacto de los costes para cada fondo con gastos corrientes conocidos.

    Con `plazo_fijo` todos los fondos se comparan al mismo plazo; sin él, cada uno a su periodo
    de mantenimiento recomendado (los que no lo tienen quedan fuera).
    """
    filas = []
    for fondo in fondos.itertuples():
        plazo = plazo_fijo or fondo.periodo_mantenimiento_anios
        if falta(fondo.gastos_corrientes_pct) or falta(plazo) or plazo <= 0:
            continue
        resultado = impacto_costes(
            importe,
            plazo,
            fondo.gastos_corrientes_pct,
            fondo.costes_entrada_pct,
            fondo.costes_salida_pct,
            rentabilidad_pct,
        )
        filas.append({"isin": fondo.isin, "plazo": plazo} | resultado)
    columnas = ["isin", "plazo", "valor_sin_costes", "valor_con_costes", "impacto", "incidencia_anual_pct"]
    tabla = pd.DataFrame(filas, columns=columnas)
    return fondos.merge(tabla, on="isin").sort_values("impacto", ascending=False, ignore_index=True)


# ---------------------------------------------------------------------------------------------
# Resúmenes y frases a partir de los datos
# ---------------------------------------------------------------------------------------------


def recuento_por_nivel(fondos: pd.DataFrame) -> dict[int, int]:
    conteo = fondos["sri"].value_counts()
    return {n: int(conteo.get(n, 0)) for n in NIVELES_RIESGO}


def frase_escala(fondos: pd.DataFrame) -> str:
    """Resumen de la escalera de riesgo."""
    if fondos.empty:
        return "No hay fondos que mostrar."
    conteo = recuento_por_nivel(fondos)
    moda = max(conteo, key=lambda n: (conteo[n], -n))
    minimo, maximo = int(fondos["sri"].min()), int(fondos["sri"].max())
    return (
        f"Los {len(fondos)} fondos van del riesgo {minimo} al {maximo}; "
        f"el nivel más habitual es el {moda}, con {fondos_txt(conteo[moda])}."
    )


def correlacion(fondos: pd.DataFrame, x: str, y: str) -> tuple[float | None, int]:
    """Correlación de Spearman (por rangos, adecuada para una escala ordinal) y tamaño de muestra."""
    datos = fondos[[x, y]].dropna()
    if len(datos) < 5 or datos[x].nunique() < 2 or datos[y].nunique() < 2:
        return None, len(datos)
    # Spearman = Pearson sobre los rangos (con rango medio en los empates); evita depender de scipy
    return float(datos[x].rank().corr(datos[y].rank())), len(datos)


def _fuerza(rho: float) -> str:
    a = abs(rho)
    return "fuerte" if a >= 0.6 else "moderada" if a >= 0.4 else "débil"


def frase_riesgo_coste(fondos: pd.DataFrame) -> str:
    datos = fondos.dropna(subset=["gastos_corrientes_pct"])
    rho, n = correlacion(datos, "sri", "gastos_corrientes_pct")
    if rho is None:
        return "No hay datos suficientes para relacionar riesgo y gastos."
    medianas = datos.groupby("sri")["gastos_corrientes_pct"].median()
    bajo, alto = int(medianas.index.min()), int(medianas.index.max())
    tramo = (
        f"la mediana de gastos corrientes pasa de {pct(medianas[bajo])} en el riesgo {bajo} "
        f"a {pct(medianas[alto])} en el riesgo {alto}"
    )
    if abs(rho) < 0.2:
        cuerpo = f"Riesgo y gastos apenas están relacionados: {tramo}"
    elif rho > 0:
        cuerpo = f"A más riesgo, más gastos, con una relación {_fuerza(rho)}: {tramo}"
    else:
        cuerpo = f"A más riesgo, menos gastos, con una relación {_fuerza(rho)}: {tramo}"
    return f"{cuerpo} (correlación de Spearman {num(rho, 2)}, {n} fondos)."


def frase_horizonte(fondos: pd.DataFrame) -> str:
    datos = fondos.dropna(subset=["periodo_mantenimiento_anios"])
    if datos.empty:
        return "Ningún KID indica el periodo de mantenimiento recomendado."
    minimo, maximo = datos["periodo_mantenimiento_anios"].min(), datos["periodo_mantenimiento_anios"].max()
    frase = f"El KID recomienda mantenerlos entre {num(minimo, 1).removesuffix(',0')}"
    frase += f" y {anios(maximo)}"
    rho, n = correlacion(datos, "sri", "periodo_mantenimiento_anios")
    if rho is not None and rho >= 0.4:
        frase += f"; cuanto más riesgo, más tiempo (correlación de Spearman {num(rho, 2)}, {n} fondos)"
    elif rho is not None and rho <= -0.4:
        frase += f"; cuanto más riesgo, menos tiempo (correlación de Spearman {num(rho, 2)}, {n} fondos)"
    return frase + "."


def resumen_por_fuente(fondos: pd.DataFrame) -> pd.DataFrame:
    """Medianas y rangos por gestora (fuente de la captura)."""
    return (
        fondos.groupby("fuente")
        .agg(
            fondos=("isin", "count"),
            sri_mediana=("sri", "median"),
            gastos_min=("gastos_corrientes_pct", "min"),
            gastos_mediana=("gastos_corrientes_pct", "median"),
            gastos_max=("gastos_corrientes_pct", "max"),
            plazo_mediana=("periodo_mantenimiento_anios", "median"),
            con_entrada=("costes_entrada_pct", lambda s: int((s > 0).sum())),
            con_salida=("costes_salida_pct", lambda s: int((s > 0).sum())),
        )
        .reset_index()
    )


def frase_impacto(tabla: pd.DataFrame, importe: float, rentabilidad_pct: float, plazo_fijo: float | None) -> str:
    if tabla.empty:
        return "Ningún fondo tiene los datos necesarios para el cálculo."
    plazo = f"durante {anios(plazo_fijo)}" if plazo_fijo else "durante el periodo recomendado de cada fondo"
    supuesto = (
        "sin rentabilidad" if rentabilidad_pct == 0 else f"con una rentabilidad bruta del {pct(rentabilidad_pct)}"
    )
    supuesto = supuesto.replace("\u00a0%", "\u00a0% anual")
    mas, menos = tabla.iloc[0], tabla.iloc[-1]
    return (
        f"Invirtiendo {eur(importe)} {plazo} y {supuesto}, los costes se llevan entre "
        f"{eur(menos.impacto)} ({menos.nombre_corto}) y {eur(mas.impacto)} ({mas.nombre_corto})."
    )


def frase_gestoras(fondos: pd.DataFrame) -> str:
    resumen = resumen_por_fuente(fondos)
    if len(resumen) < 2:
        return "Solo hay datos de una gestora."
    nombres = [NOMBRES_FUENTE.get(f, f.capitalize()) for f in resumen["fuente"]]
    partes = [f"{n}: {fondos_txt(int(r.fondos))}" for n, r in zip(nombres, resumen.itertuples(), strict=True)]
    gastos = " y ".join(f"{pct(r.gastos_mediana)} en {n}" for n, r in zip(nombres, resumen.itertuples(), strict=True))
    riesgo = " y ".join(
        f"{num(r.sri_mediana, 1).removesuffix(',0')} en {n}" for n, r in zip(nombres, resumen.itertuples(), strict=True)
    )
    return f"{'; '.join(partes)}. La mediana de gastos corrientes es {gastos}; la del indicador de riesgo, {riesgo}."


def posicion_en_nivel(fondos: pd.DataFrame, isin: str) -> str | None:
    """Frase con la posición de un fondo por gastos corrientes entre los de su mismo riesgo."""
    fondo = fondos[fondos["isin"] == isin]
    if fondo.empty or falta(fondo.iloc[0]["gastos_corrientes_pct"]):
        return None
    nivel = int(fondo.iloc[0]["sri"])
    pares = fondos[(fondos["sri"] == nivel)].dropna(subset=["gastos_corrientes_pct"])
    if len(pares) < 2:
        return f"Es el único fondo con riesgo {nivel} y gastos corrientes conocidos."
    gasto = fondo.iloc[0]["gastos_corrientes_pct"]
    puesto = int((pares["gastos_corrientes_pct"] < gasto).sum()) + 1
    empatados = int((pares["gastos_corrientes_pct"] == gasto).sum()) - 1
    texto = f"De los {len(pares)} fondos con riesgo {nivel}, "
    if puesto == 1:
        texto += "es el de menores gastos corrientes"
    elif puesto == len(pares) - empatados:
        texto += "es el de mayores gastos corrientes"
    else:
        texto += f"es el {puesto}.º con menores gastos corrientes"
    if empatados:
        texto += f" (empatado con {fondos_txt(empatados)})"
    mediana = pares["gastos_corrientes_pct"].median()
    return f"{texto}; la mediana de su nivel es {pct(mediana)}."


def proxima_ejecucion(ahora) -> "pd.Timestamp":
    """Siguiente ejecución programada del pipeline: día 15 a las 9:00 (hora de Madrid)."""
    ahora = pd.Timestamp(ahora).tz_convert("Europe/Madrid")
    candidata = ahora.replace(day=15, hour=9, minute=0, second=0, microsecond=0)
    if candidata <= ahora:
        candidata = (candidata + pd.DateOffset(months=1)).replace(day=15)
    return candidata


def citas_no_encontradas(fondos: pd.DataFrame) -> list[tuple[str, str]]:
    """Pares (ISIN, campo) cuya cita no aparece literalmente en el texto del documento."""
    return [
        (f.isin, campo)
        for f in fondos.itertuples()
        for campo, encontrada in (f.verificacion_evidencias or {}).items()
        if not encontrada
    ]
