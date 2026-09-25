# Cámara Trampa - Proyecto Inicio

Versión actual del sistema de cámara trampa inteligente.

## Objetivo

Esta etapa implementa:

- Backend con FastAPI.
- Conexión con MongoDB usando la base existente Ani_cam.
- Login básico sin JWT y sin hashing.
- Gestión básica de cámaras.
- Gestión de peticiones de foto/video.
- Consulta de eventos existentes en modo solo lectura.
- Aplicación de escritorio PySide6 con login y dashboard.

## MongoDB

Base de datos obligatoria:

```text
Ani_cam
```

Conexión:

```text
mongodb://localhost:27017/Ani_cam
```

Colecciones usadas:

- `usuarios`
- `camaras`
- `eventos`
- `archivos`
- `peticiones`

## Peticiones

La colección `peticiones` guarda solicitudes hechas desde el dashboard hacia una cámara.

Estructura básica:

```json
{
  "_id": "ObjectId generado por MongoDB",
  "camara_id": "camara001",
  "tipo": "foto",
  "estado": "pendiente",
  "fecha_hora": "2026-09-20 18:30:00"
}
```

Tipos permitidos:

- `foto`
- `video`

Estados permitidos:

- `pendiente`
- `ejecutado`
- `error`

## Eventos

La colección `eventos` se mantiene, pero el dashboard y la API la usan como historial visual de solo lectura.

No se crean eventos automáticamente al crear peticiones.

## Ejecutar backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Endpoints principales:

- `POST /api/v1/autenticacion/iniciar-sesion`
- `GET /api/v1/camaras`
- `POST /api/v1/camaras`
- `GET /api/v1/camaras/{camara_id}`
- `PUT /api/v1/camaras/{camara_id}`
- `DELETE /api/v1/camaras/{camara_id}`
- `POST /api/v1/peticiones`
- `GET /api/v1/peticiones`
- `GET /api/v1/peticiones/{peticion_id}`
- `PUT /api/v1/peticiones/{peticion_id}`
- `GET /api/v1/eventos`
- `GET /api/v1/eventos/{evento_id}`

## Ejecutar aplicación desktop

Con el backend iniciado:

```bash
cd desktop_app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Credenciales de prueba:

```text
usuario: admin
contraseña: admin123
```

## Dashboard

El dashboard tiene tres pestañas:

- Cámaras
- Peticiones
- Eventos

Peticiones permite seleccionar una cámara, solicitar foto, solicitar video, consultar el historial y ver estados.

Eventos solamente permite consultar y actualizar la tabla de eventos existentes.

## Funcionalidades no incluidas todavía

No se implementan todavía Raspberry Pi, comunicación remota, polling de peticiones, JWT, hashing, uploads, almacenamiento cloud, IA ni captura real de imágenes/videos.
