"""Parámetros de conexión del Dashboard, sin credenciales ni datos de MongoDB."""

import os


# Permite ejecutar el Dashboard desde otra PC de la red sin editar el código.
# Si no se define, conserva la instalación local de desarrollo existente.
API_BASE_URL = os.getenv("ANICAM_API_BASE_URL", "http://127.0.0.1:8000/api/v1")
