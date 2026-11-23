"""Conexión única entre FastAPI y la base de datos Ani_cam."""

# MongoClient abre y administra el canal de comunicación con MongoDB. Base de datos
# se usa para indicar que la variable base de datos representa una base concreta.
import logging

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import ConfigurationError, ConnectionFailure, OperationFailure, PyMongoError

# configuración centraliza la URI, el nombre Ani_cam y el tiempo máximo de conexión.
# Así ningún enrutador escribe estos valores directamente en su propio código.
from configuracion.ajustes import configuracion


registrador = logging.getLogger(__name__)

# Estos índices no son únicos ni cambian documentos existentes. Corresponden a
# los filtros y ordenamientos que usan el Panel de control y Raspberry: la consulta periódica busca
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
            configuracion.URI_MONGODB,
            serverSelectionTimeoutMS=configuracion.TIEMPO_ESPERA_MONGODB_MS,
        )
    except ConfigurationError:
        raise RuntimeError(
            "MONGODB_URI no tiene un formato válido. Revise backend/.env sin "
            "copiar la URI ni la contraseña en los registros."
        ) from None


# Este cliente se crea una sola vez cuando FastAPI importa este módulo. Todos los
# rutas HTTP reutilizan la misma configuración en lugar de abrir una conexión por
# cada solicitud HTTP, lo que simplifica el proyecto y evita recursos repetidos.
cliente_mongo: MongoClient = _crear_cliente()
# Selecciona exactamente la base existente Ani_cam. Esta línea no crea otra base:
# MongoDB solo la materializaría al insertar un documento, operación que realizan
# los enrutadores ya existentes cuando corresponde.
base_datos_mongo: Database = cliente_mongo[configuracion.BASE_DATOS_MONGODB]


def obtener_base_datos() -> Database:
    """Entrega la instancia compartida de ``Ani_cam`` a una dependencia FastAPI.

    Los enrutadores usan esta función con ``Depends`` para consultar la conexión
    creada al importar el módulo, sin abrir clientes por solicitud.
    """
    # FastAPI usa esta función como dependencia en las rutas. Al declararla con
    # Depends(obtener_base_datos), cada ruta HTTP recibe la misma instancia configurada
    # y puede consultar sus colecciones sin conocer cómo se creó la conexión.
    return base_datos_mongo


def comprobar_conexion() -> None:
    """Comprueba con un ping que el servidor MongoDB local responda.

    No escribe datos. Si la comprobación falla, genera un error de configuración
    seguro que no incluye la URI ni otros valores sensibles.
    """
    # Envía el comando administrativo ping al servidor de MongoDB. No modifica
    # documentos: sirve para comprobar al iniciar la API o en /health que Ani_cam
    # está disponible antes de atender operaciones del Panel de control o Raspberry.
    try:
        cliente_mongo.admin.command("ping")
    except (ConfigurationError, ConnectionFailure, OperationFailure) as excepcion:
        # No se propaga el error original: algunos controladores incluyen la URI
        # configurada y nunca debe aparecer una contraseña en logs o respuestas.
        raise RuntimeError(
            "No se pudo conectar a MongoDB local. Verifique que el servicio esté "
            "iniciado en localhost:27017 y que MONGODB_DATABASE sea Ani_cam."
        ) from None


def preparar_indices(base_datos_personalizada: Database | None = None) -> bool:
    """Asegura índices de consulta sin migrar ni modificar datos de ``Ani_cam``.

    MongoDB ignora una creación cuyo índice con el mismo nombre ya existe, por
    lo que esta operación es idempotente y se puede invocar en cada arranque.
    Si la cuenta local no dispone de permiso para crear índices, FastAPI sigue
    disponible —las consultas son correctas aunque menos eficientes— y deja una
    advertencia clara en el registro del servidor.
    """
    destino = base_datos_mongo if base_datos_personalizada is None else base_datos_personalizada
    try:
        for coleccion, campos, nombre in INDICES_CONSULTA:
            destino[coleccion].create_index(list(campos), name=nombre)
    except PyMongoError:
        # No se incluye el error original porque algunos controladores de Mongo
        # pueden incorporar detalles de conexión. La advertencia permite
        # diagnosticar permisos sin arriesgar credenciales en los logs.
        registrador.warning(
            "No se pudieron preparar los índices de consulta de Ani_cam; "
            "el servidor continuará sin esa optimización."
        )
        return False
    return True


def cerrar_conexion() -> None:
    """Cierra el cliente MongoDB compartido al finalizar FastAPI."""
    # Libera sockets y recursos de PyMongo al cerrar FastAPI. inicio.py invoca esta
    # función en el ciclo de vida de la aplicación para terminar ordenadamente.
    cliente_mongo.close()
