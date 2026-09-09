# Camara Trampa - Proyecto Inicio

Version de etapa 1 del sistema de camara trampa inteligente.

## Objetivo

Esta etapa implementa:

- Backend con FastAPI.
- Conexion con MongoDB usando la base existente Ani_cam.
- Login basico sin JWT y sin hashing.
- Gestion basica de camaras.
- Gestion basica de eventos.
- Aplicacion de escritorio PySide6 con login y dashboard.

## MongoDB

Base de datos obligatoria:

```text
Ani_cam
```

Conexion:

```text
mongodb://localhost:27017/Ani_cam
```

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
- `GET /api/v1/eventos`
- `POST /api/v1/eventos`
- `GET /api/v1/eventos/{evento_id}`

## Ejecutar aplicacion desktop

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

## Documentacion

La documentacion detallada de esta etapa esta en:

```text
docs/DOCUMENTACION_ETAPA_1.txt
```

## Funcionalidades no incluidas todavia

No se implementan todavia Raspberry Pi, requests/comandos remotos, JWT, hashing,
uploads, almacenamiento cloud, IA ni captura real de imagenes/videos.
