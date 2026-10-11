"""CRUD de las cámaras registradas en Ani_cam.camaras."""

# APIRouter agrupa las rutas; Depends inyecta MongoDB; HTTPException y status
# devuelven códigos HTTP comprensibles cuando una operación no puede realizarse.
from fastapi import APIRouter, Depends, HTTPException, status
# Database tipa la base Ani_cam. DuplicateKeyError protege contra IDs repetidos.
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

# La dependencia entrega la conexión centralizada, sin que este router abra otra.
from database.connection import get_database
# MongoDB puede devolver tipos no serializables como ObjectId; esta función los
# adapta para que FastAPI responda JSON al Dashboard.
from database.object_id import serializar_documento
# Pydantic valida la información que llega y documenta la respuesta de cada ruta.
from models.schemas import CamaraActualizar, CamaraCrear, CamaraRespuesta, MensajeRespuesta


# main.py agrega /api/v1 delante de este prefijo. Estas rutas las utiliza el
# Dashboard para administrar las cámaras que luego se eligen en Peticiones.
router = APIRouter(prefix="/camaras", tags=["camaras"])


@router.get("", response_model=list[CamaraRespuesta])
def listar_camaras(db: Database = Depends(get_database)) -> list[dict]:
    # GET /camaras devuelve todas las cámaras ordenadas por su ID textual. El
    # orden estable ayuda al selector del Dashboard y no modifica la colección.
    camaras = list(db.camaras.find().sort("_id", 1))
    return serializar_documento(camaras)


@router.post("", response_model=CamaraRespuesta, status_code=status.HTTP_201_CREATED)
def crear_camara(
    camara: CamaraCrear,
    db: Database = Depends(get_database),
) -> dict:
    # POST /camaras recibe una cámara validada por CamaraCrear. El _id es manual,
    # por ejemplo camara001, porque así está definida la colección existente.
    datos = camara.model_dump(by_alias=True)
    if db.camaras.find_one({"_id": datos["_id"]}) is not None:
        # Comprobar antes permite responder un 409 entendible sin depender solo
        # del error técnico que MongoDB produciría por una clave duplicada.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una camara con ese ID.",
        )

    try:
        # Inserta el documento completo únicamente después de verificar el ID.
        db.camaras.insert_one(datos)
    except DuplicateKeyError as exc:
        # También se controla la carrera entre dos solicitudes simultáneas que
        # podrían intentar crear la misma cámara al mismo tiempo.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una camara con ese ID.",
        ) from exc

    # Se vuelve a leer el documento para responder exactamente lo que quedó
    # almacenado en Ani_cam, con el formato esperado por CamaraRespuesta.
    creada = db.camaras.find_one({"_id": datos["_id"]})
    return serializar_documento(creada)


@router.get("/{camara_id}", response_model=CamaraRespuesta)
def obtener_camara(camara_id: str, db: Database = Depends(get_database)) -> dict:
    # GET /camaras/{camara_id} permite consultar el detalle de una fila elegida
    # por el Dashboard. Los IDs de cámaras son texto, no ObjectId de MongoDB.
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
    # PUT /camaras/{camara_id} recibe campos opcionales desde CamaraActualizar.
    # El identificador no cambia porque peticiones.camara_id depende de él.
    if db.camaras.find_one({"_id": camara_id}) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camara no encontrada.",
        )

    # exclude_unset evita borrar datos que el Dashboard no envió al editar solo
    # un campo, por ejemplo la ubicación o el estado de una cámara.
    datos = camara.model_dump(exclude_unset=True)
    if datos:
        # $set modifica únicamente los campos enviados y conserva el resto del
        # documento, incluyendo su _id y las relaciones ya existentes.
        db.camaras.update_one({"_id": camara_id}, {"$set": datos})

    # La lectura posterior devuelve la versión final para actualizar la tabla UI.
    actualizada = db.camaras.find_one({"_id": camara_id})
    return serializar_documento(actualizada)


@router.delete("/{camara_id}", response_model=MensajeRespuesta)
def eliminar_camara(camara_id: str, db: Database = Depends(get_database)) -> dict:
    # DELETE /camaras/{camara_id} elimina una cámara seleccionada en el Dashboard.
    # No borra automáticamente peticiones, eventos ni archivos relacionados para
    # no ocultar historial existente sin una regla explícita del proyecto.
    camara = db.camaras.find_one({"_id": camara_id})
    if camara is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camara no encontrada.",
        )

    # Solo después de comprobar que existe se ejecuta la eliminación solicitada.
    db.camaras.delete_one({"_id": camara_id})
    return {"mensaje": "Camara eliminada correctamente."}
