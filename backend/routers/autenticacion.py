"""Endpoints de inicio de sesión contra la colección usuarios."""

# APIRouter registra rutas; Depends entrega MongoDB; HTTPException y status
# permiten responder un 401 claro cuando las credenciales no son correctas.
from fastapi import APIRouter, Depends, HTTPException, status
# Database describe la instancia Ani_cam que inyecta la dependencia del backend.
from pymongo.database import Database

# get_database evita que este router cree conexiones propias a MongoDB.
from database.connection import get_database
# serializar_documento transforma el ObjectId del usuario antes de responder JSON.
from database.object_id import serializar_documento
# Estos esquemas validan los datos recibidos y limitan los datos devueltos.
from models.schemas import InicioSesion, InicioSesionRespuesta


# Agrupa las rutas bajo /api/v1/autenticacion cuando main.py registra el router.
router = APIRouter(prefix="/autenticacion", tags=["autenticacion"])


@router.post("/iniciar-sesion", response_model=InicioSesionRespuesta)
def iniciar_sesion(
    credenciales: InicioSesion,
    db: Database = Depends(get_database),
) -> dict:
    # POST /iniciar-sesion lo consume el Dashboard antes de mostrar sus pestañas.
    # Busca una coincidencia exacta en Ani_cam.usuarios usando el modelo Pydantic,
    # que ya validó que usuario y contraseña no lleguen vacíos.
    usuario = db.usuarios.find_one(
        {
            "usuario": credenciales.usuario,
            "contraseña": credenciales.contrasena,
        }
    )
    if usuario is None:
        # No se revela cuál de los dos datos falló para no exponer información
        # adicional sobre las cuentas guardadas en la colección usuarios.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )

    # Convierte _id a texto y elimina la contraseña antes de construir la respuesta.
    # El Dashboard solo necesita identificar al usuario y conocer su rol.
    usuario_publico = serializar_documento(usuario)
    usuario_publico.pop("contraseña", None)
    return {
        "mensaje": "Inicio de sesion exitoso.",
        "usuario": usuario_publico,
    }
