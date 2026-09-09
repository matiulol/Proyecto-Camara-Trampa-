from pymongo import MongoClient
from pymongo.database import Database

from config.settings import settings


client: MongoClient = MongoClient(
    settings.MONGODB_URI,
    serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS,
)
database: Database = client[settings.MONGODB_DATABASE]


def get_database() -> Database:
    return database


def comprobar_conexion() -> None:
    client.admin.command("ping")


def cerrar_conexion() -> None:
    client.close()
