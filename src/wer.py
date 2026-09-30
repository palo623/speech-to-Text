"""
Metrica de precision para transcripciones de audio: Word Error Rate (WER).

Se usa igual para las dos tecnicas del ejercicio, de forma que la comparacion
sea justa: Gemini (por lotes, desde Python) y Web Speech API (tiempo real, en
el navegador).

Definicion:
    WER = (sustituciones + borrados + inserciones) / palabras de la referencia
    precision = 1 - WER

No necesita dependencias: el algoritmo de Levenshtein va implementado aqui.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


# --------------------------------------------------------------------------
# Normalizacion
# --------------------------------------------------------------------------
def normalizar(texto: str) -> list[str]:
    """Minusculas, sin tildes, sin puntuacion, sin marcas de comillas.

    Asi "Estas" y "estas" no cuentan como error, que es justo el tipo de
    diferencia que no aporta informacion sobre la calidad del reconocimiento.
    """
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s]", " ", texto)
    return texto.split()


# --------------------------------------------------------------------------
# Levenshtein con backtrace
# --------------------------------------------------------------------------
def conteo_ediciones(
    referencia: list[str], hipotesis: list[str]
) -> tuple[int, int, int]:
    """Devuelve (sustituciones, borrados, inserciones).

    Es el algoritmo de Wagner-Fischer: matriz de distancias con retroceso para
    poder saber que tipo de operacion hubo en cada celda.
    """
    n, m = len(referencia), len(hipotesis)
    dist = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dist[i][0] = i
    for j in range(m + 1):
        dist[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if referencia[i - 1] == hipotesis[j - 1]:
                dist[i][j] = dist[i - 1][j - 1]
            else:
                dist[i][j] = 1 + min(
                    dist[i - 1][j - 1], dist[i - 1][j], dist[i][j - 1]
                )

    subs = borrados = inserciones = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and referencia[i - 1] == hipotesis[j - 1]:
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dist[i][j] == dist[i - 1][j - 1] + 1:
            subs += 1
            i, j = i - 1, j - 1
        elif i > 0 and dist[i][j] == dist[i - 1][j] + 1:
            borrados += 1
            i -= 1
        else:
            inserciones += 1
            j -= 1
    return subs, borrados, inserciones


@dataclass
class Metrica:
    """Resultado de comparar una referencia con una transcripcion."""

    palabras_referencia: int
    palabras_hipotesis: int
    sustituciones: int
    borrados: int
    inserciones: int

    @property
    def errores(self) -> int:
        return self.sustituciones + self.borrados + self.inserciones

    @property
    def wer(self) -> float:
        if not self.palabras_referencia:
            return 0.0
        return self.errores / self.palabras_referencia

    @property
    def precision(self) -> float:
        """Proporcion de palabras correctas. 0.0 si la referencia vacia."""
        if not self.palabras_referencia:
            return 0.0
        return max(0.0, 1.0 - self.wer)

    def resumen(self) -> str:
        return (
            f"WER {self.wer * 100:.1f}% | precision {self.precision * 100:.1f}% | "
            f"S{self.sustituciones} B{self.borrados} I{self.inserciones}"
        )


def calcular_wer(referencia: str, hipotesis: str) -> Metrica:
    """Compara el texto de referencia con el transcrito y devuelve la metrica."""
    ref, hyp = normalizar(referencia), normalizar(hipotesis)
    subs, borrados, inserciones = conteo_ediciones(ref, hyp)
    return Metrica(len(ref), len(hyp), subs, borrados, inserciones)


def autotest() -> bool:
    """Comprueba el calculo de WER con casos conocidos. Devuelve True si pasa."""
    casos = [
        ("Hola mundo", "Hola mundo", 0.0),
        ("Hola mundo", "Hola mundano", 0.5),
        ("el gato come", "el gato corre", 1 / 3),
        ("uno dos tres", "uno tres", 1 / 3),
        ("uno dos tres", "uno dos tres cuatro", 1 / 3),
        ("Hola, ¿cómo estás?", "hola como estas", 0.0),
        ("El pingüino", "el pinguino", 0.0),
        ("la casa es grande", "la casa es pequena", 0.25),
    ]
    fallos = 0
    for ref, hyp, esperado in casos:
        m = calcular_wer(ref, hyp)
        ok = abs(m.wer - esperado) < 1e-6
        fallos += not ok
        marca = "OK   " if ok else "FALLO"
        print(f"[{marca}] {ref!r} vs {hyp!r} -> WER {m.wer:.3f} (esperado {esperado:.3f})")
    print(f"\n{len(casos) - fallos}/{len(casos)} correctos")
    return fallos == 0
