# Camara Trampa - Proyecto Inicio

Version inicial del sistema de camara trampa.

Esta carpeta es una copia independiente y simplificada del proyecto principal.

## Objetivo

El proyecto busca organizar desde el inicio 2 partes principales:

- Backend con FastAPI.
- Aplicacion de escritorio con PySide6.


En esta version solo se comprueba que la arquitectura existe y que los componentes principales pueden ejecutarse.

## Estructura

```text
proyecto-inicio/
├── backend/
├── desktop_app/
```

## Ejecutar backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Endpoints disponibles:

- `GET /`
- `GET /health`
- `GET /info`

## Ejecutar aplicacion desktop

Con el backend iniciado:

```bash
cd desktop_app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```


## Funcionalidades no incluidas todavia

Esta primera version no implementa login, usuarios, camaras, eventos, roles, base de datos, sincronizacion ni captura de imagenes.
Esas partes quedan planificadas para futuras entregas.
