# Documentación de Arquitectura de Red - Perfil ASIX

## Transcripción de Audio con Google Gemini API

---

## 1. Visión General

Esta implementación proporciona un **endpoint API REST** (FastAPI) que recibe archivos de audio, los envía a **Google Gemini** para transcripción y devuelve el texto resultante en formato JSON.

### Perfil: ASIX (Administración de Sistemas Informáticos en Red)

El enfoque se centra en:
- **Arquitectura cliente-servidor** bien definida
- **Protocolos de red** (HTTP/REST, gRPC interno de Gemini)
- **Seguridad** (API keys, validación, CORS)
- **Observabilidad** (health checks, logging, métricas)
- **Escalabilidad** (stateless, procesamiento por lotes)

---

## 2. Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ARQUITECTURA DE RED                              │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────┐         HTTPS (REST)          ┌────────────────────────┐
    │  CLIENTE │ ────────────────────────────▶ │      FASTAPI           │
    │          │  multipart/form-data          │      SERVER            │
    │  • curl  │  audio file (≤25MB)           │      (uvicorn)         │
    │  • Postman│  + params opcionales         │      :8000             │
    │  • Naveg.│ ◀──────────────────────────── │                        │
    └──────────┘    JSON Response              └───────────┬────────────┘
                                                           │
                                                           │ gRPC/REST
                                                           ▼
                                                ┌────────────────────────┐
                                                │   GOOGLE GEMINI API    │
                                                │   (Vertex AI)          │
                                                │                        │
                                                │  • gemini-3.5-transcribe│
                                                │  • Files API (>20MB)   │
                                                │  • Inline (<20MB)      │
                                                └────────────────────────┘

FLUJO DE DATOS:
┌─────────┐    1. POST /transcribir    ┌─────────┐    2. Validación     ┌─────────┐
│ Cliente │ ─────────────────────────▶ │ FastAPI │ ──────────────────▶ │  Archivo │
└─────────┘   (multipart/form-data)    └─────────┘   temporal en disco   └─────────┘
                                                              │
                                                              ▼
┌─────────┐    5. JSON Response       ┌─────────┐    3. google-genai    ┌─────────┐
│ Cliente │ ◀──────────────────────── │ FastAPI │ ◀────────────────── │ Gemini  │
└─────────┘   {texto, metadata}       └─────────┘      SDK              └─────────┘
                                                              ▲
                                                              │
                                                    4. Transcripción
                                                       (procesamiento IA)
```

---

## 3. Componentes de Red

### 3.1 Cliente
- **Cualquier cliente HTTP**: curl, Postman, fetch/axios (navegador), Python requests
- **Autenticación**: No requerida a nivel HTTP (API key en servidor)
- **Formato petición**: `multipart/form-data`
- **Límite**: 25MB por archivo (configurable)

### 3.2 Servidor FastAPI (Capa de Aplicación)
| Componente | Tecnología | Puerto | Protocolo |
|------------|------------|--------|-----------|
| API REST | FastAPI 0.109+ | 8000 | HTTP/1.1, HTTP/2 |
| ASGI Server | Uvicorn | 8000 | ASGI |
| Validación | Pydantic v2 | - | - |
| CORS | Starlette CORSMiddleware | - | - |

**Endpoints:**
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Health check (kubernetes probes) |
| POST | `/transcribir` | Transcripción individual |
| POST | `/transcribir/lote` | Transcripción múltiple (≤10) |
| GET | `/docs` | Swagger UI (OpenAPI 3.0) |
| GET | `/redoc` | ReDoc documentation |

### 3.3 Capa de Integración (google-genai SDK)
- **Protocolo**: gRPC (preferido) / REST fallback
- **Autenticación**: API Key en header `x-goog-api-key`
- **Endpoint**: `generativelanguage.googleapis.com` (Google AI) o Vertex AI
- **Modelo**: `gemini-3.5-transcribe` (especializado en STT)

### 3.4 Google Gemini API (Servicio Externo)
- **Arquitectura**: Serverless, gestionado por Google
- **Escalado**: Automático
- **Regiones**: Multi-región (us-central1, europe-west1, etc.)
- **SLA**: 99.9% disponibilidad (Vertex AI)

---

## 4. Protocolos y Formatos

### 4.1 Petición POST /transcribir

```http
POST /transcribir HTTP/1.1
Host: localhost:8000
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="archivo"; filename="audio.wav"
Content-Type: audio/wav

