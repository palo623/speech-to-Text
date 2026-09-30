# Web Speech API vs Gemini

Dos tecnicas para lo mismo: pasar voz a texto. La eleccion depende de si
necesitas **subtitulado en vivo** o **transcribir ficheros ya grabados**.

## Comparativa

| Caracteristica | Web Speech API | Gemini (`gemini-3.5-transcribe`) |
| --- | --- | --- |
| Entorno | Solo navegador (Chrome, Edge) | Servidor, cualquier lenguaje |
| Clave API | No hace falta | Si, `GEMINI_API_KEY` |
| Tipo de proceso | Tiempo real (subtitulado en vivo) | Por lotes (fichero completo) |
| Resultado provisional | Si (`interimResults`) | No, entrega el texto final |
| Entrada | **Solo microfono** | **Fichero** `.wav .mp3 .webm ...` |
| Ficheros grandes | No aplica | Si, via Files API (hasta 2 GB) |
| Duracion maxima | ~60 s por sesion en Chrome | 9,5 h de audio por peticion |
| Precision | Buena; degrada con ruido | Mayor, entrenado en audio |
| Vocabulario a medida | No | Si (`custom_vocabulary`) |
| Idioma forzado | Parcial (`lang="es-ES"`) | BCP-47 explicito + autodeteccion |
| Multi-idioma / code-switching | No | Si, detecta por intervencion |
| Acentos y dialectos | Limitado | 85+ idiomas, incluidos dialectos |
| Timestamps por palabra | No | Si |
| Diarizacion (hablantes) | No | Si, hasta 8 hablantes |
| Quitar muletillas | No | Si (`mode=smart`) |
| Coste | Gratis | Tarifa por minuto de audio |
| Privacidad | Chrome envia el audio a servidores de Google | Audio al servicio de Gemini, 48 h en Files API |
| Requiere red | Si | Si |
| Sin conexion | No | No |

## Ventajas

### Web Speech API

- **Cero configuracion**: ni clave API, ni `pip install`, ni servidor.   Se abre
  una pagina y funciona.
- **Latencia minima**: el texto sale mientras hablas. Para dictar un correo o
  buscar por voz, esperar al final no tiene sentido.
- **Gratis** y sin cuotas ni facturacion.
- **Integracion trivial** en cualquier formulario web.

### Gemini

- **Trabaaja con ficheros**, que es el caso real: una reunion grabada, un
  podcast, la llamadas de atencion al cliente.
- **Mas preciso**, sobre todo con acentos, ruido de fondo y voz lejana.
- **Contexto de dominio**: con `custom_vocabulary` se le dicen los terminos
  propios ("Kubernetes", "BigQuery", nombres de productos) y deja de
  inventarselos.
- **Autodetecta el idioma** y aguanta cambios de idioma a media frase, que el
  navegador no hace.
- **Metadatos utiles**: timestamps por palabra y diarizacion, para subtitular o
  separar-who-ha-hablado.
- **Lotes y automatizacion**: cabe en un script, se ejecuta sin supervision y
  escala a cientos de ficheros.

## Desventajas

### Web Speech API

- **Solo navegador**. No hay servidor, ni Python, ni Node. Si el dato tiene que
  acabar en una base de datos o en un informe, hay que exportarlo del
  navegador.
- **Solo microfono**. Esta es la limitacion importante: para transcribir un
  `.wav` hay que reproducirlo y capturarlo por la entrada de linea, lo que
  anade ruido y penaliza la precision. No hay forma de darle el fichero.
- **Se corta a los ~60 s** en Chrome con `continuous=true`, y hay que rearmar.
- **Solo Chromium**: no funciona en Firefox ni Safari.
- **Sin control fino**: ni vocabulario, ni timestamps, ni diarizacion, ni
  limpieza de muletillas.
- **Sin control del modelo**: si falla, no hay a quien preguntar.
- **Privacidad**: el audio sale del equipo a servidores de Google sin que se
  pueda elegir.

### Gemini

- **Necesita clave API y facturacion**: hay que pedir la clave, vigilar el
  consumo y medir el gasto si se usa en volumen.
- **No es tiempo real**: entrega el texto final. Para dictado en vivo hay que ir
  a la API Live, con lo que eso implica de infraestructura.
- **Solo por el servidor**: Python, Node, Java... no desde un HTML suelto.
- **Latencia por lote**: para un audio largo hay que esperar a que termine el
  fichero completo.
- **Coste por volumen**: miles de horas de audio se notan en la factura.
- **Los ficheros subidos se guardan 48 h** en la Files API (este script los
  borra al terminar). Relevante si hay datos personales o confidenciales.
- **Depende del prompt y del formato**: si no se le pide una transcripcion, puede
  resumir o inventar. Con el modelo de transcripcion esto se evita, pero
  conviene saberlo.

## Cuando usar cada una

**Web Speech API** - dictado en vivo, busqueda por voz, formularios con entrada
de texto hablada. Todo lo que pase en el navegador y necesite respuesta
inmediata.

**Gemini** - ficheros ya grabados: entrevistas, podcasts, reuniones, atencion al
cliente. Todo lo que necesite mas precision, vocabulario del dominio,
timestamps o separacion de hablantes.

**Las dos** - dictated en vivo con la Web Speech API y, al terminar, se le pasa
el audio a Gemini para una transcripcion limpia y con metadatos. Cubre el
tiempo real y la calidad, que es justo lo que ninguna de las dos da sola.

## Advertencia sobre la fairness de la comparacion

Al puntuar las dos tecnicas con el mismo WER hay un sesgo inevitable: la Web
Speech API solo admite microfono, asi que para transcribir un fichero se
reproduce por los altavoces y se vuelve a captar. El audio pasa dos veces por
el microfono y llega con ruido y distorsion anadidos, mientras que Gemini
recibe el fichero digital sin tocar.

Es decir, el WER de la Web Speech API mide el rendimiento de la API **mas** el
de la cadena de audio de alta. La diferencia real entre ambos modelos es
probablemente mayor que la que muestra la tabla.

Para una medida mas justa habria que comparar la Web Speech API contra si misma
en la misma situacion, o comparar los dos metodos con datos grabados
directamente a microfono en lugar de ficheros.
