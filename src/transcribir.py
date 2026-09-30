"""
Metodo B: transcripcion por lotes con la API de Gemini (Python).

Envia ficheros de audio (.wav, .mp3, ...) al modelo `gemini-3.5-transcribe`
y guarda el texto en resultados/<nombre>.gemini.txt

Uso:
    py -3 src/transcribir.py
    py -3 src/transcribir.py audios/audio1.wav
    py -3 src/transcribir.py --vocab "Kubernetes,BigQuery" --timestamps
    py -3 src/transcribir.py --autotest     # prueba local, sin llamar a la API
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.wer import Metrica, autotest, calcular_wer

SUFIJO_SALIDA = ".gemini"


# --------------------------------------------------------------------------
# Llamada a Gemini
# --------------------------------------------------------------------------
@dataclass
class Resultado:
    audio: Path
    texto: str = ""
    metrica: Metrica | None = None
    error: str = ""
    segundos: float = 0.0
    detalles: str = ""


def validar_opciones(args: argparse.Namespace) -> None:
    """Comprueba incompatibilidades antes de gastar tiempo o tokens.

    La API rechaza custom_vocabulary junto a word_timestamp o diarization.
    """
    if args.vocab and (args.timestamps or args.diarizacion):
        raise SystemExit(
            "Error de configuracion: --vocab es incompatible con "
            "--timestamps y --diarizacion (la API rechaza la peticion).\n"
            "Quita --vocab o quita --timestamps/--diarizacion."
        )
    if args.modo == "smart" and (args.timestamps or args.diarizacion):
        print(
            "Aviso: el modo 'smart' ignora los timestamps y la diarizacion.",
            file=sys.stderr,
        )
    if args.vocab and len(args.vocab) > 1000:
        raise SystemExit(
            f"--vocab admite como mucho 1000 terminos (has puesto {len(args.vocab)})."
        )


def construir_config(types, args: argparse.Namespace):
    """Arma el GenerateContentConfig respetando las incompatibilidades."""
    atc: dict = {}

    if args.idioma and args.idioma.lower() != "auto":
        atc["language_codes"] = args.idioma.split(",")

    if args.vocab:
        atc["custom_vocabulary"] = args.vocab
    if args.timestamps:
        atc["word_timestamp"] = True
    if args.diarizacion:
        atc["diarization"] = True
    if args.modo and args.modo.upper() != "VERBATIM":
        atc["mode"] = "SMART"

    return types.GenerateContentConfig(
        audio_transcription_config=types.AudioTranscriptionConfig(**atc),
        # Los modelos de transcripcion no soportan function calling; desactivar
        # AFC evita el aviso del SDK y cualquier conflicto con la transcripcion.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def esperar_archivo(client, archivo, intentos: int = 30) -> None:
    """La Files API devuelve state=PROCESSING en subidas grandes."""
    for _ in range(intentos):
        if getattr(archivo, "state", "ACTIVE") == "ACTIVE":
            return
        time.sleep(2)
        archivo = client.files.get(name=archivo.name)
    print("Aviso: el archivo sigue en PROCESSING, se intenta igualmente.",
          file=sys.stderr)


def transcribir_un_audio(client, types, ruta: Path, args) -> Resultado:
    inicio = time.perf_counter()
    resultado = Resultado(audio=ruta)
    mime = config.MIME_POR_EXTENSION[ruta.suffix.lower()]
    tamano = ruta.stat().st_size
    subida = None

    try:
        gen_config = construir_config(types, args)
        if tamano <= config.LIMITE_BYTES_INLINE and not args.forzar_subida:
            contenido = types.Part.from_bytes(data=ruta.read_bytes(), mime_type=mime)
            resultado.detalles = "inline"
        else:
            subida = client.files.upload(file=str(ruta), config={"mime_type": mime})
            esperar_archivo(client, subida)
            contenido = subida
            resultado.detalles = "Files API"

        respuesta = client.models.generate_content(
            model=args.model,
            contents=[contenido],
            config=gen_config,
        )
        resultado.texto = (respuesta.text or "").strip()
    except Exception as exc:  # queremos ver cualquier fallo de la API
        resultado.error = f"{type(exc).__name__}: {exc}"
    finally:
        if subida is not None:
            try:
                client.files.delete(name=subida.name)
            except Exception:  # la limpieza no debe romper el script
                pass

    resultado.segundos = time.perf_counter() - inicio
    return resultado


# --------------------------------------------------------------------------
# Procesado
# --------------------------------------------------------------------------
def procesar(cliente, types, rutas: list[Path], args) -> list[Resultado]:
    resultados: list[Resultado] = []
    for ruta in rutas:
        print(f"\n-> {ruta.name} ({ruta.stat().st_size / 1024:.0f} KB)")
        r = transcribir_un_audio(cliente, types, ruta, args)
        if r.error:
            print(f"   ERROR: {r.error}")
        else:
            destino = config.ruta_salida(ruta, SUFIJO_SALIDA)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(r.texto + "\n", encoding="utf-8")
            print(f"   {len(r.texto.split())} palabras en {r.segundos:.1f}s -> {destino.name}")

            referencia = config.ruta_referencia(ruta)
            if referencia.is_file():
                r.metrica = calcular_wer(
                    referencia.read_text(encoding="utf-8"), r.texto
                )
                print(f"   {r.metrica.resumen()}")
            else:
                print(f"   (sin referencia {referencia.name}: no se mide precision)")
        resultados.append(r)
    return resultados


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def recoger_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Metodo B: transcribe audio con la API de Gemini.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("audios", nargs="*", type=Path,
                   help="ficheros concretos (def. todos los de audios/)")
    p.add_argument("--model", default=config.MODELO_POR_DEFECTO)
    p.add_argument("--idioma", default="es-ES",
                   help="codigos BCP-47 separados por coma, o 'auto' (def. es-ES)")
    p.add_argument("--vocab", type=lambda s: [t.strip() for t in s.split(",") if t.strip()],
                   help="terminos a sesgar, separados por coma")
    p.add_argument("--modo", choices=["verbatim", "smart"], default="verbatim")
    p.add_argument("--timestamps", action="store_true",
                   help="anade offsets por palabra")
    p.add_argument("--diarizacion", action="store_true",
                   help="etiqueta hablantes distintos")
    p.add_argument("--forzar-subida", action="store_true",
                   help="usar siempre la Files API en vez de enviar en linea")
    p.add_argument("--autotest", action="store_true",
                   help="prueba local del calculo de WER, sin llamar a la API")
    return p.parse_args(argv)


def seleccionar_audios(args: argparse.Namespace) -> list[Path]:
    if args.audios:
        rutas = []
        for r in args.audios:
            if not r.is_file():
                print(f"Ignorado (no existe): {r}", file=sys.stderr)
            elif not config.es_audio(r):
                print(f"Ignorado (formato no soportado): {r.name}", file=sys.stderr)
            else:
                rutas.append(r)
        return rutas

    rutas = config.descubrir_audios()
    if not rutas:
        print(
            f"No hay audio en {config.CARPETA_AUDIOS}/.\n"
            "Formatos admitidos: " + ", ".join(sorted(config.EXTENSIONES_AUDIO)),
            file=sys.stderr,
        )
    return rutas


def main(argv: list[str] | None = None) -> int:
    config.configurar_consola()
    args = recoger_argumentos(argv)

    if args.autotest:
        return 0 if autotest() else 1

    validar_opciones(args)
    rutas = seleccionar_audios(args)
    if not rutas:
        return 1

    from google import genai
    from google.genai import types

    cliente = genai.Client(api_key=config.obtener_clave())
    resultados = procesar(cliente, types, rutas, args)

    con_ref = [r for r in resultados if r.metrica and not r.error]
    if con_ref:
        media = sum(r.metrica.wer for r in con_ref) / len(con_ref)
        print(
            f"\nGemini: WER medio {media * 100:.1f}% "
            f"(precision media {(1 - media) * 100:.1f}%) "
            f"sobre {len(con_ref)} audio(s) con referencia."
        )
    print(f"Transcripciones en {config.CARPETA_RESULTADOS}/")

    return 1 if any(r.error for r in resultados) else 0


if __name__ == "__main__":
    raise SystemExit(main())
