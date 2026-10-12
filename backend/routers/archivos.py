"""Consulta segura de metadatos y enlaces temporales de capturas en B2."""
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from database.connection import get_database
from database.object_id import serializar_documento
from services.servicio_b2 import ErrorB2, enlace_temporal

router = APIRouter(prefix="/archivos", tags=["archivos"])


def _archivo_o_404(archivo_id: str, db: Database) -> dict:
    if not ObjectId.is_valid(archivo_id):
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    archivo = db.archivos.find_one({"_id": ObjectId(archivo_id)})
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return archivo


@router.get("/camara/{camara_id}")
def listar_por_camara(camara_id: str, db: Database = Depends(get_database)) -> list[dict]:
    return serializar_documento(list(db.archivos.find({"id_camara": camara_id}).sort("fecha_hora", -1)))


@router.get("/peticion/{peticion_id}")
def listar_por_peticion(peticion_id: str, db: Database = Depends(get_database)) -> list[dict]:
    return serializar_documento(list(db.archivos.find({"peticion_id": peticion_id}).sort("fecha_hora", -1)))


@router.get("/evento/{evento_id}")
def listar_por_evento(evento_id: str, db: Database = Depends(get_database)) -> list[dict]:
    return serializar_documento(list(db.archivos.find({"id_evento": evento_id}).sort("fecha_hora", -1)))


@router.get("/{archivo_id}/visualizacion")
def obtener_enlace_visualizacion(archivo_id: str, db: Database = Depends(get_database)) -> dict:
    archivo = _archivo_o_404(archivo_id, db)
    if archivo.get("estado_subida") != "confirmada" or not archivo.get("clave_b2"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El archivo todavía no está disponible en la nube.")
    try:
        return {"url": enlace_temporal(archivo["clave_b2"]), "expira_en_segundos": 300}
    except ErrorB2 as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
