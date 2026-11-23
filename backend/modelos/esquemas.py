"""Esquemas Pydantic para validar las entradas y respuestas de las rutas HTTP.

Los modelos reflejan los nombres y estados usados por la base ``Ani_cam`` y
mantienen explícitas las diferencias entre peticiones manuales y capturas PIR.
"""

# Literal permite limitar campos a valores exactos, por ejemplo los tipos
# de petición aceptados por el MVP: "foto" o "video".
from typing import Literal

# BaseModel y Field son la base de los esquemas de entrada/salida de FastAPI.
# Los validadores se usan para limpiar texto antes de que llegue a MongoDB.
from pydantic import BaseModel, ConfigDict, Field, field_validator


def texto_requerido(valor: str | None) -> str | None:
    """Recorta un texto opcional y rechaza cadenas vacías tras el recorte."""
    # Centraliza la validación de textos para evitar repetir la misma lógica
    # en cámaras, eventos, autenticación y peticiones.
    if valor is None:
        return valor
    valor_limpio = valor.strip()
    if not valor_limpio:
        raise ValueError("El campo no puede estar vacío.")
    return valor_limpio


class InicioSesion(BaseModel):
    """Credenciales de entrada; conserva el alias español de MongoDB."""
    # Modelo usado por la ruta HTTP de inicio de sesión. El campo interno se llama
    # "contrasena" para que Python sea simple de escribir, pero el alias
    # mantiene el nombre real en español usado por MongoDB y el panel de control.
    usuario: str
    contrasena: str = Field(alias="contraseña")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("usuario", "contrasena")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        """Normaliza cada credencial y rechaza valores vacíos."""
        return texto_requerido(valor) or ""


class UsuarioPublico(BaseModel):
    """Campos no confidenciales que se devuelven tras iniciar sesión."""
    # Representa los datos de usuario que se devuelven al panel de control.
    # La contraseña nunca se incluye en este modelo de respuesta.
    identificador: str = Field(alias="_id")
    usuario: str
    rol: str

    model_config = ConfigDict(populate_by_name=True)


class InicioSesionRespuesta(BaseModel):
    """Sobre de respuesta del inicio de sesión con mensaje y usuario público."""
    # Respuesta completa del inicio de sesión: un mensaje legible y los datos públicos
    # del usuario autenticado.
    mensaje: str
    usuario: UsuarioPublico


class CamaraBase(BaseModel):
    """Campos compartidos por creación y respuesta de cámaras.

    El identificador queda fuera de esta base y se valida en los modelos
    específicos; el período de espera PIR se limita al intervalo admitido por el Panel de control.
    """
    # Campos compartidos por creación, modificación y respuesta de cámaras.
    # El ID no va aquí porque en MongoDB se guarda como _id manual tipo camara001.
    nombre: str
    ubicacion: str
    estado: str
    fecha_instalacion: str
    # Estos valores viven por cámara en MongoDB para que el Panel de control configure
    # el comportamiento PIR de cada Raspberry y sobrevivan reinicios.
    pir_habilitado: bool = False
    pir_tipo_captura: Literal["foto", "video"] = "foto"
    pir_cooldown_segundos: int = Field(default=10, ge=3, le=3600)

    @field_validator("nombre", "ubicacion", "estado", "fecha_instalacion")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        """Recorta los campos descriptivos obligatorios de la cámara."""
        return texto_requerido(valor) or ""


class CamaraCrear(CamaraBase):
    """Datos de alta con un identificador manual como ``camara001``."""
    # La cámara usa un _id manual en español, por ejemplo camara001.
    # No se usa ObjectId para cámaras porque así está definida la base existente.
    identificador: str = Field(alias="_id", pattern=r"^camara\d{3,}$")

    model_config = ConfigDict(populate_by_name=True)


class CamaraActualizar(BaseModel):
    """Campos opcionales para actualizar una cámara sin borrar los omitidos."""
    # Todos los campos son opcionales porque un PUT puede modificar solo
    # una parte de la cámara sin reenviar todo el documento.
    nombre: str | None = None
    ubicacion: str | None = None
    estado: str | None = None
    fecha_instalacion: str | None = None
    pir_habilitado: bool | None = None
    pir_tipo_captura: Literal["foto", "video"] | None = None
    pir_cooldown_segundos: int | None = Field(default=None, ge=3, le=3600)

    @field_validator("nombre", "ubicacion", "estado", "fecha_instalacion")
    @classmethod
    def validar_texto(cls, valor: str | None) -> str | None:
        """Recorta los textos enviados y permite campos no incluidos."""
        return texto_requerido(valor)


