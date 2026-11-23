"""Rutas generales para identificar y comprobar el estado del servidor."""

# APIRouter reúne rutas que no pertenecen a una colección específica de Ani_cam.
from fastapi import APIRouter

# configuración aporta el nombre y la base configurada de la aplicación.
from configuracion.ajustes import configuracion
# comprobar_conexion ejecuta un ping sin modificar datos de MongoDB.
from base_datos.conexion import comprobar_conexion
# El servicio evita repetir los datos generales del proyecto en esta ruta.
from servicios.servicio_proyecto import obtener_informacion_proyecto


# No se define prefijo aquí porque inicio.py deja estas rutas en la raíz de la API.
enrutador = APIRouter()


@enrutador.get("/")
def leer_raiz():
    """Responde un GET de proceso sin consultar la base de datos."""
    # GET / permite saber rápidamente que el proceso de FastAPI inició. No consulta
    # MongoDB, por lo que es una comprobación de proceso y no de base de datos.
    return {"message": "Servidor iniciado correctamente"}


@enrutador.get("/health")
def comprobar_estado():
    """Responde un GET de salud que comprueba la disponibilidad de MongoDB."""
    # GET /health comprueba el servidor y MongoDB a la vez. Si ping falla, la
    # excepción permite detectar que Ani_cam no está lista para peticiones.
    comprobar_conexion()
    return {"status": "ok"}


@enrutador.get("/info")
def informacion_proyecto():
    """Expone información diagnóstica de la instalación actual."""
    # GET /info devuelve datos descriptivos sin exponer la URI ni credenciales.
    informacion = obtener_informacion_proyecto()
    informacion["mongodb"] = {
        "base_de_datos": configuracion.BASE_DATOS_MONGODB,
        "configurada": True,
    }
    return informacion
