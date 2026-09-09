from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from database.connection import get_database
from database.object_id import serializar_documento
from models.schemas import CamaraActualizar, CamaraCrear, CamaraRespuesta, MensajeRespuesta


router = APIRouter(prefix="/camaras", tags=["camaras"])


@router.get("", response_model=list[CamaraRespuesta])
def listar_camaras(db: Database = Depends(get_database)) -> list[dict]:
    camaras = list(db.camaras.find().sort("_id", 1))
    return serializar_documento(camaras)


@router.post("", response_model=CamaraRespuesta, status_code=status.HTTP_201_CREATED)
def crear_camara(
    camara: CamaraCrear,
    db: Database = Depends(get_database),
) -> dict:
    datos = camara.model_dump(by_alias=True)
    if db.camaras.find_one({"_id": datos["_id"]}) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una camara con ese ID.",
        )

    try:
        db.camaras.insert_one(datos)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una camara con ese ID.",
        ) from exc

    creada = db.camaras.find_one({"_id": datos["_id"]})
    return serializar_documento(creada)


@router.get("/{camara_id}", response_model=CamaraRespuesta)
def obtener_camara(camara_id: str, db: Database = Depends(get_database)) -> dict:
    camara = db.camaras.find_one({"_id": camara_id})
    if camara is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camara no encontrada.",
        )
    return serializar_documento(camara)


@router.put("/{camara_id}", response_model=CamaraRespuesta)
def modificar_camara(
    camara_id: str,
    camara: CamaraActualizar,
    db: Database = Depends(get_database),
) -> dict:
    if db.camaras.find_one({"_id": camara_id}) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camara no encontrada.",
        )

    datos = camara.model_dump(exclude_unset=True)
    if datos:
        db.camaras.update_one({"_id": camara_id}, {"$set": datos})

    actualizada = db.camaras.find_one({"_id": camara_id})
    return serializar_documento(actualizada)


@router.delete("/{camara_id}", response_model=MensajeRespuesta)
def eliminar_camara(camara_id: str, db: Database = Depends(get_database)) -> dict:
    camara = db.camaras.find_one({"_id": camara_id})
    if camara is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camara no encontrada.",
        )

    db.camaras.delete_one({"_id": camara_id})
    return {"mensaje": "Camara eliminada correctamente."}