<binary audio data>
------WebKitFormBoundary
Content-Disposition: form-data; name="modelo"

gemini-3.5-transcribe
------WebKitFormBoundary
Content-Disposition: form-data; name="idioma"

es-ES
------WebKitFormBoundary
Content-Disposition: form-data; name="modo"

verbatim
------WebKitFormBoundary
Content-Disposition: form-data; name="timestamps"

false
------WebKitFormBoundary
Content-Disposition: form-data; name="diarizacion"

false
------WebKitFormBoundary--
```

### 4.2 Respuesta Exitosa (200 OK)

```json
{
  "texto": "Hola mundo, esta es una prueba de transcripción.",
  "audio_original": "audio.wav",
  "duracion_segundos": 2.34,
  "modelo": "gemini-3.5-transcribe",
  "idioma": "es-ES",
  "modo": "verbatim",
  "detalles": "inline",
  "palabras": 10,
  "exito": true,
  "error": null
}
```

### 4.3 Respuesta de Error (4xx/5xx)

```json
{
  "detail": "Error en Gemini: DEADLINE_EXCEEDED: Request timeout"
}
```

### 4.4 Códigos de Estado HTTP

| Código | Significado | Cuándo ocurre |
|--------|-------------|---------------|
| 200 | OK | Transcripción exitosa |
| 400 | Bad Request | Formato no soportado, parámetros inválidos |
| 413 | Payload Too Large | Archivo > 25MB |
| 422 | Unprocessable Entity | Incompatibilidad de opciones (vocab + timestamps) |
| 502 | Bad Gateway | Error en Gemini API |
| 503 | Service Unavailable | Cliente Gemini no inicializado (falta API key) |
| 504 | Gateway Timeout | Gemini tarda demasiado |

---

## 5. Seguridad

### 5.1 Gestión de Credenciales
- **API Key Gemini**: Almacenada en `.env` (no en código)
- **Carga**: `python-dotenv` pattern manual (sin dependencias extra)
- **Variable**: `GEMINI_API_KEY` o `GOOGLE_API_KEY`
- **Rotación**: Cambiar en `.env` y reiniciar servidor

### 5.2 Validación de Entrada
- **Extensiones permitidas**: Lista blanca (wav, mp3, m4a, ogg, flac, webm, etc.)
- **Tamaño máximo**: 25MB (evita DoS y timeouts HTTP)
- **Content-Type**: Verificado via extensión + magic bytes opcional
- **Sanitización**: Nombres de archivo seguros (tempfile)

### 5.3 CORS
```python
# Configuración actual (desarrollo)
allow_origins=["*"]  # TODO: restringir en producción
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

**Producción recomendada:**
```python
allow_origins=["https://app.tudominio.com", "https://dashboard.tudominio.com"]
```

### 5.4 Rate Limiting (Pendiente)
- Implementar con `slowapi` o middleware personalizado
- Ejemplo: 60 req/min por IP

---

## 6. Despliegue

### 6.1 Desarrollo Local
```powershell
# 1. Instalar dependencias
py -3 -m pip install -r requirements.txt

# 2. Configurar API key
Copy-Item .env.example .env
notepad .env  # pegar GEMINI_API_KEY

# 3. Ejecutar servidor
py -3 src/api.py
# O directamente con uvicorn:
py -3 -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
```

### 6.2 Producción (Docker)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY .env .env

EXPOSE 8000
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 6.3 Kubernetes (Resumen)

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: asix-transcripcion-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: asix-transcripcion-api
  template:
    metadata:
      labels:
        app: asix-transcripcion-api
    spec:
      containers:
      - name: api
        image: tu-registry/asix-transcripcion:latest
        ports:
        - containerPort: 8000
        env:
        - name: GEMINI_API_KEY
          valueFrom:
            secretKeyRef:
              name: gemini-secret
              key: api-key
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: asix-transcripcion-api
spec:
  selector:
    app: asix-transcripcion-api
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
```

---

## 7. Observabilidad

### 7.1 Health Checks
```bash
# Liveness probe
curl -f http://localhost:8000/health

