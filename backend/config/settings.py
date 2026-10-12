# dataclass permite definir una configuración simple e inmutable para el backend.
from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv


# El backend se ejecuta desde esta carpeta; cargar este archivo evita depender
# del directorio desde el que se invocó Uvicorn.
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_FILE)


def _obtener_entero(nombre: str, predeterminado: int) -> int:
    """Obtiene un entero de entorno sin dejar errores de configuración ambiguos."""
    valor = os.getenv(nombre, str(predeterminado))
    try:
        return int(valor)
    except ValueError as exc:
        raise RuntimeError(f"{nombre} debe ser un número entero.") from exc


@dataclass(frozen=True)
class Settings:
    # Configuración centralizada del backend. Los secretos solo se leen del
    # entorno o de backend/.env, que no se versiona.
    PROJECT_NAME: str = "Camara Trampa Inteligente"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = (
        "API para login, camaras, peticiones y eventos de una reserva natural."
    )
    API_V1_PREFIX: str = "/api/v1"
    # Si no existe .env, se conserva MongoDB local como respaldo de desarrollo.
    # Para Atlas, MONGODB_URI debe ser una URI mongodb+srv:// completa.
    MONGODB_URI: str = field(
        default_factory=lambda: os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    )
    # No se permite cambiar accidentalmente la base histórica del proyecto.
    MONGODB_DATABASE: str = field(
        default_factory=lambda: os.getenv("MONGODB_DATABASE", "Ani_cam")
    )
    MONGODB_TIMEOUT_MS: int = field(
        default_factory=lambda: _obtener_entero("MONGODB_TIMEOUT_MS", 5000)
    )

    def __post_init__(self) -> None:
        if not self.MONGODB_URI.strip():
            raise RuntimeError("MONGODB_URI no puede estar vacía.")
        if self.MONGODB_DATABASE != "Ani_cam":
            raise RuntimeError("MONGODB_DATABASE debe ser Ani_cam.")
        if self.MONGODB_TIMEOUT_MS <= 0:
            raise RuntimeError("MONGODB_TIMEOUT_MS debe ser mayor que cero.")


# Instancia única importada por el resto del backend.
settings = Settings()
