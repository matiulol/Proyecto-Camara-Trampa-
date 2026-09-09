from contextlib import asynccontextmanager

from fastapi import FastAPI

from config.settings import settings
from database.connection import cerrar_conexion, comprobar_conexion
from routers.autenticacion import router as autenticacion_router
from routers.basic import router as basic_router
from routers.camaras import router as camaras_router
from routers.eventos import router as eventos_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    comprobar_conexion()
    try:
        yield
    finally:
        cerrar_conexion()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    lifespan=lifespan,
)

app.include_router(basic_router)
app.include_router(autenticacion_router, prefix=settings.API_V1_PREFIX)
app.include_router(camaras_router, prefix=settings.API_V1_PREFIX)
app.include_router(eventos_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
