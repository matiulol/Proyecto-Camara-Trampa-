"""Consulta el historial de eventos guardado en ``Ani_cam.eventos``.

Las rutas son de lectura; los registros pueden crearse como parte de una
captura PIR en el enrutador de peticiones y permanecen asociados a sus archivos.
"""

# ObjectId permite consultar eventos existentes por el _id generado por MongoDB.
from bson import ObjectId
# APIRouter agrupa rutas HTTP; Depends inyecta MongoDB; HTTPException y status
# construyen respuestas de error claras cuando el evento no existe.
from fastapi import APIRouter, Depends, HTTPException, status
# Base de datos tipa la conexión obtenida desde la dependencia de MongoDB.
from pymongo.database import Database

# obtener_base_datos entrega la conexión activa con Ani_cam.
from base_datos.conexion import obtener_base_datos
# serializar_documento convierte ObjectId a string antes de responder por HTTP.
from base_datos.identificador_objeto import serializar_documento
# EventoRespuesta describe los documentos de eventos que se muestran en consulta.
from modelos.esquemas import EventoRespuesta


# Este enrutador expone el historial para el Panel de control. Sus rutas sólo consultan;
# el flujo PIR registra eventos desde el enrutador de peticiones.
enrutador = APIRouter(prefix="/eventos", tags=["eventos"])


@enrutador.get("", response_model=list[EventoRespuesta])
def listar_eventos(base_datos_personalizada: Database = Depends(obtener_base_datos)) -> list[dict]:
    """Devuelve el historial de eventos ordenado por fecha y hora descendentes."""
    # Consulta todos los eventos existentes y los ordena por fecha/hora para que
    # el panel de control muestre primero la actividad más reciente registrada.
    eventos = list(base_datos_personalizada.eventos.find().sort([("fecha", -1), ("hora", -1)]))
    return serializar_documento(eventos)


@enrutador.get("/{evento_id}", response_model=EventoRespuesta)
def obtener_evento(evento_id: str, base_datos_personalizada: Database = Depends(obtener_base_datos)) -> dict:
    """Busca un evento por ObjectId y responde HTTP 404 si no existe."""
    # Valida que el identificador tenga formato ObjectId antes de buscarlo.
    # Si no es válido, se responde 404 porque para el usuario equivale a no existir.
    if not ObjectId.is_valid(evento_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )

    # Lee el evento existente sin modificarlo. La colección queda reservada como
    # registro de actividad para etapas futuras de captura automática.
    evento = base_datos_personalizada.eventos.find_one({"_id": ObjectId(evento_id)})
    if evento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )
    return serializar_documento(evento)
