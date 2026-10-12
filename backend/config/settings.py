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
    # ANICAM utiliza exclusivamente MongoDB local. La validación posterior evita
    # que una variable de entorno heredada conecte accidentalmente a Atlas.
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
    # B2 es opcional al arrancar: las credenciales se validan recién cuando una
    # captura necesita la nube, de modo que una Raspberry pueda informar un error
    # claro sin exponer secretos ni impedir diagnosticar FastAPI.
    B2_DIRECCION_SERVICIO: str = field(default_factory=lambda: os.getenv("B2_DIRECCION_SERVICIO", ""))
    B2_NOMBRE_DEPOSITO: str = field(default_factory=lambda: os.getenv("B2_NOMBRE_DEPOSITO", ""))
    B2_REGION: str = field(default_factory=lambda: os.getenv("B2_REGION", ""))
    B2_IDENTIFICADOR_CLAVE: str = field(default_factory=lambda: os.getenv("B2_IDENTIFICADOR_CLAVE", ""))
    B2_CLAVE_SECRETA: str = field(default_factory=lambda: os.getenv("B2_CLAVE_SECRETA", ""))

    def __post_init__(self) -> None:
        if self.MONGODB_URI.rstrip("/") != "mongodb://localhost:27017":
            raise RuntimeError(
                "MONGODB_URI debe apuntar a mongodb://localhost:27017 para usar "
                "la instancia local de ANICAM."
            )
        if self.MONGODB_DATABASE != "Ani_cam":
            raise RuntimeError("MONGODB_DATABASE debe ser Ani_cam.")
        if self.MONGODB_TIMEOUT_MS <= 0:
            raise RuntimeError("MONGODB_TIMEOUT_MS debe ser mayor que cero.")

    def b2_configurado(self) -> bool:
        """Indica si están todos los valores necesarios sin revelar ninguno."""
        return all((self.B2_DIRECCION_SERVICIO, self.B2_NOMBRE_DEPOSITO, self.B2_REGION,
                    self.B2_IDENTIFICADOR_CLAVE, self.B2_CLAVE_SECRETA))


# Instancia única importada por el resto del backend.
settings = Settings()
