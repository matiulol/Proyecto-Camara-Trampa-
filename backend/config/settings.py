from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    PROJECT_NAME: str = "Camara Trampa Inteligente"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = (
        "API inicial para login, camaras y eventos de una reserva natural."
    )
    API_V1_PREFIX: str = "/api/v1"
    MONGODB_URI: str = "mongodb://localhost:27017/Ani_cam"
    MONGODB_DATABASE: str = "Ani_cam"
    MONGODB_TIMEOUT_MS: int = 5000


settings = Settings()
