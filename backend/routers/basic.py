"""Rutas generales para identificar y comprobar el estado del backend."""

# APIRouter reúne rutas que no pertenecen a una colección específica de Ani_cam.
from fastapi import APIRouter

# settings aporta el nombre y la conexión configurada de la aplicación.
from config.settings import settings
# comprobar_conexion ejecuta un ping sin modificar datos de MongoDB.
from database.connection import comprobar_conexion
# El servicio evita repetir los datos generales del proyecto en esta ruta.
from services.project_service import get_project_info


# No se define prefijo aquí porque main.py deja estas rutas en la raíz de la API.
router = APIRouter()


@router.get("/")
def read_root():
    # GET / permite saber rápidamente que el proceso de FastAPI inició. No consulta
    # MongoDB, por lo que es una comprobación de proceso y no de base de datos.
    return {"message": "Backend iniciado correctamente"}


@router.get("/health")
def health_check():
    # GET /health comprueba el backend y MongoDB a la vez. Si ping falla, la
    # excepción permite detectar que Ani_cam no está lista para peticiones.
    comprobar_conexion()
    return {"status": "ok"}


@router.get("/info")
def project_info():
    # GET /info devuelve datos descriptivos usados para diagnosticar la instalación.
    # La configuración se lee desde settings para reflejar el entorno realmente activo.
    info = get_project_info()
    info["mongodb"] = {
        "base_de_datos": settings.MONGODB_DATABASE,
        "conexion": settings.MONGODB_URI,
    }
    return info
