# datetime se usa para guardar fecha_hora de creación de la petición.
from datetime import datetime

# ObjectId permite consultar documentos de MongoDB por el _id real generado.
from bson import ObjectId
# APIRouter agrupa endpoints; Depends inyecta MongoDB; HTTPException devuelve
# errores claros al cliente; status evita escribir códigos HTTP "mágicos".
from fastapi import APIRouter, Depends, HTTPException, status
# Database tipa la conexión que se recibe desde database.connection.
from pymongo.database import Database

# get_database entrega la instancia conectada a la base Ani_cam.
from database.connection import get_database
# serializar_documento convierte ObjectId en texto para que FastAPI responda JSON.
from database.object_id import serializar_documento
# Modelos Pydantic que validan entrada y salida de peticiones.
from models.schemas import PeticionActualizar, PeticionCrear, PeticionRespuesta


# Agrupa todos los endpoints de peticiones bajo /api/v1/peticiones.
# Una petición representa "quiero que esta cámara haga algo".
router = APIRouter(prefix="/peticiones", tags=["peticiones"])


def _obtener_peticion_o_404(peticion_id: str, db: Database) -> dict:
    # Valida el ObjectId recibido por URL antes de consultar MongoDB. Esto evita
    # errores internos cuando el usuario envía un identificador con formato inválido.
    if not ObjectId.is_valid(peticion_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Petición no encontrada.",
        )

    # Busca la petición en Ani_cam.peticiones usando el ObjectId real de MongoDB.
    peticion = db.peticiones.find_one({"_id": ObjectId(peticion_id)})
    if peticion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Petición no encontrada.",
        )
    return peticion


@router.post("", response_model=PeticionRespuesta, status_code=status.HTTP_201_CREATED)
def crear_peticion(
    peticion: PeticionCrear,
    db: Database = Depends(get_database),
) -> dict:
    # Verifica que la cámara exista antes de crear la solicitud. Las cámaras usan
    # IDs manuales como camara001, por eso se consulta _id como texto y no ObjectId.
    if db.camaras.find_one({"_id": peticion.camara_id}) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe una cámara con el camara_id indicado.",
        )

    # La petición comienza siempre como pendiente porque todavía no hay Raspberry
    # conectada que pueda ejecutarla en esta etapa del proyecto.
    datos = peticion.model_dump()
    datos["estado"] = "pendiente"
    datos["fecha_hora"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Inserta el documento en la colección nueva Ani_cam.peticiones y luego lo
    # vuelve a leer para devolver la versión exacta guardada por MongoDB.
    resultado = db.peticiones.insert_one(datos)
    creada = db.peticiones.find_one({"_id": resultado.inserted_id})
    return serializar_documento(creada)


@router.get("", response_model=list[PeticionRespuesta])
def listar_peticiones(db: Database = Depends(get_database)) -> list[dict]:
    # Devuelve el historial de peticiones ordenado desde las más recientes.
    # No crea eventos ni modifica otra colección.
    peticiones = list(db.peticiones.find().sort("fecha_hora", -1))
    return serializar_documento(peticiones)


@router.get("/{peticion_id}", response_model=PeticionRespuesta)
def obtener_peticion(peticion_id: str, db: Database = Depends(get_database)) -> dict:
    # Consulta una petición puntual para mostrar detalle o confirmar estado desde
    # el dashboard.
    peticion = _obtener_peticion_o_404(peticion_id, db)
    return serializar_documento(peticion)


@router.put("/{peticion_id}", response_model=PeticionRespuesta)
def actualizar_peticion(
    peticion_id: str,
    peticion: PeticionActualizar,
    db: Database = Depends(get_database),
) -> dict:
    # Primero se comprueba que la petición exista. El modelo Pydantic ya limita
    # estado a: pendiente, ejecutado o error.
    _obtener_peticion_o_404(peticion_id, db)

    # Actualiza únicamente el estado. No se permite cambiar cámara, tipo ni fecha
    # porque esos datos forman parte del historial de la solicitud original.
    db.peticiones.update_one(
        {"_id": ObjectId(peticion_id)},
        {"$set": {"estado": peticion.estado}},
    )
    actualizada = db.peticiones.find_one({"_id": ObjectId(peticion_id)})
    return serializar_documento(actualizada)
