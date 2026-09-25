"""Conexión única entre FastAPI y la base de datos Ani_cam."""

# MongoClient abre y administra el canal de comunicación con MongoDB. Database
# se usa para indicar que la variable database representa una base concreta.
from pymongo import MongoClient
from pymongo.database import Database

# settings centraliza la URI, el nombre Ani_cam y el tiempo máximo de conexión.
# Así ningún router escribe estos valores directamente en su propio código.
from config.settings import settings


# Este cliente se crea una sola vez cuando FastAPI importa este módulo. Todos los
# endpoints reutilizan la misma configuración en lugar de abrir una conexión por
# cada solicitud HTTP, lo que simplifica el proyecto y evita recursos repetidos.
client: MongoClient = MongoClient(
    settings.MONGODB_URI,
    serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS,
)
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
    client.admin.command("ping")


def cerrar_conexion() -> None:
    # Libera sockets y recursos de PyMongo al cerrar FastAPI. main.py invoca esta
    # función en el ciclo de vida de la aplicación para terminar ordenadamente.
    client.close()
