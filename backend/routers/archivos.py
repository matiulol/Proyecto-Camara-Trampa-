"""Consulta segura de metadatos y enlaces temporales de capturas en B2."""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from database.connection import get_database
from database.object_id import serializar_documento
from services.servicio_b2 import ErrorB2, enlace_temporal

router = APIRouter(prefix="/archivos", tags=["archivos"])


_FORMATOS_FECHA_HORA = (
    "%Y-%m-%d %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
)


def _fecha_ordenable(archivo: dict) -> datetime:
    """Obtiene una fecha real sin alterar los metadatos históricos.

    En ``archivos`` hay registros heredados con fecha ``DD-MM-AAAA`` y otros
    nuevos con ``AAAA-MM-DD``. MongoDB ordenaba esas cadenas literalmente, por
    lo que una fecha antigua podía aparecer antes que una captura reciente en el
    Dashboard. Se normaliza sólo para la respuesta; el documento almacenado no
    se modifica. Si falta una fecha reconocible, se usa el tiempo del ObjectId
    como último recurso para conservar un orden estable.
    """
    fecha_hora = archivo.get("fecha_hora")
    if isinstance(fecha_hora, str):
        for formato in _FORMATOS_FECHA_HORA:
            try:
                return datetime.strptime(fecha_hora, formato)
            except ValueError:
                continue

    identificador = archivo.get("_id")
    if isinstance(identificador, ObjectId):
        return identificador.generation_time.astimezone(timezone.utc).replace(tzinfo=None)
    return datetime.min


def _listar_archivos_ordenados(db: Database, filtro: dict) -> list[dict]:
    """Lee y ordena metadatos por fecha cronológica, incluso los heredados."""
    archivos = list(db.archivos.find(filtro))
    return sorted(archivos, key=_fecha_ordenable, reverse=True)


def _archivo_o_404(archivo_id: str, db: Database) -> dict:
    if not ObjectId.is_valid(archivo_id):
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    archivo = db.archivos.find_one({"_id": ObjectId(archivo_id)})
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return archivo


@router.get("/camara/{camara_id}")
def listar_por_camara(camara_id: str, db: Database = Depends(get_database)) -> list[dict]:
    return serializar_documento(_listar_archivos_ordenados(db, {"id_camara": camara_id}))


@router.get("/peticion/{peticion_id}")
def listar_por_peticion(peticion_id: str, db: Database = Depends(get_database)) -> list[dict]:
    return serializar_documento(_listar_archivos_ordenados(db, {"peticion_id": peticion_id}))


@router.get("/evento/{evento_id}")
def listar_por_evento(evento_id: str, db: Database = Depends(get_database)) -> list[dict]:
    return serializar_documento(_listar_archivos_ordenados(db, {"id_evento": evento_id}))


@router.get("/{archivo_id}/visualizacion")
def obtener_enlace_visualizacion(archivo_id: str, db: Database = Depends(get_database)) -> dict:
    archivo = _archivo_o_404(archivo_id, db)
    if archivo.get("estado_subida") != "confirmada" or not archivo.get("clave_b2"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El archivo todavía no está disponible en la nube.")
    try:
        return {"url": enlace_temporal(archivo["clave_b2"]), "expira_en_segundos": 300}
    except ErrorB2 as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