class CamaraRespuesta(CamaraBase):
    """Representación de salida que expone MongoDB ``_id`` como alias."""
    # Modelo de salida para cámaras. Expone el _id de MongoDB como campo
    # principal para conservar la estructura real de la colección.
    identificador: str = Field(alias="_id")

    model_config = ConfigDict(populate_by_name=True)


class EventoRespuesta(BaseModel):
    """Campos de evento que el servidor presenta en el historial."""
    # Los eventos quedan como registro visual de solo lectura. Este modelo
    # describe lo que el servidor devuelve cuando consulta Ani_cam.eventos.
    identificador: str = Field(alias="_id")
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
        """Normaliza los datos textuales descriptivos del evento."""
        return texto_requerido(valor) or ""


class PeticionCrear(BaseModel):
    """Orden de captura solicitada para una cámara por Panel de control o PIR."""
    # Datos mínimos que envía el panel de control para pedirle algo a una cámara.
    # La fecha y el estado se completan en el servidor para mantener consistencia.
    camara_id: str
    tipo: Literal["foto", "video"]
    origen: Literal["manual", "pir"] = "manual"

    @field_validator("camara_id")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        """Recorta el identificador textual de la cámara."""
        return texto_requerido(valor) or ""


class CapturaPIRError(BaseModel):
    """Fallo de una captura PIR aceptada que no creó una petición pendiente.

    El servidor registra estos datos como evento de error asociado a la cámara.
    """
    camara_id: str
    tipo: Literal["foto", "video"]
    mensaje_error: str

    @field_validator("camara_id", "mensaje_error")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        """Rechaza identificadores o mensajes de error vacíos."""
        return texto_requerido(valor) or ""


class PeticionActualizar(BaseModel):
    """Cambio permitido del estado de una petición ya existente."""
    # Actualización controlada del estado de una petición. Solo se aceptan los
    # tres estados definidos para el MVP, sin estados intermedios.
    estado: Literal["pendiente", "ejecutado", "error"]


class PeticionResultado(BaseModel):
    """Resultado final enviado por Raspberry para una orden obtenida por consulta periódica.

    Un éxito requiere que la ruta HTTP de archivo confirme la subida; este modelo
    se utiliza principalmente para comunicar fallos de hardware o transferencia.
    """
    # Datos que envía exclusivamente la Raspberry cuando termina una petición que
    # recibió por consulta periódica. El servidor conserva el control de MongoDB: la Raspberry
    # nunca escribe documentos directamente en Ani_cam.
    estado: Literal["ejecutado", "error"]
    nombre_archivo: str | None = None
    ruta_local: str | None = None
    mensaje_error: str | None = None

    @field_validator("nombre_archivo", "ruta_local", "mensaje_error")
    @classmethod
    def validar_texto_opcional(cls, valor: str | None) -> str | None:
        """Recorta los detalles opcionales sin convertir ausencias en texto."""
        return texto_requerido(valor)


class PeticionRespuesta(BaseModel):
    """Datos de historial de una petición y, si existen, de su resultado."""
    # Modelo de salida de la colección peticiones. El _id es ObjectId en MongoDB,
    # pero se serializa como texto antes de responder por HTTP.
    identificador: str = Field(alias="_id")
    camara_id: str
    tipo: Literal["foto", "video"]
    estado: Literal["pendiente", "ejecutado", "error"]
    fecha_hora: str
    archivo_id: str | None = None
    nombre_archivo: str | None = None
    mensaje_error: str | None = None
    origen: Literal["manual", "pir"] = "manual"

    model_config = ConfigDict(populate_by_name=True)


class MensajeRespuesta(BaseModel):
    """Respuesta breve para operaciones que devuelven un mensaje al cliente."""
    # Respuesta simple reutilizable para operaciones que solo necesitan
    # informar el resultado al panel de control.
    mensaje: str
