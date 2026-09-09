from fastapi import APIRouter

from config.settings import settings
from database.connection import comprobar_conexion
from services.project_service import get_project_info


router = APIRouter()


@router.get("/")
def read_root():
    return {"message": "Backend iniciado correctamente"}


@router.get("/health")
def health_check():
    comprobar_conexion()
    return {"status": "ok"}


@router.get("/info")
def project_info():
    info = get_project_info()
    info["mongodb"] = {
        "base_de_datos": settings.MONGODB_DATABASE,
        "conexion": settings.MONGODB_URI,
    }
    return info
