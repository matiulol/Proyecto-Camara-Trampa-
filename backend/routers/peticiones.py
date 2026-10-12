# datetime se usa para guardar fecha_hora de creación de la petición.
from datetime import datetime

# ObjectId permite consultar documentos de MongoDB por el _id real generado.
from bson import ObjectId
# APIRouter agrupa endpoints; Depends inyecta MongoDB; HTTPException devuelve
# errores claros al cliente; status evita escribir códigos HTTP "mágicos".
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
# Database tipa la conexión que se recibe desde database.connection.
from pymongo.database import Database

# get_database entrega la instancia conectada a la base Ani_cam.
from database.connection import get_database
# serializar_documento convierte ObjectId en texto para que FastAPI responda JSON.
from database.object_id import serializar_documento
# Modelos Pydantic que validan entrada y salida de peticiones.
from models.schemas import (
    PeticionActualizar,
    PeticionCrear,
    PeticionRespuesta,
    PeticionResultado,
)
from services.servicio_b2 import ErrorB2, clave_objeto, subir_archivo


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

    # La petición comienza como pendiente hasta que la Raspberry asociada la
    # reciba mediante polling y comunique un resultado final.
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


@router.get("/pendientes/{camara_id}", response_model=PeticionRespuesta | None)
def obtener_peticion_pendiente(camara_id: str, db: Database = Depends(get_database)) -> dict | None:
    # Este endpoint es consumido por una Raspberry concreta mediante polling HTTP.
    # Devuelve solo la petición pendiente más antigua para respetar el orden en que
    # el dashboard solicitó las capturas y evitar que una cámara ejecute varias a la vez.
    peticion = db.peticiones.find_one(
        {"camara_id": camara_id, "estado": "pendiente"},
        sort=[("fecha_hora", 1)],
    )
    return serializar_documento(peticion) if peticion else None


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


@router.put("/{peticion_id}/resultado", response_model=PeticionRespuesta)
def registrar_resultado_peticion(
    peticion_id: str,
    resultado: PeticionResultado,
    db: Database = Depends(get_database),
) -> dict:
    # La Raspberry llama esta ruta al finalizar una foto o video. Se exige que la
    # petición siga pendiente para que un reintento tardío no sobrescriba el
    # historial ya terminado con estado ejecutado o error.
    peticion = _obtener_peticion_o_404(peticion_id, db)
    if peticion["estado"] != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La petición ya fue resuelta y no puede registrar otro resultado.",
        )

    cambios: dict[str, str] = {"estado": resultado.estado}
    if resultado.estado == "error":
        cambios["mensaje_error"] = resultado.mensaje_error or "La Raspberry no pudo completar la captura."
    else:
        # Una captura no queda ejecutada hasta que /archivo confirma B2. Esta
        # ruta se conserva para informar errores de hardware o transferencia.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use la carga de archivo para confirmar una captura ejecutada.",
        )

    db.peticiones.update_one({"_id": ObjectId(peticion_id)}, {"$set": cambios})
    actualizada = db.peticiones.find_one({"_id": ObjectId(peticion_id)})
    return serializar_documento(actualizada)


@router.post("/{peticion_id}/archivo", response_model=PeticionRespuesta)
def recibir_archivo_capturado(
    peticion_id: str,
    archivo: UploadFile = File(...),
    db: Database = Depends(get_database),
) -> dict:
    """Recibe una captura ya guardada en SD, la sube a B2 y recién la confirma.

    La Raspberry nunca conoce las credenciales B2: conserva su copia local y usa
    este canal HTTP existente para transferir los bytes al backend.
    """
    peticion = _obtener_peticion_o_404(peticion_id, db)
    if peticion["estado"] == "ejecutado":
        existente = db.archivos.find_one({"peticion_id": peticion_id, "estado_subida": "confirmada"})
        if existente:
            return serializar_documento(peticion)
        raise HTTPException(status_code=409, detail="La petición ya fue resuelta.")
    if peticion["estado"] == "error":
        raise HTTPException(status_code=409, detail="La petición ya tiene un error registrado.")

    extension = (archivo.filename or "").lower().rsplit(".", 1)[-1]
    esperado = {"foto": {"jpg", "jpeg"}, "video": {"mp4"}}[peticion["tipo"]]
    if extension not in esperado:
        raise HTTPException(status_code=422, detail="El tipo de archivo no coincide con la petición.")

    tipo = "imagen" if peticion["tipo"] == "foto" else "video"
    contenido = "image/jpeg" if tipo == "imagen" else "video/mp4"
    clave = clave_objeto(peticion["camara_id"], peticion_id, archivo.filename or "captura", tipo)
    try:
        # upload_fileobj transmite desde el archivo temporal HTTP; no depende de
        # ninguna ruta de la Raspberry y no duplica el objeto al reintentar.
        subir_archivo(archivo.file, clave, contenido)
    except ErrorB2 as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
    finally:
        archivo.file.close()

    # La consulta previa hace idempotente el registro si B2 confirmó una subida
    # anterior pero la Raspberry repite la solicitud por un corte de red.
    existente = db.archivos.find_one({"peticion_id": peticion_id})
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_archivo = {
        "id_camara": peticion["camara_id"], "peticion_id": peticion_id,
        "tipo": tipo, "nombre_archivo": archivo.filename, "fecha_hora": fecha,
        "clave_b2": clave, "estado_subida": "confirmada", "tipo_contenido": contenido,
    }
    if existente:
        db.archivos.update_one({"_id": existente["_id"]}, {"$set": datos_archivo})
        archivo_id = existente["_id"]
    else:
        archivo_id = db.archivos.insert_one(datos_archivo).inserted_id
    db.peticiones.update_one(
        {"_id": ObjectId(peticion_id)},
        {"$set": {"estado": "ejecutado", "archivo_id": str(archivo_id), "nombre_archivo": archivo.filename}},
    )
    return serializar_documento(db.peticiones.find_one({"_id": ObjectId(peticion_id)}))
