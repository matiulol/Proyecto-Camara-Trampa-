"""Configuración editable de la Raspberry sin direcciones fijas en el código."""

import os

# Estas variables permiten usar la misma aplicación en cada Raspberry. En la
# Raspberry real se define BACKEND_URL con la IP de la computadora que ejecuta FastAPI.
CAMARA_ID = os.getenv("CAMARA_ID", "camara001")
URL_BACKEND = os.getenv("URL_BACKEND", "http://127.0.0.1:8000/api/v1")
INTERVALO_CONSULTA_MS = int(os.getenv("INTERVALO_CONSULTA_MS", "5000"))
DURACION_VIDEO_SEGUNDOS = int(os.getenv("DURACION_VIDEO_SEGUNDOS", "10"))
PHOTO_SIZE = (1920, 1080)
VIDEO_BITRATE = 10_000_000
