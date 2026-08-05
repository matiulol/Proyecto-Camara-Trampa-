from fastapi import APIRouter

from services.project_service import get_project_info


router = APIRouter()


@router.get("/")
def read_root():
    return {"message": "Backend iniciado correctamente"}


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/info")
def project_info():
    return get_project_info()
