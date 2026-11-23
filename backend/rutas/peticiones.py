"""Gestiona órdenes de captura y la persistencia asociada a capturas PIR.

Las peticiones manuales siguen el ciclo de consulta periódica de Raspberry. Las capturas
PIR pueden registrarse directamente como eventos con metadatos, sin crear una
petición pendiente; en ambos flujos FastAPI coordina MongoDB y la subida a B2.
"""

# datetime se usa para guardar fecha_hora de creación de la petición.
from datetime import datetime
import logging

# ObjectId permite consultar documentos de MongoDB por el _id real generado.
from bson import ObjectId
# APIRouter agrupa rutas HTTP; Depends inyecta MongoDB; HTTPException devuelve
# errores claros al cliente; status evita escribir códigos HTTP "mágicos".
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
# Base de datos tipa la conexión que se recibe desde base_datos.conexion.
from pymongo.database import Database
from pymongo.errors import PyMongoError

# obtener_base_datos entrega la instancia conectada a la base Ani_cam.
from base_datos.conexion import obtener_base_datos
# serializar_documento convierte ObjectId en texto para que FastAPI responda JSON.
from base_datos.identificador_objeto import serializar_documento
# Modelos Pydantic que validan entrada y salida de peticiones.
from modelos.esquemas import (
    PeticionActualizar,
    CapturaPIRError,
    PeticionCrear,
    PeticionRespuesta,
    PeticionResultado,
)
from servicios.servicio_b2 import ErrorB2, clave_objeto, subir_archivo


# Agrupa todas las rutas HTTP de peticiones bajo /api/v1/peticiones.
# Una petición representa "quiero que esta cámara haga algo".
enrutador = APIRouter(prefix="/peticiones", tags=["peticiones"])
registrador = logging.getLogger(__name__)


def _actualizar_evento_relacionado(base_datos_personalizada: Database, peticion: dict, cambios: dict) -> None:
    """Actualiza sólo el evento PIR vinculado, cuando el flujo lo creó."""
    evento_id = peticion.get("evento_id")
    if not evento_id:
        return
    filtro = {"_id": ObjectId(evento_id) if ObjectId.is_valid(evento_id) else evento_id}
    resultado = base_datos_personalizada.eventos.update_one(filtro, {"$set": cambios})
    if resultado.matched_count != 1:
        raise RuntimeError("No se encontró el evento PIR asociado a la petición.")


def _confirmar_peticion_con_archivo(
    base_datos_personalizada: Database, peticion: dict, peticion_id: str, metadato: dict
) -> dict:
    """Vincula una captura B2 ya confirmada con su petición y evento PIR.

    Esta operación es idempotente a nivel del objeto B2: si una respuesta HTTP
    se pierde después de confirmar el metadato, un segundo intento sólo completa
    la relación de MongoDB y no vuelve a cargar bytes ni crea otro documento.
    """
    actualizacion = base_datos_personalizada.peticiones.update_one(
        {"_id": ObjectId(peticion_id), "estado": "pendiente"},
        {
            "$set": {
                "estado": "ejecutado",
                "archivo_id": str(metadato["_id"]),
                "nombre_archivo": metadato.get("nombre_archivo", ""),
            }
        },
    )
    if actualizacion.matched_count != 1:
        # Otro reintento pudo haber terminado la misma petición entre la lectura
        # inicial y esta actualización. Si dejó exactamente el mismo archivo
        # confirmado, se trata de un éxito idempotente y sólo resta asegurar el
        # vínculo del evento PIR. Cualquier otro estado sigue siendo conflicto.
        actualizada = base_datos_personalizada.peticiones.find_one({"_id": ObjectId(peticion_id)})
        if not (
            actualizada
            and actualizada.get("estado") == "ejecutado"
            and actualizada.get("archivo_id") == str(metadato["_id"])
        ):
            raise RuntimeError("No se pudo confirmar la petición en MongoDB.")
        _actualizar_evento_relacionado(
            base_datos_personalizada, actualizada, {"estado": "ejecutado", "archivo_id": str(metadato["_id"])}
        )
        return actualizada
    _actualizar_evento_relacionado(
        base_datos_personalizada, peticion, {"estado": "ejecutado", "archivo_id": str(metadato["_id"])}
    )
    actualizada = base_datos_personalizada.peticiones.find_one({"_id": ObjectId(peticion_id)})
    if actualizada is None:
        raise RuntimeError("No se pudo recuperar la petición confirmada.")
    return actualizada


