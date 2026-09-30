"""
ASIX Profile: API Endpoint para transcripcion de audio con Gemini.

Arquitectura de red:
┌─────────────┐     HTTP POST /transcribir      ┌─────────────┐     gRPC/REST      ┌──────────────┐
│   Cliente   │ ──────────────────────────────▶ │  FastAPI    │ ─────────────────▶ │  Google      │
│  (curl,     │  multipart/form-data            │  Server     │  google-genai SDK  │  Gemini API  │
│  Postman,   │  audio file + params            │  (uvicorn)  │                    │  (Vertex AI) │
│  navegador) │ ◀────────────────────────────── │  :8000      │ ◀───────────────── │              │
└─────────────┘     JSON {texto, metadata}      └─────────────┘                    └──────────────┘

Flujos de datos:
1. Cliente envia POST /transcribir con archivo audio (multipart/form-data)
2. FastAPI valida extension, tamaño (<=25MB), y parametros opcionales
3. Servidor usa google-genai SDK para enviar audio a Gemini (inline o Files API)
4. Gemini procesa y devuelve transcripcion
5. FastAPI responde con JSON: {texto, duracion, modelo, idioma, ...}

Endpoints:
- POST   /transcribir       Transcribe un archivo de audio
- GET    /health            Health check
- GET    /docs              Documentacion Swagger/OpenAPI automatica
"""

from __future__ import annotations

import time
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Importar configuracion y logica existente
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.transcribir import (
    transcribir_un_audio,
    construir_config,
    validar_opciones,
    Resultado,
)
import argparse
from google import genai
from google.genai import types

# --------------------------------------------------------------------------
# Modelos Pydantic para request/response
# --------------------------------------------------------------------------

class TranscripcionRequest(BaseModel):
    """Parametros opcionales de transcripcion."""
    modelo: str = Field(default=config.MODELO_POR_DEFECTO, description="Modelo Gemini a usar")
    idioma: str = Field(default="es-ES", description="Codigos BCP-47 separados por coma, o 'auto'")
    vocab: Optional[str] = Field(default=None, description="Terminos a sesgar, separados por coma")
    modo: str = Field(default="verbatim", description="verbatim o smart")
    timestamps: bool = Field(default=False, description="Incluir timestamps por palabra")
    diarizacion: bool = Field(default=False, description="Etiquetar hablantes distintos")


class TranscripcionResponse(BaseModel):
    """Respuesta de la transcripcion."""
    texto: str
    audio_original: str
    duracion_segundos: float
    modelo: str
    idioma: str
    modo: str
    detalles: str  # "inline" o "Files API"
    palabras: int
    exito: bool = True
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    servicio: str = "ASIX Transcripcion API"
    version: str = "1.0.0"
    modelo_disponible: str = config.MODELO_POR_DEFECTO


# --------------------------------------------------------------------------
# FastAPI App
# --------------------------------------------------------------------------

