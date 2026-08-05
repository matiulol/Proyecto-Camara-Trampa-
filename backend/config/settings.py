from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    PROJECT_NAME: str = "Camara Trampa"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = (
        "API inicial para un sistema de monitoreo con camaras trampa."
    )


settings = Settings()
