"""CRUD de las cámaras registradas en Ani_cam.camaras."""

# APIRouter agrupa las rutas; Depends inyecta MongoDB; HTTPException y status
# devuelven códigos HTTP comprensibles cuando una operación no puede realizarse.
from fastapi import APIRouter, Depends, HTTPException, status
# Base de datos tipa la base Ani_cam. DuplicateKeyError protege contra IDs repetidos.
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

# La dependencia entrega la conexión centralizada, sin que este enrutador abra otra.
from base_datos.conexion import obtener_base_datos
# MongoDB puede devolver tipos no serializables como ObjectId; esta función los
# adapta para que FastAPI responda JSON al Panel de control.
from base_datos.identificador_objeto import serializar_documento
# Pydantic valida la información que llega y documenta la respuesta de cada ruta.
from modelos.esquemas import CamaraActualizar, CamaraCrear, CamaraRespuesta, MensajeRespuesta


# inicio.py agrega /api/v1 delante de este prefijo. Estas rutas las utiliza el
# Panel de control para administrar las cámaras que luego se eligen en Peticiones.
enrutador = APIRouter(prefix="/camaras", tags=["cámaras"])


@enrutador.get("", response_model=list[CamaraRespuesta])
def listar_camaras(base_datos_personalizada: Database = Depends(obtener_base_datos)) -> list[dict]:
    """Devuelve las cámaras por identificador sin modificar la colección."""
    # GET /camaras devuelve todas las cámaras ordenadas por su ID textual. El
    # orden estable ayuda al selector del Panel de control y no modifica la colección.
    camaras = list(base_datos_personalizada.camaras.find().sort("_id", 1))
    return serializar_documento(camaras)


@enrutador.post("", response_model=CamaraRespuesta, status_code=status.HTTP_201_CREATED)
def crear_camara(
    camara: CamaraCrear,
    base_datos_personalizada: Database = Depends(obtener_base_datos),
) -> dict:
    """Crea una cámara con su ``_id`` textual y devuelve el documento guardado.

    La validación del esquema controla formato y campos; un identificador
    duplicado produce HTTP 409.
    """
    # POST /camaras recibe una cámara validada por CamaraCrear. El _id es manual,
    # por ejemplo camara001, porque así está definida la colección existente.
    datos = camara.model_dump(by_alias=True)
    if base_datos_personalizada.camaras.find_one({"_id": datos["_id"]}) is not None:
        # Comprobar antes permite responder un 409 entendible sin depender solo
        # del error técnico que MongoDB produciría por una clave duplicada.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cámara con ese ID.",
        )

    try:
        # Inserta el documento completo únicamente después de verificar el ID.
        base_datos_personalizada.camaras.insert_one(datos)
    except DuplicateKeyError as excepcion:
        # También se controla la carrera entre dos solicitudes simultáneas que
        # podrían intentar crear la misma cámara al mismo tiempo.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cámara con ese ID.",
        ) from excepcion

    # Se vuelve a leer el documento para responder exactamente lo que quedó
    # almacenado en Ani_cam, con el formato esperado por CamaraRespuesta.
    creada = base_datos_personalizada.camaras.find_one({"_id": datos["_id"]})
    return serializar_documento(creada)


@enrutador.get("/{camara_id}", response_model=CamaraRespuesta)
def obtener_camara(camara_id: str, base_datos_personalizada: Database = Depends(obtener_base_datos)) -> dict:
    """Busca una cámara por su identificador textual o responde HTTP 404."""
    # GET /camaras/{camara_id} permite consultar el detalle de una fila elegida
    # por el Panel de control. Los IDs de cámaras son texto, no ObjectId de MongoDB.
    camara = base_datos_personalizada.camaras.find_one({"_id": camara_id})
    if camara is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cámara no encontrada.",
        )
    return serializar_documento(camara)


@enrutador.put("/{camara_id}", response_model=CamaraRespuesta)
def modificar_camara(
    camara_id: str,
    camara: CamaraActualizar,
    base_datos_personalizada: Database = Depends(obtener_base_datos),
) -> dict:
    """Aplica únicamente los campos enviados y devuelve la cámara actualizada."""
    # PUT /camaras/{camara_id} recibe campos opcionales desde CamaraActualizar.
    # El identificador no cambia porque peticiones.camara_id depende de él.
    if base_datos_personalizada.camaras.find_one({"_id": camara_id}) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cámara no encontrada.",
        )

    # exclude_unset evita borrar datos que el Panel de control no envió al editar solo
    # un campo, por ejemplo la ubicación o el estado de una cámara.
    datos = camara.model_dump(exclude_unset=True)
    if datos:
        # $set modifica únicamente los campos enviados y conserva el resto del
        # documento, incluyendo su _id y las relaciones ya existentes.
        base_datos_personalizada.camaras.update_one({"_id": camara_id}, {"$set": datos})

    # La lectura posterior devuelve la versión final para actualizar la tabla UI.
    actualizada = base_datos_personalizada.camaras.find_one({"_id": camara_id})
    return serializar_documento(actualizada)


@enrutador.delete("/{camara_id}", response_model=MensajeRespuesta)
def eliminar_camara(camara_id: str, base_datos_personalizada: Database = Depends(obtener_base_datos)) -> dict:
    """Elimina una cámara existente sin borrar sus historiales relacionados."""
    # DELETE /camaras/{camara_id} elimina una cámara seleccionada en el Panel de control.
    # No borra automáticamente peticiones, eventos ni archivos relacionados para
    # no ocultar historial existente sin una regla explícita del proyecto.
    camara = base_datos_personalizada.camaras.find_one({"_id": camara_id})
    if camara is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cámara no encontrada.",
        )

    # Solo después de comprobar que existe se ejecuta la eliminación solicitada.
    base_datos_personalizada.camaras.delete_one({"_id": camara_id})
    return {"mensaje": "Camara eliminada correctamente."}
