"""Carga y valida la configuración del servidor y de sus servicios externos.

Los valores se leen del entorno y de ``backend/.env`` cuando existe; las
restricciones de MongoDB mantienen el uso de la base local ``Ani_cam``.
"""

# dataclass permite definir una configuración simple e inmutable para el servidor.
from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv


# El servidor se ejecuta desde esta carpeta; cargar este archivo evita depender
# del directorio desde el que se invocó Uvicorn.
ARCHIVO_ENTORNO = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ARCHIVO_ENTORNO)


def _obtener_entero(nombre: str, predeterminado: int) -> int:
    """Obtiene un entero de entorno sin dejar errores de configuración ambiguos."""
    valor = os.getenv(nombre, str(predeterminado))
    try:
        return int(valor)
    except ValueError as excepcion:
        raise RuntimeError(f"{nombre} debe ser un número entero.") from excepcion


@dataclass(frozen=True)
class Configuracion:
    """Valores inmutables que comparten FastAPI, MongoDB y Backblaze B2.

    Los valores de B2 permanecen vacíos si no se configuraron y se validan al
    usarse; la conexión de MongoDB, en cambio, debe respetar la instalación
    local que utiliza esta versión del proyecto.
    """
    # Configuración centralizada del servidor. Los secretos solo se leen del
    # entorno o de backend/.env, que no se versiona.
    NOMBRE_PROYECTO: str = "Camara Trampa Inteligente"
    VERSION_PROYECTO: str = "1.0.0"
    DESCRIPCION: str = (
        "API para inicio de sesión, camaras, peticiones y eventos de una reserva natural."
    )
    PREFIJO_API_V1: str = "/api/v1"
    # ANICAM utiliza exclusivamente MongoDB local. La validación posterior evita
    # que una variable de entorno heredada conecte accidentalmente a Atlas.
    URI_MONGODB: str = field(
        default_factory=lambda: os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    )
    # No se permite cambiar accidentalmente la base histórica del proyecto.
    BASE_DATOS_MONGODB: str = field(
        default_factory=lambda: os.getenv("MONGODB_DATABASE", "Ani_cam")
    )
    TIEMPO_ESPERA_MONGODB_MS: int = field(
        default_factory=lambda: _obtener_entero("MONGODB_TIMEOUT_MS", 5000)
    )
    # B2 es opcional al arrancar: las credenciales se validan recién cuando una
    # captura necesita la nube, de modo que una Raspberry pueda informar un error
    # claro sin exponer secretos ni impedir diagnosticar FastAPI.
    DIRECCION_SERVICIO_B2: str = field(default_factory=lambda: os.getenv("B2_DIRECCION_SERVICIO", ""))
    NOMBRE_DEPOSITO_B2: str = field(default_factory=lambda: os.getenv("B2_NOMBRE_DEPOSITO", ""))
    REGION_B2: str = field(default_factory=lambda: os.getenv("B2_REGION", ""))
    IDENTIFICADOR_CLAVE_B2: str = field(default_factory=lambda: os.getenv("B2_IDENTIFICADOR_CLAVE", ""))
    CLAVE_SECRETA_B2: str = field(default_factory=lambda: os.getenv("B2_CLAVE_SECRETA", ""))

    def __post_init__(self) -> None:
        """Rechaza valores que contradicen la base local configurada para ANICAM."""
        if self.URI_MONGODB.rstrip("/") != "mongodb://localhost:27017":
            raise RuntimeError(
                "MONGODB_URI debe apuntar a mongodb://localhost:27017 para usar "
                "la instancia local de ANICAM."
            )
        if self.BASE_DATOS_MONGODB != "Ani_cam":
            raise RuntimeError("MONGODB_DATABASE debe ser Ani_cam.")
        if self.TIEMPO_ESPERA_MONGODB_MS <= 0:
            raise RuntimeError("MONGODB_TIMEOUT_MS debe ser mayor que cero.")

    def b2_configurado(self) -> bool:
        """Indica si B2 tiene completos sus cinco parámetros requeridos.

        Sólo devuelve un booleano: nunca expone ni registra las credenciales.
        """
        return all((self.DIRECCION_SERVICIO_B2, self.NOMBRE_DEPOSITO_B2, self.REGION_B2,
                    self.IDENTIFICADOR_CLAVE_B2, self.CLAVE_SECRETA_B2))


# Instancia única importada por el resto del servidor.
configuracion = Configuracion()
