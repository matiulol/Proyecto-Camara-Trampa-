from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def texto_requerido(valor: str | None) -> str | None:
    if valor is None:
        return valor
    valor_limpio = valor.strip()
    if not valor_limpio:
        raise ValueError("El campo no puede estar vacio.")
    return valor_limpio


class InicioSesion(BaseModel):
    usuario: str
    contrasena: str = Field(alias="contraseña")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("usuario", "contrasena")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return texto_requerido(valor) or ""


class UsuarioPublico(BaseModel):
    id: str = Field(alias="_id")
    usuario: str
    rol: str

    model_config = ConfigDict(populate_by_name=True)


class InicioSesionRespuesta(BaseModel):
    mensaje: str
    usuario: UsuarioPublico


class CamaraBase(BaseModel):
    nombre: str
    ubicacion: str
    estado: str
    fecha_instalacion: str

    @field_validator("nombre", "ubicacion", "estado", "fecha_instalacion")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return texto_requerido(valor) or ""


class CamaraCrear(CamaraBase):
    id: str = Field(alias="_id", pattern=r"^camara\d{3,}$")

    model_config = ConfigDict(populate_by_name=True)


class CamaraActualizar(BaseModel):
    nombre: str | None = None
    ubicacion: str | None = None
    estado: str | None = None
    fecha_instalacion: str | None = None

    @field_validator("nombre", "ubicacion", "estado", "fecha_instalacion")
    @classmethod
    def validar_texto(cls, valor: str | None) -> str | None:
        return texto_requerido(valor)


class CamaraRespuesta(CamaraBase):
    id: str = Field(alias="_id")

    model_config = ConfigDict(populate_by_name=True)


class EventoCrear(BaseModel):
    camara_id: str
    fecha: str
    hora: str
    tipo: Literal["foto", "video"]
    descripcion: str
    estado: str

    @field_validator("camara_id", "fecha", "hora", "descripcion", "estado")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return texto_requerido(valor) or ""


class EventoRespuesta(EventoCrear):
    id: str = Field(alias="_id")

    model_config = ConfigDict(populate_by_name=True)


class MensajeRespuesta(BaseModel):
    mensaje: str
