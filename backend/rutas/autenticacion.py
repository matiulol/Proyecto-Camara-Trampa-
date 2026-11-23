"""Rutas HTTP de inicio de sesión contra la colección usuarios."""

# APIRouter registra rutas; Depends entrega MongoDB; HTTPException y status
# permiten responder un 401 claro cuando las credenciales no son correctas.
from fastapi import APIRouter, Depends, HTTPException, status
# Base de datos describe la instancia Ani_cam que inyecta la dependencia del servidor.
from pymongo.database import Database

# obtener_base_datos evita que este enrutador cree conexiones propias a MongoDB.
from base_datos.conexion import obtener_base_datos
# serializar_documento transforma el ObjectId del usuario antes de responder JSON.
from base_datos.identificador_objeto import serializar_documento
# Estos esquemas validan los datos recibidos y limitan los datos devueltos.
from modelos.esquemas import InicioSesion, InicioSesionRespuesta


# El prefijo de ruta se conserva sin acento por compatibilidad HTTP. La etiqueta
# solo organiza la documentación automática de OpenAPI.
enrutador = APIRouter(prefix="/autenticacion", tags=["autenticación"])


@enrutador.post("/iniciar-sesion", response_model=InicioSesionRespuesta)
def iniciar_sesion(
    credenciales: InicioSesion,
    base_datos_personalizada: Database = Depends(obtener_base_datos),
) -> dict:
    """Valida las credenciales existentes y devuelve sólo datos públicos.

    La consulta coincide exactamente con usuario y contraseña en ``usuarios``;
    las credenciales inválidas producen HTTP 401 sin indicar cuál falló.
    """
    # POST /iniciar-sesion lo consume el Panel de control antes de mostrar sus pestañas.
    # Busca una coincidencia exacta en Ani_cam.usuarios usando el modelo Pydantic,
    # que ya validó que usuario y contraseña no lleguen vacíos.
    usuario = base_datos_personalizada.usuarios.find_one(
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
    # El Panel de control solo necesita identificar al usuario y conocer su rol.
    usuario_publico = serializar_documento(usuario)
    usuario_publico.pop("contraseña", None)
    return {
        "mensaje": "Inicio de sesion exitoso.",
        "usuario": usuario_publico,
    }