def _obtener_peticion_o_404(peticion_id: str, base_datos_personalizada: Database) -> dict:
    """Valida y recupera una petición por ObjectId o responde HTTP 404."""
    # Valida el ObjectId recibido por URL antes de consultar MongoDB. Esto evita
    # errores internos cuando el usuario envía un identificador con formato inválido.
    if not ObjectId.is_valid(peticion_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Petición no encontrada.",
        )

    # Busca la petición en Ani_cam.peticiones usando el ObjectId real de MongoDB.
    peticion = base_datos_personalizada.peticiones.find_one({"_id": ObjectId(peticion_id)})
    if peticion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Petición no encontrada.",
        )
    return peticion


def _validar_camara_pir(camara_id: str, base_datos_personalizada: Database) -> None:
    """Comprueba que exista la cámara textual antes de aceptar un resultado PIR.

    Si no hay coincidencia en ``camaras``, detiene el flujo con HTTP 404.
    """
    if base_datos_personalizada.camaras.find_one({"_id": camara_id}) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe una cámara con el identificador indicado.")


@enrutador.post("/pir/error")
def registrar_error_captura_pir(
    resultado: CapturaPIRError,
    base_datos_personalizada: Database = Depends(obtener_base_datos),
) -> dict:
    """Conserva un fallo PIR aceptado, sin crear una entrada en ``peticiones``."""
    _validar_camara_pir(resultado.camara_id, base_datos_personalizada)
    ahora = datetime.now()
    evento = {
        "camara_id": resultado.camara_id,
        "fecha": ahora.strftime("%Y-%m-%d"),
        "hora": ahora.strftime("%H:%M:%S"),
        "tipo": resultado.tipo,
        "descripcion": "Captura automática detectada por sensor PIR.",
        "estado": "error",
        "mensaje_error": resultado.mensaje_error,
    }
    try:
        evento_id = base_datos_personalizada.eventos.insert_one(evento).inserted_id
        creado = base_datos_personalizada.eventos.find_one({"_id": evento_id})
        if creado is None:
            raise RuntimeError("MongoDB no devolvió el evento PIR creado.")
    except (PyMongoError, RuntimeError) as excepcion:
        registrador.exception("No se pudo registrar el error PIR: camara_id=%s", resultado.camara_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo registrar el error de captura PIR.") from excepcion
    return serializar_documento(creado)


@enrutador.post("/pir/archivo")
def recibir_captura_pir(
    camara_id: str = Form(...),
    tipo: str = Form(...),
    archivo: UploadFile = File(...),
    base_datos_personalizada: Database = Depends(obtener_base_datos),
) -> dict:
    """Persiste una captura PIR finalizada sin pasar por una petición pendiente.

    La ruta es necesaria porque las rutas históricas de archivo requieren un
    ``peticion_id`` pendiente. Mantiene el mismo orden seguro: metadato
    pendiente, subida B2 y confirmación final del archivo y su evento.
    """
    if tipo not in {"foto", "video"}:
        raise HTTPException(status_code=422, detail="El tipo de captura PIR no es válido.")
    _validar_camara_pir(camara_id, base_datos_personalizada)
    extension = (archivo.filename or "").lower().rsplit(".", 1)[-1]
    if extension not in ({"jpg", "jpeg"} if tipo == "foto" else {"mp4"}):
        raise HTTPException(status_code=422, detail="El tipo de archivo no coincide con la captura PIR.")

    ahora = datetime.now()
    tipo_archivo = "imagen" if tipo == "foto" else "video"
    contenido = "image/jpeg" if tipo_archivo == "imagen" else "video/mp4"
    evento = {
        "camara_id": camara_id,
        "fecha": ahora.strftime("%Y-%m-%d"),
        "hora": ahora.strftime("%H:%M:%S"),
        "tipo": tipo,
        "descripcion": "Captura automática detectada por sensor PIR.",
        "estado": "pendiente",
    }
    evento_id = None
    metadato = None
    try:
        evento_id = base_datos_personalizada.eventos.insert_one(evento).inserted_id
        clave = clave_objeto(camara_id, str(evento_id), archivo.filename or "captura", tipo_archivo)
        datos_archivo = {
            "id_camara": camara_id,
            "id_evento": str(evento_id),
            "tipo": tipo_archivo,
            "nombre_archivo": archivo.filename,
            "fecha_hora": ahora.strftime("%Y-%m-%d %H:%M:%S"),
            "clave_b2": clave,
            "estado_subida": "pendiente",
            "tipo_contenido": contenido,
        }
        archivo_id = base_datos_personalizada.archivos.insert_one(datos_archivo).inserted_id
        metadato = base_datos_personalizada.archivos.find_one({"_id": archivo_id})
        if metadato is None:
            raise RuntimeError("MongoDB no devolvió el metadato de la captura PIR.")
        subir_archivo(archivo.file, clave, contenido)
        confirmado = base_datos_personalizada.archivos.update_one({"_id": archivo_id}, {"$set": {"estado_subida": "confirmada"}})
        if confirmado.matched_count != 1:
            raise RuntimeError("No se pudo confirmar el archivo PIR en MongoDB.")
        evento_confirmado = base_datos_personalizada.eventos.update_one(
            {"_id": evento_id}, {"$set": {"estado": "ejecutado", "archivo_id": str(archivo_id)}}
        )
        if evento_confirmado.matched_count != 1:
            raise RuntimeError("No se pudo confirmar el evento PIR en MongoDB.")
        creado = base_datos_personalizada.eventos.find_one({"_id": evento_id})
        if creado is None:
            raise RuntimeError("No se pudo recuperar el evento PIR confirmado.")
        return serializar_documento(creado)
    except ErrorB2 as excepcion:
        # El archivo local sigue en la Raspberry; MongoDB refleja que B2 no lo
        # confirmó y el evento no se presenta como captura exitosa.
        try:
            if metadato is not None:
                base_datos_personalizada.archivos.update_one({"_id": metadato["_id"]}, {"$set": {"estado_subida": "error", "mensaje_error": str(excepcion)}})
            if evento_id is not None:
                base_datos_personalizada.eventos.update_one({"_id": evento_id}, {"$set": {"estado": "error", "mensaje_error": str(excepcion)}})
        except PyMongoError:
            registrador.exception("B2 falló y MongoDB no pudo registrar el error PIR.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(excepcion)) from excepcion
    except (PyMongoError, RuntimeError) as excepcion:
        registrador.exception("No se pudo persistir la captura PIR: camara_id=%s", camara_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo persistir la captura PIR.") from excepcion
    finally:
        archivo.file.close()


@enrutador.post("", response_model=PeticionRespuesta, status_code=status.HTTP_201_CREATED)
def crear_peticion(
    peticion: PeticionCrear,
    base_datos_personalizada: Database = Depends(obtener_base_datos),
) -> dict:
    """Crea una petición pendiente para una cámara y devuelve su documento.

    Para el origen PIR histórico también registra y vincula un evento antes de
    exponer la orden. Si falla la escritura, limpia sólo los documentos creados
    por esta llamada y responde HTTP 503.
    """
    # Verifica que la cámara exista antes de crear la solicitud. Las cámaras usan
    # IDs manuales como camara001, por eso se consulta _id como texto y no ObjectId.
    if base_datos_personalizada.camaras.find_one({"_id": peticion.camara_id}) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe una cámara con el identificador indicado.",
        )

    # La petición comienza como pendiente hasta que la Raspberry asociada la
    # reciba mediante consulta periódica y comunique un resultado final.
    datos = peticion.model_dump()
    datos["estado"] = "pendiente"
    ahora = datetime.now()
    datos["fecha_hora"] = ahora.strftime("%Y-%m-%d %H:%M:%S")

    evento_id = None
    peticion_creada_id = None
    try:
        # Una detección PIR es un evento real. Se registra antes de exponer la
        # orden para que la captura posterior pueda conservar ``id_evento``.
        if datos["origen"] == "pir":
            evento = {
                "camara_id": peticion.camara_id,
                "fecha": ahora.strftime("%Y-%m-%d"),
                "hora": ahora.strftime("%H:%M:%S"),
                "tipo": peticion.tipo,
                "descripcion": "Captura automática detectada por sensor PIR.",
                "estado": "pendiente",
            }
            evento_id = base_datos_personalizada.eventos.insert_one(evento).inserted_id
            datos["evento_id"] = str(evento_id)

        resultado = base_datos_personalizada.peticiones.insert_one(datos)
        peticion_creada_id = resultado.inserted_id
        if evento_id is not None:
            vinculo = base_datos_personalizada.eventos.update_one(
                {"_id": evento_id}, {"$set": {"peticion_id": str(resultado.inserted_id)}}
            )
            if vinculo.matched_count != 1:
                raise RuntimeError("No se pudo vincular el evento PIR con su petición.")
        creada = base_datos_personalizada.peticiones.find_one({"_id": resultado.inserted_id})
        if creada is None:
            raise RuntimeError("MongoDB no devolvió la petición creada.")
    except (PyMongoError, RuntimeError) as excepcion:
        # No se dejan registros PIR a medias si no pudo quedar disponible la
        # orden. La limpieza sólo afecta los IDs creados en esta misma llamada.
        if peticion_creada_id is not None:
            try:
                base_datos_personalizada.peticiones.delete_one({"_id": peticion_creada_id})
            except PyMongoError:
                registrador.exception("No se pudo limpiar una petición PIR sin evento vinculado.")
        if evento_id is not None:
            try:
                base_datos_personalizada.eventos.delete_one({"_id": evento_id})
            except PyMongoError:
                registrador.exception("No se pudo limpiar un evento PIR sin petición.")
        registrador.exception("No se pudo crear una petición: camara_id=%s", peticion.camara_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo registrar la petición en MongoDB. Intente nuevamente.",
        ) from excepcion
    return serializar_documento(creada)


@enrutador.get("", response_model=list[PeticionRespuesta])
def listar_peticiones(base_datos_personalizada: Database = Depends(obtener_base_datos)) -> list[dict]:
    """Devuelve el historial completo de peticiones desde la más reciente."""
    # Devuelve el historial de peticiones ordenado desde las más recientes.
    # No crea eventos ni modifica otra colección.
    peticiones = list(base_datos_personalizada.peticiones.find().sort("fecha_hora", -1))
    return serializar_documento(peticiones)


@enrutador.get("/pendientes/{camara_id}", response_model=PeticionRespuesta | None)
def obtener_peticion_pendiente(camara_id: str, base_datos_personalizada: Database = Depends(obtener_base_datos)) -> dict | None:
    """Devuelve la orden pendiente más antigua para la cámara indicada.

    La Raspberry consulta esta ruta en cada ciclo periódico; una cámara sin órdenes recibe
    ``None`` y no se modifica ninguna colección.
    """
    # Esta ruta HTTP la consulta una Raspberry concreta de forma periódica.
    # Devuelve solo la petición pendiente más antigua para respetar el orden en que
    # el panel de control solicitó las capturas y evitar que una cámara ejecute varias a la vez.
    peticion = base_datos_personalizada.peticiones.find_one(
        {"camara_id": camara_id, "estado": "pendiente"},
        sort=[("fecha_hora", 1)],
    )
    return serializar_documento(peticion) if peticion else None


@enrutador.get("/{peticion_id}", response_model=PeticionRespuesta)
def obtener_peticion(peticion_id: str, base_datos_personalizada: Database = Depends(obtener_base_datos)) -> dict:
    """Devuelve el detalle de una petición existente o responde HTTP 404."""
    # Consulta una petición puntual para mostrar detalle o confirmar estado desde
    # el panel de control.
    peticion = _obtener_peticion_o_404(peticion_id, base_datos_personalizada)
    return serializar_documento(peticion)


@enrutador.put("/{peticion_id}", response_model=PeticionRespuesta)
def actualizar_peticion(
    peticion_id: str,
    peticion: PeticionActualizar,
    base_datos_personalizada: Database = Depends(obtener_base_datos),
) -> dict:
    """Actualiza el estado permitido de una petición y devuelve su versión final."""
    # Primero se comprueba que la petición exista. El modelo Pydantic ya limita
    # estado a: pendiente, ejecutado o error.
    _obtener_peticion_o_404(peticion_id, base_datos_personalizada)

    # Actualiza únicamente el estado. No se permite cambiar cámara, tipo ni fecha
    # porque esos datos forman parte del historial de la solicitud original.
    base_datos_personalizada.peticiones.update_one(
        {"_id": ObjectId(peticion_id)},
        {"$set": {"estado": peticion.estado}},
    )
    actualizada = base_datos_personalizada.peticiones.find_one({"_id": ObjectId(peticion_id)})
    return serializar_documento(actualizada)


@enrutador.put("/{peticion_id}/resultado", response_model=PeticionRespuesta)
def registrar_resultado_peticion(
    peticion_id: str,
    resultado: PeticionResultado,
    base_datos_personalizada: Database = Depends(obtener_base_datos),
) -> dict:
    """Registra un fallo de captura o reconcilia un archivo ya confirmado.

    Un estado exitoso sin metadato confirmado se rechaza; la ruta de archivo es
    quien establece ese éxito. Los resultados tardíos sobre una petición ya
    resuelta producen HTTP 409, salvo la reconciliación idempotente del mismo
    archivo confirmado.
    """
    # La Raspberry llama esta ruta al finalizar una foto o video. Un reintento
    # tardío no puede sobrescribir el historial ya terminado con estado error.
    peticion = _obtener_peticion_o_404(peticion_id, base_datos_personalizada)
    # Si B2 y el metadato ya quedaron confirmados pero FastAPI perdió la
    # respuesta final, la Raspberry puede intentar comunicar un error. El
    # archivo confirmado es evidencia suficiente para reconciliar la petición
    # como ejecutada, sin sobrescribirlo por un falso estado de error.
    metadato_confirmado = base_datos_personalizada.archivos.find_one(
        {"peticion_id": peticion_id, "estado_subida": "confirmada"}
    )
    if peticion["estado"] == "ejecutado" and metadato_confirmado:
        try:
            # También repara el único paso que pudo quedar pendiente si la
            # actualización de la petición fue confirmada antes que la del
            # evento PIR, sin modificar la captura ni crear otro metadato.
            _actualizar_evento_relacionado(
                base_datos_personalizada,
                peticion,
                {"estado": "ejecutado", "archivo_id": str(metadato_confirmado["_id"])},
            )
        except (PyMongoError, RuntimeError) as excepcion:
            registrador.exception(
                "No se pudo reconciliar el evento de una captura confirmada: peticion_id=%s",
                peticion_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudo confirmar el evento asociado a la captura.",
            ) from excepcion
        return serializar_documento(peticion)

    if peticion["estado"] != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La petición ya fue resuelta y no puede registrar otro resultado.",
        )

    if metadato_confirmado:
        try:
            actualizada = _confirmar_peticion_con_archivo(
                base_datos_personalizada, peticion, peticion_id, metadato_confirmado
            )
        except (PyMongoError, RuntimeError) as excepcion:
            registrador.exception(
                "No se pudo reconciliar una captura confirmada: peticion_id=%s",
                peticion_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudo confirmar la captura ya subida en MongoDB.",
            ) from excepcion
        return serializar_documento(actualizada)

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

    try:
        actualizacion = base_datos_personalizada.peticiones.update_one(
            {"_id": ObjectId(peticion_id), "estado": "pendiente"}, {"$set": cambios}
        )
        if actualizacion.matched_count != 1:
            raise RuntimeError("La petición ya no estaba pendiente al registrar el error.")
        _actualizar_evento_relacionado(
            base_datos_personalizada, peticion, {"estado": "error", "mensaje_error": cambios["mensaje_error"]}
        )
        actualizada = base_datos_personalizada.peticiones.find_one({"_id": ObjectId(peticion_id)})
        if actualizada is None:
            raise RuntimeError("No se pudo recuperar la petición con error.")
    except (PyMongoError, RuntimeError) as excepcion:
        registrador.exception("No se pudo registrar el error de captura: peticion_id=%s", peticion_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo registrar el error de captura en MongoDB.",
        ) from excepcion
    return serializar_documento(actualizada)


@enrutador.post("/{peticion_id}/archivo", response_model=PeticionRespuesta)
def recibir_archivo_capturado(
    peticion_id: str,
    archivo: UploadFile = File(...),
    base_datos_personalizada: Database = Depends(obtener_base_datos),
) -> dict:
    """Recibe una captura ya guardada en SD, la sube a B2 y recién la confirma.

    La Raspberry nunca conoce las credenciales B2: conserva su copia local y usa
    este canal HTTP existente para transferir los bytes al servidor.
    """
    peticion = _obtener_peticion_o_404(peticion_id, base_datos_personalizada)
    if peticion["estado"] == "ejecutado":
        existente = base_datos_personalizada.archivos.find_one(
            {"peticion_id": peticion_id, "estado_subida": "confirmada"}
        )
        if existente:
            try:
                _actualizar_evento_relacionado(
                    base_datos_personalizada,
                    peticion,
                    {"estado": "ejecutado", "archivo_id": str(existente["_id"])},
                )
            except (PyMongoError, RuntimeError) as excepcion:
                registrador.exception(
                    "No se pudo reconciliar el evento de una captura confirmada: peticion_id=%s",
                    peticion_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="No se pudo confirmar el evento asociado a la captura.",
                ) from excepcion
            return serializar_documento(peticion)
        raise HTTPException(status_code=409, detail="La petición fue resuelta sin metadato confirmado.")
    if peticion["estado"] == "error":
        raise HTTPException(status_code=409, detail="La petición ya tiene un error registrado.")

    extension = (archivo.filename or "").lower().rsplit(".", 1)[-1]
    esperado = {"foto": {"jpg", "jpeg"}, "video": {"mp4"}}[peticion["tipo"]]
    if extension not in esperado:
        raise HTTPException(status_code=422, detail="El tipo de archivo no coincide con la petición.")

    tipo = "imagen" if peticion["tipo"] == "foto" else "video"
    contenido = "image/jpeg" if tipo == "imagen" else "video/mp4"
    clave = clave_objeto(
        peticion["camara_id"], peticion_id, archivo.filename or "captura", tipo
    )
    try:
        # Se guarda el metadato pendiente antes de subir. Así un fallo de
        # MongoDB no se confunde con uno de B2 ni deja un éxito falso.
        metadato = base_datos_personalizada.archivos.find_one({"peticion_id": peticion_id})
        if metadato is None:
            datos_archivo = {
                "id_camara": peticion["camara_id"],
                "peticion_id": peticion_id,
                "tipo": tipo,
                "nombre_archivo": archivo.filename,
                "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "clave_b2": clave,
                "estado_subida": "pendiente",
                "tipo_contenido": contenido,
            }
            if peticion.get("evento_id"):
                datos_archivo["id_evento"] = peticion["evento_id"]
            archivo_id = base_datos_personalizada.archivos.insert_one(datos_archivo).inserted_id
            metadato = base_datos_personalizada.archivos.find_one({"_id": archivo_id})
        if metadato is None:
            raise RuntimeError("MongoDB no devolvió el metadato de la captura.")
    except (PyMongoError, RuntimeError) as excepcion:
        registrador.exception("No se pudo guardar el metadato pendiente: peticion_id=%s", peticion_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo guardar el metadato de la captura en MongoDB.",
        ) from excepcion

    try:
        # La clave determinista conserva la idempotencia del flujo existente:
        # si la Raspberry repite el POST, B2 actualiza el mismo objeto.
        if metadato.get("estado_subida") != "confirmada":
            subir_archivo(archivo.file, metadato.get("clave_b2", clave), contenido)
    except ErrorB2 as excepcion:
        # El documento pendiente ya existe, por lo que el fallo de B2 puede
        # quedar reflejado sin esperar a que la Raspberry logre una segunda
        # llamada a /resultado. Así no se muestra como pendiente una carga que
        # el proveedor rechazó.
        try:
            archivo_error = base_datos_personalizada.archivos.update_one(
                {"_id": metadato["_id"]},
                {"$set": {"estado_subida": "error", "mensaje_error": str(excepcion)}},
            )
            if archivo_error.matched_count != 1:
                raise RuntimeError("No se pudo registrar el fallo de B2 en el metadato.")
            peticion_error = base_datos_personalizada.peticiones.update_one(
                {"_id": ObjectId(peticion_id), "estado": "pendiente"},
                {"$set": {"estado": "error", "mensaje_error": str(excepcion)}},
            )
            if peticion_error.matched_count != 1:
                raise RuntimeError("No se pudo registrar el fallo de B2 en la petición.")
            _actualizar_evento_relacionado(
                base_datos_personalizada, peticion, {"estado": "error", "mensaje_error": str(excepcion)}
            )
        except (PyMongoError, RuntimeError):
            registrador.exception(
                "B2 rechazó el archivo y MongoDB no pudo reflejar el fallo: peticion_id=%s",
                peticion_id,
            )
        registrador.warning("Fallo de B2 para peticion_id=%s", peticion_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(excepcion)
        ) from None
    finally:
        archivo.file.close()

    try:
        confirmado = base_datos_personalizada.archivos.update_one(
            {"_id": metadato["_id"]}, {"$set": {"estado_subida": "confirmada"}}
        )
        if confirmado.matched_count != 1:
            raise RuntimeError("No se pudo confirmar el metadato de la captura.")
        actualizada = _confirmar_peticion_con_archivo(
            base_datos_personalizada, peticion, peticion_id, metadato
        )
        return serializar_documento(actualizada)
    except (PyMongoError, RuntimeError) as excepcion:
        registrador.exception("B2 confirmó el archivo, pero MongoDB no terminó la confirmación: peticion_id=%s", peticion_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="B2 confirmó el archivo, pero MongoDB no pudo finalizar sus metadatos.",
        ) from excepcion
