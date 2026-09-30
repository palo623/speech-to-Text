# Arquitectura de Red - API de Transcripción con Gemini (Perfil ASIX)

## Resumen

Este documento describe la arquitectura de red del endpoint API REST desarrollado con FastAPI que recibe archivos de audio, los envía al modelo **Gemini 3.5 Transcribe** de Google para transcripción y devuelve el texto resultante.

---

## Diagrama de Arquitectura

```
┌─────────────┐     HTTP/REST      ┌──────────────────┐     gRPC/HTTPS     ┌─────────────────────────────┐
│   CLIENTE   │ ◄────────────────► │   FASTAPI SERVER │ ◄─────────────────► │   GOOGLE GEMINI API         │
│             │   Puerto 8000      │   (src/api.py)   │   Puerto 443       │   generativelanguage.goog...│
└─────────────┘                    └──────────────────┘                    └─────────────────────────────┘
        │                                 │                                          │
        │                                 │                                          │
        ▼                                 ▼                                          ▼
   Audio file                      Procesamiento                            Files API (temp)
   (multipart/                     Validación MIME                           Storage 48h max
   form-data)                       Upload inline/<20MB                                                   
                                    Files API >20MB                         Transcription
                                                                     Model: gemini-3.5-transcribe
```

---

## Componentes de Red

### 1. Cliente (Cualquier cliente HTTP)
- **Protocolo**: HTTP/1.1 o HTTP/2
- **Puerto destino**: 8000 (configurable)
- **Métodos**: POST, GET
- **Content-Type**: `multipart/form-data` (subida audio), `application/x-www-form-urlencoded` (URL)
- **Autenticación**: No requerida a nivel de API (la API Key de Gemini se gestiona en servidor)

### 2. Servidor FastAPI (Capa de Aplicación)
- **Framework**: FastAPI 0.109+ sobre Uvicorn (ASGI)
- **Host**: `0.0.0.0` (escucha en todas las interfaces)
- **Puerto**: 8000
- **Workers**: 1 (modo desarrollo con reload), escalable en producción

#### Endpoints disponibles:

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/health` | GET | Health check - verifica API key configurada |
| `/modelos` | GET | Lista modelos de transcripción disponibles |
| `/transcribir` | POST | Transcribe audio subido directamente (multipart) |
| `/transcribir/url` | POST | Transcribe audio desde URL pública (descarga + transcribe) |

#### Flujo de request `/transcribir`:
```
1. Cliente → POST /transcribir (audio + params)
2. FastAPI valida: MIME type, tamaño, parámetros
3. Si audio ≤ 20 MB → envío inline (bytes directos)
4. Si audio > 20 MB → subida a Google Files API (temporal)
5. Llamada a Gemini: models.generate_content()
6. Recepción respuesta JSON con transcripción
7. Limpieza: borra archivo temporal de Files API
8. Respuesta HTTP 200: {texto, modelo, duracion_ms, caracteres}
```

### 3. Comunicación Servidor → Google Gemini API

#### Protocolo y Transporte
- **Protocolo**: HTTPS (TLS 1.2+)
- **Puerto**: 443
- **SDK**: `google-genai` (Python) - usa gRPC/HTTP/JSON internamente
- **Endpoint**: `generativelanguage.googleapis.com`

#### Autenticación
- **Método**: API Key en header `x-goog-api-key`
- **Origen**: Variable de entorno `GEMINI_API_KEY` (cargada desde `.env`)
- **Alcance**: Solo valida acceso al proyecto Google Cloud, no identifica al usuario final

#### Formato de Datos (Request a Gemini)
```json
{
  "model": "gemini-3.5-transcribe",
  "contents": [{
    "parts": [{
      "inline_data": {
        "mime_type": "audio/m4a",
        "data": "<base64_audio_bytes>"
      }
    }]
  }],
  "generation_config": {
    "audio_transcription_config": {
      "language_codes": ["es-ES"],
      "custom_vocabulary": ["Kubernetes", "BigQuery"],
      "word_timestamp": false,
      "diarization": false,
      "mode": "VERBATIM"
    }
  }
}
```

#### Respuesta de Gemini
```json
{
  "text": "Texto transcrito completo...",
  "usage_metadata": {
    "prompt_token_count": 1234,
    "candidates_token_count": 567
  }
}
```

---

## Gestión de Archivos de Audio

### Dos vías según tamaño:

| Tamaño | Método | Detalles |
|--------|--------|----------|
| **≤ 20 MB** | **Inline** | Bytes codificados en base64 dentro del request JSON. Un solo round-trip. |
| **> 20 MB** | **Files API** | 1. POST a `files.googleapis.com` → recibe `file.name`<br>2. Polling `files.get()` hasta `state=ACTIVE` (máx 30 × 2s)<br>3. Referencia `file.name` en `generate_content`<br>4. DELETE `files.delete()` al terminar (limpieza automática) |

### Formatos soportados (MIME types)
```
audio/wav, audio/mp3, audio/m4a, audio/aac, audio/aiff,
audio/ogg, audio/opus, audio/flac, audio/webm, audio/mpeg,
audio/l16, audio/alaw, audio/mulaw
```

### Límites de Gemini
- **Duración máxima**: 9.5 horas por request
- **Tamaño máx. Files API**: 2 GB
- **Retención Files API**: 48 horas (el script borra al acabar)

---

## Seguridad de Red

### Capa de Transporte
- **Cliente ↔ FastAPI**: HTTP plano (desarrollo) / HTTPS recomendado (producción con reverse proxy nginx/traefik + TLS)
- **FastAPI ↔ Gemini**: HTTPS obligatorio (TLS 1.2+)

### Datos Sensibles
| Dato | Dónde viaja | Protección |
|------|-------------|------------|
| Audio del usuario | Cliente → FastAPI → Gemini | HTTPS en ambos tramos |
| API Key Gemini | Solo FastAPI → Gemini (header `x-goog-api-key`) | Nunca expuesta al cliente |
| Transcripción | Gemini → FastAPI → Cliente | HTTPS |

### Consideraciones ASIX
- **No hay autenticación/autorización en la API** (ejercicio académico). En producción: JWT, OAuth2, API Gateway.
- **Rate limiting**: No implementado. Añadir `slowapi` o nginx `limit_req`.
- **Logging**: Solo stdout Uvicorn. En producción: structured logging (JSON), ELK/Loki.
- **CORS**: No configurado. Añadir `CORSMiddleware` si frontend en otro origen.

---

## Despliegue en Producción (Recomendaciones ASIX)

```yaml
# docker-compose.yml ejemplo
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 512M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - api
```

### Nginx Reverse Proxy (TLS Termination + Rate Limit)
```nginx
# nginx.conf
http {
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    
    server {
        listen 443 ssl http2;
        ssl_certificate /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;
        
        location / {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://api:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            client_max_body_size 50M;  # Para audios grandes
        }
    }
}
```

---

## Pruebas de Conectividad

### Health Check
```bash
curl http://localhost:8000/health
# {"status":"ok","api_key":"configurada"}
```

### Listar Modelos
```bash
curl http://localhost:8000/modelos
# [{"nombre":"gemini-3.5-transcribe","descripcion":null}]
```

### Transcribir Audio (multipart)
```bash
curl -X POST http://localhost:8000/transcribir \
  -F "audio=@audios/audio1.wav" \
  -F "idioma=es-ES" \
  -F "vocab=Kubernetes,BigQuery" \
  -F "timestamps=true"