app = FastAPI(
    title="ASIX Transcripcion API",
    description=(
        "Endpoint para transcripcion de audio usando Google Gemini. "
        "Recibe archivos de audio y devuelve el texto transcrito."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS para permitir peticiones desde navegador (DAW/DAM)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En produccion: dominios especificos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cliente Gemini global (se inicializa al arrancar)
gemini_client: genai.Client | None = None


@app.on_event("startup")
async def startup_event():
    """Inicializar cliente Gemini al arrancar el servidor."""
    global gemini_client
    try:
        api_key = config.obtener_clave()
        gemini_client = genai.Client(api_key=api_key)
        print(f"[STARTUP] Cliente Gemini inicializado con modelo {config.MODELO_POR_DEFECTO}")
    except SystemExit as e:
        print(f"[STARTUP] ERROR: {e}")
        # No lanzamos excepcion para que /health siga funcionando


@app.on_event("shutdown")
async def shutdown_event():
    """Limpieza al apagar."""
    pass


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Sistema"])
async def health_check():
    """Verifica que el servicio esta operativo."""
    return HealthResponse()


@app.post(
    "/transcribir",
    response_model=TranscripcionResponse,
    tags=["Transcripcion"],
    summary="Transcribe un archivo de audio",
    description=(
        "Sube un archivo de audio (wav, mp3, m4a, etc.) y obtiene la transcripcion "
        "usando Google Gemini. Soporta parametros opcionales para personalizar la transcripcion."
    ),
)
async def transcribir_audio(
    archivo: UploadFile = File(..., description="Archivo de audio a transcribir"),
    modelo: str = Form(default=config.MODELO_POR_DEFECTO),
    idioma: str = Form(default="es-ES"),
    vocab: Optional[str] = Form(default=None),
    modo: str = Form(default="verbatim"),
    timestamps: bool = Form(default=False),
    diarizacion: bool = Form(default=False),
):
    """
    Transcribe un archivo de audio enviado via multipart/form-data.
    
    **Parametros:**
    - **archivo**: Archivo de audio (wav, mp3, m4a, ogg, flac, webm, etc.)
    - **modelo**: Modelo Gemini (def: gemini-3.5-transcribe)
    - **idioma**: Codigos BCP-47 (ej: es-ES, en-US, auto)
    - **vocab**: Terminologia especifica separada por comas
    - **modo**: verbatim (literal) o smart (limpia muletillas)
    - **timestamps**: Incluir offset temporal por palabra
    - **diarizacion**: Identificar hablantes distintos
    
    **Respuesta:**
    ```json
    {
      "texto": "Texto transcrito...",
      "audio_original": "audio.wav",
      "duracion_segundos": 2.34,
      "modelo": "gemini-3.5-transcribe",
      "idioma": "es-ES",
      "modo": "verbatim",
      "detalles": "inline",
      "palabras": 42,
      "exito": true
    }
    ```
    """
    # Validar que hay cliente Gemini
    if gemini_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cliente Gemini no inicializado. Verifica GEMINI_API_KEY en .env"
        )

    # Validar extension
    if not config.es_audio(Path(archivo.filename or "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Formato no soportado: {archivo.filename}. "
                f"Formatos validos: {', '.join(sorted(config.EXTENSIONES_AUDIO))}"
            ),
        )

    # Validar tamaño (max 25MB para evitar timeouts en HTTP)
    contenido = await archivo.read()
    if len(contenido) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Archivo demasiado grande (max 25MB). Usa Files API para archivos mayores."
        )

    # Guardar temporalmente
    suffix = Path(archivo.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(contenido)
        tmp_path = Path(tmp.name)

    try:
        # Construir namespace tipo argparse para reutilizar logica existente
        args = argparse.Namespace(
            model=modelo,
            idioma=idioma,
            vocab=[t.strip() for t in vocab.split(",")] if vocab else None,
            modo=modo,
            timestamps=timestamps,
            diarizacion=diarizacion,
            forzar_subida=False,
        )

        # Validar incompatibilidades
        validar_opciones(args)

        # Transcribir usando la logica existente
        resultado = transcribir_un_audio(gemini_client, types, tmp_path, args)

        if resultado.error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error en Gemini: {resultado.error}"
            )

        return TranscripcionResponse(
            texto=resultado.texto,
            audio_original=archivo.filename or "desconocido",
            duracion_segundos=round(resultado.segundos, 2),
            modelo=modelo,
            idioma=idioma,
            modo=modo,
            detalles=resultado.detalles,
            palabras=len(resultado.texto.split()) if resultado.texto else 0,
            exito=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {type(e).__name__}: {e}"
        )
    finally:
        # Limpiar archivo temporal
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.post(
    "/transcribir/lote",
    response_model=List[TranscripcionResponse],
    tags=["Transcripcion"],
    summary="Transcribe multiples archivos de audio",
    description="Procesa varios archivos en una sola peticion (hasta 10 archivos).",
)
async def transcribir_lote(
    archivos: List[UploadFile] = File(..., description="Lista de archivos de audio"),
    modelo: str = Form(default=config.MODELO_POR_DEFECTO),
    idioma: str = Form(default="es-ES"),
    vocab: Optional[str] = Form(default=None),
    modo: str = Form(default="verbatim"),
    timestamps: bool = Form(default=False),
    diarizacion: bool = Form(default=False),
):
    """Transcribe multiples archivos en una sola peticion."""
    if gemini_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cliente Gemini no inicializado"
        )

    if len(archivos) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximo 10 archivos por lote"
        )

    args = argparse.Namespace(
        model=modelo,
        idioma=idioma,
        vocab=[t.strip() for t in vocab.split(",")] if vocab else None,
        modo=modo,
        timestamps=timestamps,
        diarizacion=diarizacion,
        forzar_subida=False,
    )
    validar_opciones(args)

    resultados = []
    for archivo in archivos:
        if not config.es_audio(Path(archivo.filename or "")):
            resultados.append(TranscripcionResponse(
                texto="",
                audio_original=archivo.filename or "desconocido",
                duracion_segundos=0,
                modelo=modelo,
                idioma=idioma,
                modo=modo,
                detalles="error",
                palabras=0,
                exito=False,
                error=f"Formato no soportado: {archivo.filename}"
            ))
            continue

        contenido = await archivo.read()
        if len(contenido) > 25 * 1024 * 1024:
            resultados.append(TranscripcionResponse(
                texto="",
                audio_original=archivo.filename or "desconocido",
                duracion_segundos=0,
                modelo=modelo,
                idioma=idioma,
                modo=modo,
                detalles="error",
                palabras=0,
                exito=False,
                error="Archivo demasiado grande (>25MB)"
            ))
            continue

        suffix = Path(archivo.filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contenido)
            tmp_path = Path(tmp.name)

        try:
            resultado = transcribir_un_audio(gemini_client, types, tmp_path, args)
            if resultado.error:
                resultados.append(TranscripcionResponse(
                    texto="",
                    audio_original=archivo.filename,
                    duracion_segundos=round(resultado.segundos, 2),
                    modelo=modelo,
                    idioma=idioma,
                    modo=modo,
                    detalles="error",
                    palabras=0,
                    exito=False,
                    error=resultado.error
                ))
            else:
                resultados.append(TranscripcionResponse(
                    texto=resultado.texto,
                    audio_original=archivo.filename,
                    duracion_segundos=round(resultado.segundos, 2),
                    modelo=modelo,
                    idioma=idioma,
                    modo=modo,
                    detalles=resultado.detalles,
                    palabras=len(resultado.texto.split()) if resultado.texto else 0,
                    exito=True,
                ))
        except Exception as e:
            resultados.append(TranscripcionResponse(
                texto="",
                audio_original=archivo.filename or "desconocido",
                duracion_segundos=0,
                modelo=modelo,
                idioma=idioma,
                modo=modo,
                detalles="error",
                palabras=0,
                exito=False,
                error=f"{type(e).__name__}: {e}"
            ))
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    return resultados


# --------------------------------------------------------------------------
# Ejecucion directa
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print("Iniciando servidor ASIX Transcripcion API en http://localhost:8000")
    print("Documentacion: http://localhost:8000/docs")
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)