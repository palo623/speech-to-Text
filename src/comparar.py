"""
Compara la precision de los dos metodos y genera el informe final.

    Metodo A -> resultados/<nombre>.webspeech.txt  (Web Speech API, navegador)
    Metodo B -> resultados/<nombre>.gemini.txt      (Gemini, Python)
    Referencia -> audios/<nombre>.txt               (lo que escribiste a mano)

Calcula el WER de cada metodo con exactamente el mismo codigo (src/wer.py), de
modo que la comparacion sea valida.

Uso:
    py -3 src/comparar.py
    py -3 src/comparar.py --salida resultados/informe.md
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.wer import Metrica, autotest, calcular_wer, normalizar

SUFIJOS = {
    "Web Speech API": ".webspeech",
    "Gemini": ".gemini",
}


@dataclass
class Fila:
    audio: Path
    metricas: dict[str, Metrica | None]

    @property
    def puntuan(self) -> list[str]:
        return [m for m, mt in self.metricas.items() if mt is not None]


def leer_referencia(audio: Path) -> str | None:
    ref = config.ruta_referencia(audio)
    if not ref.is_file():
        return None
    texto = ref.read_text(encoding="utf-8").strip()
    return texto or None


def cargar_filas(audios: list[Path]) -> list[Fila]:
    filas: list[Fila] = []
    for audio in audios:
        referencia = leer_referencia(audio)
        if referencia is None:
            continue
        metricas: dict[str, Metrica | None] = {}
        for metodo, sufijo in SUFIJOS.items():
            ruta = config.ruta_salida(audio, sufijo)
            if ruta.is_file():
                metricas[metodo] = calcular_wer(
                    referencia, ruta.read_text(encoding="utf-8")
                )
            else:
                metricas[metodo] = None
        filas.append(Fila(audio=audio, metricas=metricas))
    return filas


def escribir_informe(filas: list[Fila], destino: Path, argumentos) -> None:
    lineas = [
        "# Informe de precision: Web Speech API vs Gemini",
        "",
        "Metrica: **WER** = (sustituciones + borrados + inserciones) / palabras",
        "de la referencia. Precision = 1 - WER. Cuanto menor el WER, mejor.",
        "",
        "El texto se normaliza antes de comparar (minusculas, sin tildes, sin",
        "puntuacion), asi que los acentos no cuentan como error.",
        "",
    ]

    if filas:
        lineas += [
            "## Resultado por audio",
            "",
            "| Audio | Metodo | Palabras ref. | WER | Precision | S | B | I |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for fila in filas:
            alguna = False
            for metodo, m in fila.metricas.items():
                if m is None:
                    continue
                alguna = True
                lineas.append(
                    f"| {fila.audio.name} | {metodo} | {m.palabras_referencia} "
                    f"| {m.wer * 100:.1f}% | {m.precision * 100:.1f}% "
                    f"| {m.sustituciones} | {m.borrados} | {m.inserciones} |"
                )
            if not alguna:
                lineas.append(
                    f"| {fila.audio.name} | sin transcripciones | - | - | - | - | - | - |"
                )
        lineas.append("")

        # Medias por metodo, solo sobre los audios que ambos resolvieron.
        comparables = [
            f for f in filas
            if f.metricas.get("Web Speech API") and f.metricas.get("Gemini")
        ]
        if comparables:
            lineas += ["## Media de WER (solo audios medidos con ambos metodos)", ""]
            for metodo in SUFIJOS:
                wer = sum(f.metricas[metodo].wer for f in comparables) / len(comparables)
                lineas.append(
                    f"- **{metodo}**: WER {wer * 100:.1f}% "
                    f"(precision {(1 - wer) * 100:.1f}%) sobre {len(comparables)} audio(s)"
                )
            mejor = min(
                comparables,
                key=lambda f: f.metricas["Gemini"].wer - f.metricas["Web Speech API"].wer,
            )
            dif = mejor.metricas["Gemini"].wer - mejor.metricas["Web Speech API"].wer
            if abs(dif) < 0.005:
                lineas.append("\nLos dos metodos dan practicamente el mismo resultado.")
            elif dif < 0:
                lineas.append(
                    f"\nGemini tiene mejor WER en {mejor.audio.name} "
                    f"({dif * 100:.1f} puntos de diferencia a su favor)."
                )
            else:
                lineas.append(
                    f"\nLa Web Speech API tiene mejor WER en {mejor.audio.name} "
                    f"({-dif * 100:.1f} puntos de diferencia a su favor)."
                )
            lineas.append("")
    else:
        lineas += [
            "## Sin datos que comparar",
            "",
            "No hay ningun audio con transcripcion de referencia "
            "(`audios/<nombre>.txt`).",
            "",
        ]

    lineas += _faltantes(filas, argumentos)
    lineas += [
        "## Lectura del resultado",
        "",
        "- Web Speech API solo funciona en Chrome/Edge y **solo con microfono**.",
        "  Para transcribir un fichero hay que reproducirlo por los altavoces y",
        "  capturarlo de nuevo, lo que anade ruido y penaliza su precision.",
        "  Por eso la comparacion de WER entre ambos no es del todo justa:",
        "  Gemini recibe el audio digital limpio.",
        "- Gemini procesa el fichero directamente, sin pasar por el microfono,",
        "  y es un modelo entrenado especificamente en audio.",
        "- La Web Speech API devuelve resultados provisionales mientras hablas;",
        "  Gemini devuelve el texto final de una sola vez.",
        "",
    ]

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _faltantes(filas: list[Fila], argumentos) -> list[str]:
    """Avisos sobre lo que falta por hacer, para no dejar huecos en el informe."""
    avisos: list[str] = []
    todos = config.descubrir_audios()
    con_ref = [a for a in todos if leer_referencia(a)]

    if not con_ref:
        avisos += [
            "## Pendiente",
            "",
            "- Escribe la referencia (lo que dijiste) junto a cada audio:",
            "  `audios/audio1.wav` + `audios/audio1.txt`",
            "",
        ]
        return avisos

    faltan_gemini = [
        a for a in con_ref
        if not config.ruta_salida(a, SUFIJOS["Gemini"]).is_file()
    ]
    faltan_web = [
        a for a in con_ref
        if not config.ruta_salida(a, SUFIJOS["Web Speech API"]).is_file()
    ]

    if faltan_gemini or faltan_web:
        avisos += ["## Pendiente", ""]
    if faltan_gemini:
        nombres = ", ".join(a.name for a in faltan_gemini)
        avisos += [
            f"- Falta la transcripcion de Gemini para: {nombres}",
            f"  Ejecuta:  py -3 src\\transcribir.py {nombres}",
            "",
        ]
    if faltan_web:
        nombres = ", ".join(a.name for a in faltan_web)
        avisos += [
            f"- Falta la transcripcion de la Web Speech API para: {nombres}",
            f"  Abrir web\\index.html, transcribirlos y guardar cada texto en",
            f"  {config.CARPETA_RESULTADOS}\\<nombre>.webspeech.txt",
            "",
        ]
    return avisos


def recoger_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compara el WER de la Web Speech API y de Gemini.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--salida", type=Path,
                   default=config.CARPETA_RESULTADOS / "informe.md",
                   help="fichero del informe (def. resultados/informe.md)")
    p.add_argument("--autotest", action="store_true",
                   help="prueba local del calculo de WER, sin ficheros")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    config.configurar_consola()
    args = recoger_argumentos(argv)

    if args.autotest:
        return 0 if autotest() else 1

    audios = config.descubrir_audios()
    if not audios:
        print(f"No hay audio en {config.CARPETA_AUDIOS}/.", file=sys.stderr)
        print("Graba los 3 audios de prueba y ponlos ahi.", file=sys.stderr)
        return 1

    filas = cargar_filas(audios)

    for fila in filas:
        m = fila.metricas.get("Gemini")
        if m:
            print(f"{fila.audio.name}: Gemini WER {m.wer * 100:.1f}%")
        m = fila.metricas.get("Web Speech API")
        if m:
            print(f"{fila.audio.name}: Web Speech API WER {m.wer * 100:.1f}%")

    escribir_informe(filas, args.salida, args)
    print(f"\nInforme: {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