```

### Transcribir desde URL
```bash
curl -X POST http://localhost:8000/transcribir/url \
  -F "url=https://ejemplo.com/audio.mp3" \
  -F "idioma=auto"
```

---

## Métricas de Red (Observabilidad)

### Latencias típicas (estimadas)
| Operación | Latencia aprox. |
|-----------|-----------------|
| Health check | < 5 ms |
| Upload inline (5 MB) | 200-500 ms |
| Upload Files API (50 MB) | 2-5 s (subida) + 10-30 s (procesamiento) |
| Transcripción Gemini (1 min audio) | 3-8 s |
| Transcripción Gemini (10 min audio) | 15-40 s |
| **Total end-to-end (1 min)** | **4-10 s** |

### Puntos de fallo de red
1. **Cliente → FastAPI**: Timeout 60s (configurar en reverse proxy)
2. **FastAPI → Files API**: Timeout 60s subida, polling 60s max
3. **FastAPI → Gemini generate_content**: Timeout 120s (audio largo)
4. **DNS**: `generativelanguage.googleapis.com` debe resolver

---

## Troubleshooting Común

| Error | Causa | Solución |
|-------|-------|----------|
| `503 api_key no configurada` | Falta `.env` o `GEMINI_API_KEY` | Copiar `.env.example` → `.env` y poner clave |
| `403 PERMISSION_DENIED` | API key inválida/sin billing | Verificar clave en aistudio.google.com, habilitar facturación |
| `413 Request Entity Too Large` | Audio > límite nginx/client_max_body_size | Aumentar `client_max_body_size` en nginx |
| `504 Gateway Timeout` | Transcripción muy larga | Aumentar timeouts proxy, usar `/transcribir/url` para archivos grandes |
| `400 Formato no soportado` | Extensión no en `MIME_POR_EXTENSION` | Añadir MIME type en `config.py` o convertir audio |

---

## Resumen para Entrega ASIX

✅ **Endpoint API REST funcional** (FastAPI)  
✅ **Recepción audio multipart/form-data**  
✅ **Integración Gemini (google-genai SDK)**  
✅ **Soporte archivos >20 MB vía Files API**  
✅ **Parámetros: modelo, idioma, vocabulario, timestamps, diarización**  
✅ **Documentación arquitectura de red (este fichero)**  
✅ **Health check y listado modelos**  
✅ **Limpieza automática recursos temporales**  

**Para probar**: 
1. Editar `.env` con API key válida de Gemini
2. Ejecutar: `py -3 -m src.api`
3. Probar endpoints con `curl` o Postman