# Respuesta esperada:
# {"status":"ok","servicio":"ASIX Transcripcion API","version":"1.0.0","modelo_disponible":"gemini-3.5-transcribe"}
```

### 7.2 Logging
- **Nivel**: INFO (requests), ERROR (fallos Gemini)
- **Formato**: JSON estructurado (producción)
- **Campos clave**: timestamp, endpoint, client_ip, duration_ms, status_code, audio_duration

### 7.3 Métricas Sugeridas (Prometheus)
| Métrica | Tipo | Descripción |
|---------|------|-------------|
| `http_requests_total` | Counter | Peticiones por endpoint/status |
| `http_request_duration_seconds` | Histogram | Latencia peticiones |
| `transcription_duration_seconds` | Histogram | Tiempo procesamiento Gemini |
| `transcription_errors_total` | Counter | Errores por tipo |
| `audio_size_bytes` | Histogram | Tamaño archivos recibidos |

---

## 8. Escalabilidad y Rendimiento

### 8.1 Cuellos de Botella
1. **Gemini API**: Latencia de red + procesamiento IA (1-10s típicos)
2. **Subida de archivos**: Ancho de banda cliente → servidor
3. **Archivos >20MB**: Files API añade 2-5s extra (upload + processing)

### 8.2 Estrategias de Escalado
- **Horizontal**: Múltiples réplicas FastAPI (stateless)
- **Cola de trabajo**: Para archivos grandes, usar Redis + workers (Celery/RQ)
- **Cache**: No aplica (cada audio es único)
- **CDN**: Solo para servir docs estáticos (/docs)

### 8.3 Timeouts Recomendados
| Componente | Timeout |
|------------|---------|
| Cliente HTTP | 60s (configurable) |
| Uvicorn keep-alive | 75s |
| Gemini SDK | 120s (default) |
| Load Balancer | 90s |

---

## 9. Testing

### 9.1 Pruebas Manuales

```bash
# Health check
curl http://localhost:8000/health

# Transcripción simple
curl -X POST http://localhost:8000/transcribir \
  -F "archivo=@audios/audio1.m4a" \
  -F "idioma=es-ES" \
  -F "modo=verbatim"

# Con timestamps y diarización
curl -X POST http://localhost:8000/transcribir \
  -F "archivo=@audios/audio2.wav" \
  -F "timestamps=true" \
  -F "diarizacion=true"

# Lote (múltiples archivos)
curl -X POST http://localhost:8000/transcribir/lote \
  -F "archivos=@audios/audio1.m4a" \
  -F "archivos=@audios/audio2.wav"
```

### 9.2 Pruebas Automatizadas
```powershell
# Ejecutar script de prueba (requiere servidor corriendo)
py -3 src/test_api.py
```

### 9.3 Casos de Prueba de Carga (locust/k6)
```python
# locustfile.py
from locust import HttpUser, task, between

class TranscripcionUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def transcribir(self):
        with open("audios/audio1.m4a", "rb") as f:
            self.client.post("/transcribir", files={"archivo": f})
```

---

## 10. Troubleshooting

| Problema | Causa | Solución |
|----------|-------|----------|
| `503 Service Unavailable` | Falta GEMINI_API_KEY | Verificar `.env` y reiniciar |
| `413 Payload Too Large` | Archivo > 25MB | Aumentar límite o usar Files API directo |
| `502 Bad Gateway` | Error Gemini (quota, red) | Reintentar, verificar cuota en AI Studio |
| `422 Unprocessable` | vocab + timestamps | Quitar una opción incompatible |
| Timeout cliente | Audio muy largo | Aumentar timeout cliente, usar lote asíncrono |
| CORS error navegador | Origen no permitido | Configurar `allow_origins` en producción |

---

## 11. Referencias

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Google Gemini API Docs](https://ai.google.dev/gemini-api/docs)
- [google-genai Python SDK](https://github.com/googleapis/python-genai)
- [Uvicorn Deployment](https://www.uvicorn.org/deployment/)
- [OpenAPI 3.0 Spec](https://swagger.io/specification/)

---

*Documento generado para el Reto del Día - Perfil ASIX*
*Fecha: 2026-09-30*