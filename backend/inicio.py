"""Configura la aplicación FastAPI y conecta sus rutas con los servicios locales.

Este módulo registra las rutas HTTP generales y los enrutadores de ANICAM. Su ciclo
de vida comprueba MongoDB y prepara los índices de consulta antes de aceptar
tráfico, y cierra el cliente compartido cuando el servidor termina.
"""

# asynccontextmanager permite definir qué ocurre al iniciar y cerrar la API.
from contextlib import asynccontextmanager

# FastAPI es la clase principal del framework usada para construir la aplicación.
from fastapi import FastAPI

# configuración concentra nombre del proyecto, prefijo de API y configuración MongoDB.
from configuracion.ajustes import configuracion
# Estas funciones manejan la comprobación y cierre de la conexión con MongoDB.
from base_datos.conexion import cerrar_conexion, comprobar_conexion, preparar_indices
# Cada enrutador agrupa rutas HTTP de una parte concreta del sistema.
from rutas.autenticacion import enrutador as enrutador_autenticacion
from rutas.archivos import enrutador as enrutador_archivos
from rutas.generales import enrutador as enrutador_general
from rutas.camaras import enrutador as enrutador_camaras
from rutas.eventos import enrutador as enrutador_eventos
from rutas.peticiones import enrutador as enrutador_peticiones


@asynccontextmanager
async def ciclo_vida(aplicacion: FastAPI):
    """Prepara y libera los recursos compartidos por la aplicación.

    Comprueba MongoDB y asegura los índices antes de atender solicitudes. El
    bloque ``finally`` cierra la conexión incluso si FastAPI se detiene por un
    error durante su ciclo de vida.
    """
    # Al iniciar FastAPI se comprueba que MongoDB responda. Si Ani_cam no está
    # disponible, el error aparece al arrancar y no durante una acción del usuario.
    comprobar_conexion()
    # Los índices se crean de forma idempotente y no cambian documentos ni
    # colecciones históricas. Si faltan permisos, el helper deja una advertencia
    # y la API conserva su funcionamiento normal.
    preparar_indices()
    try:
        yield
    finally:
        # Cierra el cliente de MongoDB cuando se detiene la API para liberar
        # recursos del proceso local de desarrollo.
        cerrar_conexion()


# Configuración principal de la API. El nombre, versión y descripción viven en
# configuración para que el proyecto tenga un único lugar de configuración.
app = FastAPI(
    title=configuracion.NOMBRE_PROYECTO,
    version=configuracion.VERSION_PROYECTO,
    description=configuracion.DESCRIPCION,
    lifespan=ciclo_vida,
)

# Los enrutadores se registran bajo /api/v1 cuando corresponden a funcionalidades
# del MVP. Las rutas básicas quedan fuera para salud e información general.
app.include_router(enrutador_general)
app.include_router(enrutador_autenticacion, prefix=configuracion.PREFIJO_API_V1)
app.include_router(enrutador_archivos, prefix=configuracion.PREFIJO_API_V1)
app.include_router(enrutador_camaras, prefix=configuracion.PREFIJO_API_V1)
app.include_router(enrutador_peticiones, prefix=configuracion.PREFIJO_API_V1)
app.include_router(enrutador_eventos, prefix=configuracion.PREFIJO_API_V1)


if __name__ == "__main__":
    # Conserva el mismo host y puerto documentados para la ejecución en red. Así
    # ``python inicio.py`` no contradice el comando Uvicorn que necesita la Raspberry.
    import uvicorn

    uvicorn.run("inicio:app", host="0.0.0.0", port=8000, reload=True)
