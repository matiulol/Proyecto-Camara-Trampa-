from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from database.connection import get_database
from database.object_id import serializar_documento
from models.schemas import EventoCrear, EventoRespuesta


router = APIRouter(prefix="/eventos", tags=["eventos"])


@router.get("", response_model=list[EventoRespuesta])
def listar_eventos(db: Database = Depends(get_database)) -> list[dict]:
    eventos = list(db.eventos.find().sort([("fecha", -1), ("hora", -1)]))
    return serializar_documento(eventos)


@router.post("", response_model=EventoRespuesta, status_code=status.HTTP_201_CREATED)
def crear_evento(
    evento: EventoCrear,
    db: Database = Depends(get_database),
) -> dict:
    datos = evento.model_dump()
    if db.camaras.find_one({"_id": datos["camara_id"]}) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe una camara con el camara_id indicado.",
        )

    resultado = db.eventos.insert_one(datos)
    creado = db.eventos.find_one({"_id": resultado.inserted_id})
    return serializar_documento(creado)


@router.get("/{evento_id}", response_model=EventoRespuesta)
def obtener_evento(evento_id: str, db: Database = Depends(get_database)) -> dict:
    if not ObjectId.is_valid(evento_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )

    evento = db.eventos.find_one({"_id": ObjectId(evento_id)})
    if evento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )
    return serializar_documento(evento)
