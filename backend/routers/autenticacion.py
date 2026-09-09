from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from database.connection import get_database
from database.object_id import serializar_documento
from models.schemas import InicioSesion, InicioSesionRespuesta


router = APIRouter(prefix="/autenticacion", tags=["autenticacion"])


@router.post("/iniciar-sesion", response_model=InicioSesionRespuesta)
def iniciar_sesion(
    credenciales: InicioSesion,
    db: Database = Depends(get_database),
) -> dict:
    usuario = db.usuarios.find_one(
        {
            "usuario": credenciales.usuario,
            "contraseña": credenciales.contrasena,
        }
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )

    usuario_publico = serializar_documento(usuario)
    usuario_publico.pop("contraseña", None)
    return {
        "mensaje": "Inicio de sesion exitoso.",
        "usuario": usuario_publico,
    }
