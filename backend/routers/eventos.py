# ObjectId permite consultar eventos existentes por el _id generado por MongoDB.
from bson import ObjectId
# APIRouter agrupa endpoints; Depends inyecta MongoDB; HTTPException y status
# construyen respuestas de error claras cuando el evento no existe.
from fastapi import APIRouter, Depends, HTTPException, status
# Database tipa la conexión obtenida desde la dependencia de MongoDB.
from pymongo.database import Database

# get_database entrega la conexión activa con Ani_cam.
from database.connection import get_database
# serializar_documento convierte ObjectId a string antes de responder por HTTP.
from database.object_id import serializar_documento
# EventoRespuesta describe los documentos de eventos que se muestran en consulta.
from models.schemas import EventoRespuesta


# Este router expone la colección Ani_cam.eventos como historial visual.
# En esta etapa los eventos son solo lectura: no se crean desde FastAPI
# ni desde el dashboard cuando el usuario genera peticiones.
router = APIRouter(prefix="/eventos", tags=["eventos"])


@router.get("", response_model=list[EventoRespuesta])
def listar_eventos(db: Database = Depends(get_database)) -> list[dict]:
    # Consulta todos los eventos existentes y los ordena por fecha/hora para que
    # el dashboard muestre primero la actividad más reciente registrada.
    eventos = list(db.eventos.find().sort([("fecha", -1), ("hora", -1)]))
    return serializar_documento(eventos)


@router.get("/{evento_id}", response_model=EventoRespuesta)
def obtener_evento(evento_id: str, db: Database = Depends(get_database)) -> dict:
    # Valida que el identificador tenga formato ObjectId antes de buscarlo.
    # Si no es válido, se responde 404 porque para el usuario equivale a no existir.
    if not ObjectId.is_valid(evento_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )

    # Lee el evento existente sin modificarlo. La colección queda reservada como
    # registro de actividad para etapas futuras de captura automática.
    evento = db.eventos.find_one({"_id": ObjectId(evento_id)})
    if evento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )
    return serializar_documento(evento)
