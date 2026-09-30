"""
Script de prueba para la API ASIX.

Uso:
    py -3 src/test_api.py

Prueba los endpoints /health y /transcribir con un audio de ejemplo.
"""

import sys
from pathlib import Path
import requests
import time

# Añadir raiz al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "http://localhost:8000"


def test_health():
    """Prueba el endpoint /health."""
    print("\n=== TEST /health ===")
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")
        return resp.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_transcribir(audio_path: Path):
    """Prueba el endpoint /transcribir con un archivo."""
    print(f"\n=== TEST /transcribir con {audio_path.name} ===")
    try:
        with open(audio_path, "rb") as f:
            files = {"archivo": (audio_path.name, f, "audio/m4a")}
            data = {
                "modelo": "gemini-3.5-transcribe",
                "idioma": "es-ES",
                "modo": "verbatim",
            }
            resp = requests.post(f"{BASE_URL}/transcribir", files=files, data=data, timeout=60)
        
        print(f"Status: {resp.status_code}")
        result = resp.json()
        print(f"Exito: {result.get('exito')}")
        print(f"Texto: {result.get('texto', '')[:100]}...")
        print(f"Duracion: {result.get('duracion_segundos')}s")
        print(f"Palabras: {result.get('palabras')}")
        print(f"Detalles: {result.get('detalles')}")
        if result.get('error'):
            print(f"Error: {result['error']}")
        return resp.status_code == 200 and result.get('exito')
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def main():
    print("Pruebas de la API ASIX Transcripcion")
    print("=" * 50)
    print(f"URL base: {BASE_URL}")
    print("Asegurate de que el servidor este corriendo: py -3 src/api.py")
    
    # Test health
    if not test_health():
        print("\n[FALLO] Health check fallo. Servidor no disponible.")
        return 1
    
    # Buscar audio de prueba
    from src.config import CARPETA_AUDIOS, descubrir_audios
    audios = descubrir_audios(CARPETA_AUDIOS)
    
    if not audios:
        print("\n[AVISO] No hay audios en la carpeta audios/ para probar.")
        return 0
    
    # Probar con el primer audio
    test_transcribir(audios[0])
    
    print("\n=== RESUMEN ===")
    print("Pruebas completadas. Revisa la salida arriba.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())