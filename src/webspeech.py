"""
Metodo A: transcripcion en tiempo real con la Web Speech API (navegador).

Solo funciona en el navegador (Chrome o Edge) y solo con microfono: por eso
esta parte se implementa como pagina web, no como script de Python.

Para compararla con Gemini sobre los MISMOS audios, el flujo es:
  1. Reproduces el audio por los altavoces con el microfono capturando.
  2. La Web Speech API transcribe en vivo.
  3. Guardas el resultado con el boton "Guardar como .txt" y lo dejas en
     resultados/<nombre>.webspeech.txt
  4. comparar.py puntua ambos metodos con el mismo WER.

Aviso: el paso 1 reintroduce el audio por el microfono, asi que la Web Speech
API parte de una senal mas degradada que Gemini. El informe lo señala.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config


def comprobar_entorno() -> int:
    """Comprueba que existe un audio de referencia y avisa de los requisitos."""
    config.configurar_consola()
    print("Metodo A: Web Speech API (navegador)")
    print()
    print("Se usa desde el navegador, no desde Python. Pasos:")
    print()
    print(f"  1. Abre  web\\index.html  con doble clic, o sirve la carpeta:")
    print(f"       py -3 -m http.server 8000    (despues http://localhost:8000/web/)")
    print()
    print("  2. En la pagina:")
    print("     - Escribe el nombre del audio en 'Nombre' (audio1, audio2, ...)")
    print("     - Pulsa 'Empezar a grabar' y habla al microfono")
    print("     - O elige un fichero y pulsa 'Reproducir y transcribir'")
    print("     - Pulsa 'Guardar como .txt' y mueve el fichero descargado")
    print("       a  resultados\\<nombre>.webspeech.txt")
    print()
    print("  3. Vuelve aqui y puntua ambos metodos:")
    print("       py -3 src\\comparar.py")
    print()

    audios = config.descubrir_audios()
    if not audios:
        print(f"Aviso: no hay audio en {config.CARPETA_AUDIOS}/ todavia.")
        return 0

    print(f"Audios detectados ({len(audios)}):")
    for a in audios:
        ref = config.ruta_referencia(a)
        estado = "con referencia" if ref.is_file() else "SIN referencia"
        print(f"  - {a.name} ({estado})")

    sin_ref = [a for a in audios if not config.ruta_referencia(a).is_file()]
    if sin_ref:
        print()
        print("Sin .txt de referencia no se puede medir la precision de:")
        for a in sin_ref:
            print(f"  - {a.name}")
        print("Escribe a mano lo que dijiste en un .txt con el mismo nombre.")

    return 0


def main() -> int:
    return comprobar_entorno()


if __name__ == "__main__":
    raise SystemExit(main())
