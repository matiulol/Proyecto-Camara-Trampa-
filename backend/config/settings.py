# dataclass permite definir una configuración simple e inmutable para el backend.
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Configuración centralizada del backend. Se mantiene simple porque el MVP
    # usa una sola base local y no necesita perfiles de entorno todavía.
    PROJECT_NAME: str = "Camara Trampa Inteligente"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = (
        "API inicial para login, camaras, peticiones y eventos de una reserva natural."
    )
    API_V1_PREFIX: str = "/api/v1"
    # La base de datos del proyecto es Ani_cam.
    MONGODB_URI: str = "mongodb://localhost:27017/Ani_cam"
    MONGODB_DATABASE: str = "Ani_cam"
    MONGODB_TIMEOUT_MS: int = 5000


# Instancia única importada por el resto del backend.
settings = Settings()
