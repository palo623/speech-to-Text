# Transcripcion de audio: Web Speech API vs Gemini

Comparacion de dos formas de pasar voz a texto, usando los **mismos 3 audios** y
midiendo la precision con el **mismo calculo** en ambos casos.

| Metodo | Donde corre | Como transcribe |
| --- | --- | --- |
| **A - Web Speech API** | Navegador (Chrome/Edge) | En tiempo real, desde el microfono |
| **B - Gemini** | Python, servidor | Por lotes, desde el fichero de audio |

## Estructura

```
Proyecto IA Transcribir/
├─ .env.example          Plantilla de la API key
├─ README.md             Instrucciones
├─ comparativa.md        Ventajas y desventajas de cada metodo
├─ requirements.txt      Dependencias
├─ src/
│  ├─ config.py          Rutas, credenciales, discovering de audios
│  ├─ wer.py             Metrica de precision (Word Error Rate)
│  ├─ transcribir.py     Metodo B: Gemini
│  ├─ webspeech.py       Metodo A: instrucciones de la pagina web
│  └─ comparar.py        Puntua ambos metodos y genera el informe
├─ web/
│  └─ index.html         Metodo A: la app de la Web Speech API
├─ audios/               Tus 3 audios + las referencias .txt
└─ resultados/           Transcripciones e informe (se genera solo)
```

## 1. Donde poner la API key

Solo la necesita el metodo B. La copia va en `src/config.py`, que la lee
automaticamente.

```powershell
Copy-Item .env.example .env
notepad .env
```

```
GEMINI_API_KEY=AIzaSy...tu_clave_real...
```

- Consigue la clave gratis en <https://aistudio.google.com/apikey>
- `.env` esta en `.gitignore`, no se sube al repositorio
- Sin `.env`, en su lugar: `$env:GEMINI_API_KEY = "AIzaSy..."` en PowerShell

## 2. Instalar

```powershell
py -3 -m pip install -r requirements.txt
```

## 3. Grabar los 3 audios

Ponlos en `audios/`, cada uno con su `.txt` de referencia (mismo nombre):

| Audio | Caso | Que demuestra |
| --- | --- | --- |
| `audio1` | Frase corta en silencio | Limite superior de precision |
| `audio2` | Frase con ruido de fondo | Robustez |
| `audio3` | Nombre propio o termino tecnico | Efecto de `--vocab` |

Sin el `.txt` de referencia no hay precision que medir: el script no tiene con
qué comparar.

## 4. Metodo B: Gemini

```powershell
py -3 src\transcribir.py
```

Guarda cada transcripcion en `resultados/<nombre>.gemini.txt`.

Opciones utiles:

```powershell
py -3 src\transcribir.py audios\audio1.wav        # ficheros concretos
py -3 src\transcribir.py --vocab "Kubernetes,BigQuery"   # sesgar terminos
py -3 src\transcribir.py --modo smart             # quita muletillas
py -3 src\transcribir.py --timestamps             # offset por palabra
py -3 src\transcribir.py --diarizacion            # etiqueta hablantes
py -3 src\transcribir.py --idioma auto            # autodeteccion
```

| Flag | Efecto |
| --- | --- |
| `--model` | Modelo (def. `gemini-3.5-transcribe`) |
| `--idioma` | BCP-47: `es-ES`, `es-ES,en-US`, o `auto` |
| `--vocab` | Sesga terminos (max. 1000) |
| `--modo` | `verbatim` (literal, def.) o `smart` (limpia muletillas) |
| `--timestamps` | Inicio y fin de cada palabra |
| `--diarizacion` | Distingue hasta 8 hablantes |
| `--forzar-subida` | Siempre por Files API, nunca en linea |

**Incompatibilidades** (la API las rechaza; el script avisa antes de gastar
tokens): `--vocab` no se combina con `--timestamps` ni `--diarizacion`, y
`--modo smart` ignora ambos.

## 5. Metodo A: Web Speech API

Es una pagina web, no un script. Abre `web\index.html` con doble clic, o si
Chrome bloquea el microfono en `file://`, sirve la carpeta:

```powershell
py -3 -m http.server 8000
```

y abre <http://localhost:8000/web/>.

1. Pon en "Nombre" el mismo que el audio (`audio1`).
2. Opcion A: pulsa **Empezar a grabar** y habla al microfono.
3. Opcion B: elige el fichero, pulsa **Reproducir y transcribir**.
4. **Guardar como .txt** y mueve el fichero a `resultados/`.

Quedara como `resultados/audio1.webspeech.txt`, que es lo que busca `comparar.py`.

```powershell
py -3 src\webspeech.py     # reminder de estos pasos por consola
```

## 6. Comparar

```powershell
py -3 src\comparar.py
```

Genera `resultados/informe.md` con el WER de cada metodo, audio por audio, y la
media de los que se pudieron puntuar con ambos.

Comprobar el calculo del WER sin llamar a ninguna API:

```powershell
py -3 src\comparar.py --autotest
```

## Como se mide la precision

```
WER = (sustituciones + borrados + inserciones) / palabras de la referencia
precision = 1 - WER
```

El texto se normaliza antes de comparar: minusculas, sin tildes, sin
puntuacion. Asi "Estás" frente a "estas" no cuenta como error, que es
justamente el tipo de diferencia que no dice nada sobre la calidad del
reconocimiento. El algoritmo de Levenshtein va en `src/wer.py`, sin
dependencias.

## Web Speech API vs Gemini

El detalle esta en [comparativa.md](comparativa.md). En corto:

| | Web Speech API | Gemini |
| --- | --- | --- |
| Entorno | Solo navegador | Cualquiera, servidor |
| Clave API | No hace falta | Si |
| Tipo | Tiempo real | Por lotes |
| Entrada | Solo microfono | Fichero |
| Precision | Buena, degrada con ruido | Mayor |
| Coste | Gratis | Tarifa por audio |

**Ojo con la comparacion de WER**: la Web Speech API solo admite microfono, asi
que para puntuar un fichero hay que reproducirlo por los altavoces y capturarlo
de nuevo. El audio pasa dos veces por el microfono y llega degradado, mientras
que Gemini recibe el fichero digital intacto. La comparacion de WER entre
ambos no es del todo justa, y conviene decirlo en las conclusiones.
