# Literal permite limitar campos a valores exactos, por ejemplo los tipos
# de petición aceptados por el MVP: "foto" o "video".
from typing import Literal

# BaseModel y Field son la base de los esquemas de entrada/salida de FastAPI.
# Los validadores se usan para limpiar texto antes de que llegue a MongoDB.
from pydantic import BaseModel, ConfigDict, Field, field_validator


def texto_requerido(valor: str | None) -> str | None:
    # Centraliza la validación de textos para evitar repetir la misma lógica
    # en cámaras, eventos, autenticación y peticiones.
    if valor is None:
        return valor
    valor_limpio = valor.strip()
    if not valor_limpio:
        raise ValueError("El campo no puede estar vacio.")
    return valor_limpio


class InicioSesion(BaseModel):
    # Modelo usado por el endpoint de login. El campo interno se llama
    # "contrasena" para que Python sea simple de escribir, pero el alias
    # mantiene el nombre real en español usado por MongoDB y el dashboard.
    usuario: str
    contrasena: str = Field(alias="contraseña")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("usuario", "contrasena")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return texto_requerido(valor) or ""


class UsuarioPublico(BaseModel):
    # Representa los datos de usuario que se devuelven al dashboard.
    # La contraseña nunca se incluye en este modelo de respuesta.
    id: str = Field(alias="_id")
    usuario: str
    rol: str

    model_config = ConfigDict(populate_by_name=True)


class InicioSesionRespuesta(BaseModel):
    # Respuesta completa del login: un mensaje legible y los datos públicos
    # del usuario autenticado.
    mensaje: str
    usuario: UsuarioPublico


class CamaraBase(BaseModel):
    # Campos compartidos por creación, modificación y respuesta de cámaras.
    # El ID no va aquí porque en MongoDB se guarda como _id manual tipo camara001.
    nombre: str
    ubicacion: str
    estado: str
    fecha_instalacion: str

    @field_validator("nombre", "ubicacion", "estado", "fecha_instalacion")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return texto_requerido(valor) or ""


class CamaraCrear(CamaraBase):
    # La cámara usa un _id manual en español, por ejemplo camara001.
    # No se usa ObjectId para cámaras porque así está definida la base existente.
    id: str = Field(alias="_id", pattern=r"^camara\d{3,}$")

    model_config = ConfigDict(populate_by_name=True)


class CamaraActualizar(BaseModel):
    # Todos los campos son opcionales porque un PUT puede modificar solo
    # una parte de la cámara sin reenviar todo el documento.
    nombre: str | None = None
    ubicacion: str | None = None
    estado: str | None = None
    fecha_instalacion: str | None = None

    @field_validator("nombre", "ubicacion", "estado", "fecha_instalacion")
    @classmethod
    def validar_texto(cls, valor: str | None) -> str | None:
        return texto_requerido(valor)


class CamaraRespuesta(CamaraBase):
    # Modelo de salida para cámaras. Expone el _id de MongoDB como campo
    # principal para conservar la estructura real de la colección.
    id: str = Field(alias="_id")

    model_config = ConfigDict(populate_by_name=True)


class EventoRespuesta(BaseModel):
    # Los eventos quedan como registro visual de solo lectura. Este modelo
    # describe lo que el backend devuelve cuando consulta Ani_cam.eventos.
    id: str = Field(alias="_id")
    camara_id: str
    fecha: str
    hora: str
    tipo: Literal["foto", "video"]
    descripcion: str
    estado: str

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("camara_id", "fecha", "hora", "descripcion", "estado")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return texto_requerido(valor) or ""


class PeticionCrear(BaseModel):
    # Datos mínimos que envía el dashboard para pedirle algo a una cámara.
    # La fecha y el estado se completan en el backend para mantener consistencia.
    camara_id: str
    tipo: Literal["foto", "video"]

    @field_validator("camara_id")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return texto_requerido(valor) or ""


class PeticionActualizar(BaseModel):
    # Actualización controlada del estado de una petición. Solo se aceptan los
    # tres estados definidos para el MVP, sin estados intermedios.
    estado: Literal["pendiente", "ejecutado", "error"]


class PeticionRespuesta(BaseModel):
    # Modelo de salida de la colección peticiones. El _id es ObjectId en MongoDB,
    # pero se serializa como texto antes de responder por HTTP.
    id: str = Field(alias="_id")
    camara_id: str
    tipo: Literal["foto", "video"]
    estado: Literal["pendiente", "ejecutado", "error"]
    fecha_hora: str

    model_config = ConfigDict(populate_by_name=True)


class MensajeRespuesta(BaseModel):
    # Respuesta simple reutilizable para operaciones que solo necesitan
    # informar el resultado al dashboard.
    mensaje: str
