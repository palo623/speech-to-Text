"""
Configuracion compartida: credenciales, rutas y discovering de audios.

Centraliza lo que ambos metodos necesitan para saber donde esta la API key y
donde estan los ficheros, para que ningun script tenga que hardcodear rutas.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Rutas absolutas relativas a la raiz del proyecto (padre de src/).
RAIZ = Path(__file__).resolve().parent.parent
CARPETA_AUDIOS = RAIZ / "audios"
CARPETA_RESULTADOS = RAIZ / "resultados"
RUTA_ENV = RAIZ / ".env"
RUTA_ENV_EJEMPLO = RAIZ / ".env.example"

# Modelo de transcripcion de Google. Ver README para el resto de opciones.
MODELO_POR_DEFECTO = "gemini-3.5-transcribe"

# La API acepta hasta 20 MB en linea; por encima hay que usar la Files API.
LIMITE_BYTES_INLINE = 20 * 1024 * 1024

MIME_POR_EXTENSION = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".m4a": "audio/m4a",
    ".aac": "audio/aac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/opus",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".mpeg": "audio/mpeg",
    ".mpg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".l16": "audio/l16",
    ".alaw": "audio/alaw",
    ".mulaw": "audio/mulaw",
}

EXTENSIONES_AUDIO = set(MIME_POR_EXTENSION)


# --------------------------------------------------------------------------
# Salida por consola en UTF-8 (Windows usa cp1252 y rompe las tildes)
# --------------------------------------------------------------------------
def configurar_consola() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


# --------------------------------------------------------------------------
# Credenciales
# --------------------------------------------------------------------------
def cargar_dotenv(ruta: Path | str = RUTA_ENV) -> None:
    """Carga un .env sencillo sin dependencias. No pisa variables ya puestas."""
    ruta = Path(ruta)
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        if valor:
            os.environ.setdefault(clave, valor)


def obtener_clave() -> str:
    """Devuelve la API key o aborta con instrucciones claras."""
    cargar_dotenv()
    for nombre in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        clave = os.environ.get(nombre)
        if clave and clave.strip():
            return clave.strip()
    raise SystemExit(
        "Falta la API key de Gemini.\n"
        "\n"
        "Opcion 1 - fichero .env (la mas comoda):\n"
        f"  1) Copia el ejemplo:  Copy-Item \"{RUTA_ENV_EJEMPLO.name}\" .env\n"
        f"  2) Abre el .env y pega tu clave en GEMINI_API_KEY=...\n"
        "\n"
        "Opcion 2 - variable de entorno en PowerShell:\n"
        '  $env:GEMINI_API_KEY = "AIzaSy..."\n'
        "\n"
        "La clave se consigue gratis en https://aistudio.google.com/apikey"
    )


# --------------------------------------------------------------------------
# Audios
# --------------------------------------------------------------------------
def es_audio(ruta: Path) -> bool:
    return ruta.suffix.lower() in EXTENSIONES_AUDIO


def descubrir_audios(carpeta: Path = CARPETA_AUDIOS) -> list[Path]:
    """Devuelve los audios de la carpeta ignorando el LEEME y subcarpetas."""
    if not carpeta.is_dir():
        return []
    return sorted(
        p for p in carpeta.iterdir() if p.is_file() and es_audio(p)
    )


def ruta_referencia(audio: Path) -> Path:
    """Transcripcion de referencia: mismo nombre, extension .txt."""
    return audio.with_suffix(".txt")


def ruta_salida(audio: Path, sufijo: str) -> Path:
    """Destino de una transcripcion: resultados/<nombre><sufijo>.txt."""
    return CARPETA_RESULTADOS / f"{audio.stem}{sufijo}.txt"
