"""Rutas generales para identificar y comprobar el estado del backend."""

# APIRouter reúne rutas que no pertenecen a una colección específica de Ani_cam.
from fastapi import APIRouter

# settings aporta el nombre y la conexión configurada de la aplicación.
from config.settings import settings
# comprobar_conexion ejecuta un ping sin modificar datos de MongoDB.
from database.connection import comprobar_conexion
# El servicio evita repetir los datos generales del proyecto en esta ruta.
from services.servicio_proyecto import obtener_informacion_proyecto


# No se define prefijo aquí porque main.py deja estas rutas en la raíz de la API.
router = APIRouter()


@router.get("/")
def read_root():
    """Responde un GET de proceso sin consultar la base de datos."""
    # GET / permite saber rápidamente que el proceso de FastAPI inició. No consulta
    # MongoDB, por lo que es una comprobación de proceso y no de base de datos.
    return {"message": "Backend iniciado correctamente"}


@router.get("/health")
def health_check():
    """Responde un GET de salud que comprueba la disponibilidad de MongoDB."""
    # GET /health comprueba el backend y MongoDB a la vez. Si ping falla, la
    # excepción permite detectar que Ani_cam no está lista para peticiones.
    comprobar_conexion()
    return {"status": "ok"}


@router.get("/info")
def project_info():
    """Expone información diagnóstica de la instalación actual."""
    # GET /info devuelve datos descriptivos usados para diagnosticar la instalación.
    # La configuración se lee desde settings para reflejar el entorno realmente activo.
    info = obtener_informacion_proyecto()
    info["mongodb"] = {
        "base_de_datos": settings.MONGODB_DATABASE,
        "conexion": settings.MONGODB_URI,
    }
    return info
