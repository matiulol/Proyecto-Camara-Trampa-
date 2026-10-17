"""Conexión única entre FastAPI y la base de datos Ani_cam."""

# MongoClient abre y administra el canal de comunicación con MongoDB. Database
# se usa para indicar que la variable database representa una base concreta.
import logging

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import ConfigurationError, ConnectionFailure, OperationFailure, PyMongoError

# settings centraliza la URI, el nombre Ani_cam y el tiempo máximo de conexión.
# Así ningún router escribe estos valores directamente en su propio código.
from config.settings import settings


logger = logging.getLogger(__name__)

# Estos índices no son únicos ni cambian documentos existentes. Corresponden a
# los filtros y ordenamientos que usan Dashboard y Raspberry: el polling busca
# la orden pendiente más antigua de una cámara, mientras las demás pantallas
# consultan historiales y archivos por sus relaciones ya existentes.
INDICES_CONSULTA: tuple[tuple[str, tuple[tuple[str, int], ...], str], ...] = (
    (
        "peticiones",
        (("camara_id", ASCENDING), ("estado", ASCENDING), ("fecha_hora", ASCENDING)),
        "peticiones_pendientes_por_camara",
    ),
    (
        "peticiones",
        (("fecha_hora", DESCENDING),),
        "peticiones_historial_por_fecha",
    ),
    ("archivos", (("id_camara", ASCENDING),), "archivos_por_camara"),
    ("archivos", (("peticion_id", ASCENDING),), "archivos_por_peticion"),
    ("archivos", (("id_evento", ASCENDING),), "archivos_por_evento"),
    (
        "eventos",
        (("fecha", DESCENDING), ("hora", DESCENDING)),
        "eventos_historial_por_fecha",
    ),
    ("usuarios", (("usuario", ASCENDING),), "usuarios_por_nombre"),
)


def _crear_cliente() -> MongoClient:
    """Crea el cliente sin permitir que una URI inválida llegue a los registros."""
    try:
        return MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS,
        )
    except ConfigurationError:
        raise RuntimeError(
            "MONGODB_URI no tiene un formato válido. Revise backend/.env sin "
            "copiar la URI ni la contraseña en los registros."
        ) from None


# Este cliente se crea una sola vez cuando FastAPI importa este módulo. Todos los
# endpoints reutilizan la misma configuración en lugar de abrir una conexión por
# cada solicitud HTTP, lo que simplifica el proyecto y evita recursos repetidos.
client: MongoClient = _crear_cliente()
# Selecciona exactamente la base existente Ani_cam. Esta línea no crea otra base:
# MongoDB solo la materializaría al insertar un documento, operación que realizan
# los routers ya existentes cuando corresponde.
database: Database = client[settings.MONGODB_DATABASE]


def get_database() -> Database:
    # FastAPI usa esta función como dependencia en los routers. Al declararla con
    # Depends(get_database), cada endpoint recibe la misma instancia configurada
    # y puede consultar sus colecciones sin conocer cómo se creó la conexión.
    return database


def comprobar_conexion() -> None:
    # Envía el comando administrativo ping al servidor de MongoDB. No modifica
    # documentos: sirve para comprobar al iniciar la API o en /health que Ani_cam
    # está disponible antes de atender operaciones del Dashboard o Raspberry.
    try:
        client.admin.command("ping")
    except (ConfigurationError, ConnectionFailure, OperationFailure) as exc:
        # No se propaga el error original: algunos controladores incluyen la URI
        # configurada y nunca debe aparecer una contraseña en logs o respuestas.
        raise RuntimeError(
            "No se pudo conectar a MongoDB local. Verifique que el servicio esté "
            "iniciado en localhost:27017 y que MONGODB_DATABASE sea Ani_cam."
        ) from None


def preparar_indices(db: Database | None = None) -> bool:
    """Asegura índices de consulta sin migrar ni modificar datos de ``Ani_cam``.

    MongoDB ignora una creación cuyo índice con el mismo nombre ya existe, por
    lo que esta operación es idempotente y se puede invocar en cada arranque.
    Si la cuenta local no dispone de permiso para crear índices, FastAPI sigue
    disponible —las consultas son correctas aunque menos eficientes— y deja una
    advertencia clara en el registro del servidor.
    """
    destino = database if db is None else db
    try:
        for coleccion, campos, nombre in INDICES_CONSULTA:
            destino[coleccion].create_index(list(campos), name=nombre)
    except PyMongoError:
        # No se incluye el error original porque algunos controladores de Mongo
        # pueden incorporar detalles de conexión. La advertencia permite
        # diagnosticar permisos sin arriesgar credenciales en los logs.
        logger.warning(
            "No se pudieron preparar los índices de consulta de Ani_cam; "
            "el backend continuará sin esa optimización."
        )
        return False
    return True


def cerrar_conexion() -> None:
    # Libera sockets y recursos de PyMongo al cerrar FastAPI. main.py invoca esta
    # función en el ciclo de vida de la aplicación para terminar ordenadamente.
    client.close()
