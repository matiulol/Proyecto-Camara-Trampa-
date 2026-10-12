# asynccontextmanager permite definir qué ocurre al iniciar y cerrar la API.
from contextlib import asynccontextmanager

# FastAPI es la clase principal del framework usada para construir la aplicación.
from fastapi import FastAPI

# settings concentra nombre del proyecto, prefijo de API y configuración MongoDB.
from config.settings import settings
# Estas funciones manejan la comprobación y cierre de la conexión con MongoDB.
from database.connection import cerrar_conexion, comprobar_conexion
# Cada router agrupa endpoints de una parte concreta del sistema.
from routers.autenticacion import router as autenticacion_router
from routers.archivos import router as archivos_router
from routers.basic import router as basic_router
from routers.camaras import router as camaras_router
from routers.eventos import router as eventos_router
from routers.peticiones import router as peticiones_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Controla recursos compartidos durante el inicio y cierre de FastAPI."""
    # Al iniciar FastAPI se comprueba que MongoDB responda. Si Ani_cam no está
    # disponible, el error aparece al arrancar y no durante una acción del usuario.
    comprobar_conexion()
    try:
        yield
    finally:
        # Cierra el cliente de MongoDB cuando se detiene la API para liberar
        # recursos del proceso local de desarrollo.
        cerrar_conexion()


# Configuración principal de la API. El nombre, versión y descripción viven en
# settings para que el proyecto tenga un único lugar de configuración.
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    lifespan=lifespan,
)

# Los routers se registran bajo /api/v1 cuando corresponden a funcionalidades
# del MVP. Las rutas básicas quedan fuera para salud e información general.
app.include_router(basic_router)
app.include_router(autenticacion_router, prefix=settings.API_V1_PREFIX)
app.include_router(archivos_router, prefix=settings.API_V1_PREFIX)
app.include_router(camaras_router, prefix=settings.API_V1_PREFIX)
app.include_router(peticiones_router, prefix=settings.API_V1_PREFIX)
app.include_router(eventos_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    # Conserva el mismo host y puerto documentados para la ejecución en red. Así
    # ``python main.py`` no contradice el comando Uvicorn que necesita la Raspberry.
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
