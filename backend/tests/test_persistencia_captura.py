"""Pruebas unitarias del orden de persistencia de una captura."""
from io import BytesIO
import unittest
from unittest.mock import patch

from bson import ObjectId
from services.servicio_b2 import ErrorB2
from models.schemas import PeticionCrear, PeticionResultado
from routers.peticiones import (
    _actualizar_evento_relacionado,
    crear_peticion,
    obtener_peticion_pendiente,
    registrar_resultado_peticion,
    recibir_archivo_capturado,
)


class Resultado:
    def __init__(self, matched_count=1, inserted_id=None):
        self.matched_count, self.inserted_id = matched_count, inserted_id


class Coleccion:
    def __init__(self, documentos=()):
        self.documentos = list(documentos)

    @staticmethod
    def _coincide(documento, filtro):
        return all(documento.get(campo) == valor for campo, valor in filtro.items())

    def find_one(self, filtro, sort=None):
        return next((d for d in self.documentos if self._coincide(d, filtro)), None)

    def insert_one(self, documento):
        copia = dict(documento)
        copia["_id"] = ObjectId()
        self.documentos.append(copia)
        return Resultado(inserted_id=copia["_id"])

    def update_one(self, filtro, actualizacion):
        documento = self.find_one(filtro)
        if not documento:
            return Resultado(0)
        documento.update(actualizacion["$set"])
        return Resultado(1)


class BaseFalsa:
    def __init__(self, peticion):
        self.camaras = Coleccion([{"_id": peticion["camara_id"]}])
        self.peticiones = Coleccion([peticion])
        self.archivos = Coleccion()
        self.eventos = Coleccion()


class ArchivoFalso:
    filename = "captura.jpg"

    def __init__(self):
        self.file = BytesIO(b"jpeg de prueba")


class VideoFalso(ArchivoFalso):
    filename = "captura.mp4"


class PersistenciaCapturaTests(unittest.TestCase):
    def setUp(self):
        self.peticion_id = ObjectId()
        self.peticion = {
            "_id": self.peticion_id, "camara_id": "camara001", "tipo": "foto",
            "estado": "pendiente",
        }

    def test_registra_y_confirma_metadato_antes_de_devolver_exito(self):
        base = BaseFalsa(self.peticion)
        with patch("routers.peticiones.subir_archivo") as subir:
            respuesta = recibir_archivo_capturado(str(self.peticion_id), ArchivoFalso(), base)

        self.assertEqual(respuesta["estado"], "ejecutado")
        self.assertEqual(base.archivos.documentos[0]["id_camara"], "camara001")
        self.assertEqual(base.archivos.documentos[0]["tipo"], "imagen")
        self.assertEqual(base.archivos.documentos[0]["estado_subida"], "confirmada")
        self.assertEqual(base.peticiones.documentos[0]["archivo_id"], str(base.archivos.documentos[0]["_id"]))
        subir.assert_called_once()

    def test_no_sube_si_falla_el_metadato_previo(self):
        base = BaseFalsa(self.peticion)
        base.archivos.insert_one = lambda _documento: (_ for _ in ()).throw(RuntimeError("mongo caído"))
        with patch("routers.peticiones.subir_archivo") as subir, patch(
            "routers.peticiones.logger.exception"
        ):
            with self.assertRaisesRegex(Exception, "No se pudo guardar el metadato"):
                recibir_archivo_capturado(str(self.peticion_id), ArchivoFalso(), base)
        subir.assert_not_called()
        self.assertEqual(base.peticiones.documentos[0]["estado"], "pendiente")

    def test_reintento_reutiliza_un_metadato_sin_duplicarlo(self):
        base = BaseFalsa(self.peticion)
        with patch("routers.peticiones.subir_archivo"):
            recibir_archivo_capturado(str(self.peticion_id), ArchivoFalso(), base)
        # Una respuesta HTTP perdida puede repetir la misma carga; la petición
        # ya confirmada retorna su estado y no inserta otro documento.
        with patch("routers.peticiones.subir_archivo") as subir:
            respuesta = recibir_archivo_capturado(str(self.peticion_id), ArchivoFalso(), base)
        self.assertEqual(respuesta["estado"], "ejecutado")
        self.assertEqual(len(base.archivos.documentos), 1)
        subir.assert_not_called()

    def test_registra_video_con_metadato_y_tipo_correctos(self):
        self.peticion["tipo"] = "video"
        base = BaseFalsa(self.peticion)
        with patch("routers.peticiones.subir_archivo") as subir:
            respuesta = recibir_archivo_capturado(str(self.peticion_id), VideoFalso(), base)

        self.assertEqual(respuesta["estado"], "ejecutado")
        self.assertEqual(base.archivos.documentos[0]["tipo"], "video")
        self.assertEqual(base.archivos.documentos[0]["tipo_contenido"], "video/mp4")
        subir.assert_called_once()

    def test_reintento_confirma_peticion_si_b2_ya_subio_el_archivo(self):
        """Un fallo posterior a B2 se recupera sin subir ni duplicar el archivo."""
        base = BaseFalsa(self.peticion)
        actualizar_original = base.peticiones.update_one
        base.peticiones.update_one = lambda _filtro, _cambios: Resultado(0)

        with patch("routers.peticiones.subir_archivo") as primera_subida, patch(
            "routers.peticiones.logger.exception"
        ):
            with self.assertRaisesRegex(Exception, "MongoDB no pudo finalizar"):
                recibir_archivo_capturado(str(self.peticion_id), ArchivoFalso(), base)

        self.assertEqual(base.archivos.documentos[0]["estado_subida"], "confirmada")
        self.assertEqual(base.peticiones.documentos[0]["estado"], "pendiente")
        primera_subida.assert_called_once()

        base.peticiones.update_one = actualizar_original
        with patch("routers.peticiones.subir_archivo") as reintento_subida:
            respuesta = recibir_archivo_capturado(str(self.peticion_id), ArchivoFalso(), base)

        self.assertEqual(respuesta["estado"], "ejecutado")
        self.assertEqual(len(base.archivos.documentos), 1)
        reintento_subida.assert_not_called()

    def test_resultado_error_reconcilia_archivo_ya_confirmado(self):
        """Un error de respuesta no degrada una captura B2 ya comprobada."""
        base = BaseFalsa(self.peticion)
        archivo_id = ObjectId()
        base.archivos.documentos.append(
            {
                "_id": archivo_id,
                "peticion_id": str(self.peticion_id),
                "nombre_archivo": "captura.jpg",
                "estado_subida": "confirmada",
            }
        )

        respuesta = registrar_resultado_peticion(
            str(self.peticion_id),
            PeticionResultado(estado="error", mensaje_error="respuesta perdida"),
            base,
        )

        self.assertEqual(respuesta["estado"], "ejecutado")
        self.assertEqual(respuesta["archivo_id"], str(archivo_id))
        self.assertNotIn("mensaje_error", respuesta)

    def test_reintento_de_resultado_ejecutado_repara_evento_pir(self):
        """Una respuesta perdida no degrada la petición ni duplica el archivo."""
        evento_id = ObjectId()
        archivo_id = ObjectId()
        self.peticion.update(
            {"estado": "ejecutado", "evento_id": str(evento_id), "archivo_id": str(archivo_id)}
        )
        base = BaseFalsa(self.peticion)
        base.eventos = Coleccion([{"_id": evento_id, "estado": "pendiente"}])
        base.archivos.documentos.append(
            {
                "_id": archivo_id,
                "peticion_id": str(self.peticion_id),
                "nombre_archivo": "captura.jpg",
                "estado_subida": "confirmada",
            }
        )

        respuesta = registrar_resultado_peticion(
            str(self.peticion_id),
            PeticionResultado(estado="error", mensaje_error="la respuesta se perdió"),
            base,
        )

        self.assertEqual(respuesta["estado"], "ejecutado")
        self.assertEqual(len(base.archivos.documentos), 1)
        self.assertEqual(base.eventos.documentos[0]["estado"], "ejecutado")
        self.assertEqual(base.eventos.documentos[0]["archivo_id"], str(archivo_id))

    def test_peticion_pir_crea_evento_vinculado_y_queda_pendiente(self):
        base = BaseFalsa(self.peticion)
        base.peticiones = Coleccion()
        creada = crear_peticion(
            PeticionCrear(camara_id="camara001", tipo="foto", origen="pir"), base
        )

        pendiente = obtener_peticion_pendiente("camara001", base)
        self.assertEqual(creada["estado"], "pendiente")
        self.assertEqual(pendiente["_id"], creada["_id"])
        self.assertEqual(len(base.eventos.documentos), 1)
        self.assertEqual(
            base.eventos.documentos[0]["peticion_id"], creada["_id"]
        )

    def test_fallo_de_b2_deja_archivo_y_peticion_en_error(self):
        evento_id = ObjectId()
        self.peticion["evento_id"] = str(evento_id)
        base = BaseFalsa(self.peticion)
        base.eventos = Coleccion([{"_id": evento_id, "estado": "pendiente"}])
        with patch(
            "routers.peticiones.subir_archivo", side_effect=ErrorB2("B2 no disponible")
        ):
            with self.assertRaisesRegex(Exception, "B2 no disponible"):
                recibir_archivo_capturado(str(self.peticion_id), ArchivoFalso(), base)

        self.assertEqual(base.archivos.documentos[0]["estado_subida"], "error")
        self.assertEqual(base.archivos.documentos[0]["mensaje_error"], "B2 no disponible")
        self.assertEqual(base.peticiones.documentos[0]["estado"], "error")
        self.assertEqual(base.eventos.documentos[0]["estado"], "error")

    def test_actualiza_el_evento_pir_relacionado(self):
        evento_id = ObjectId()
        base = BaseFalsa(self.peticion)
        base.eventos = Coleccion([{"_id": evento_id, "estado": "pendiente"}])
        _actualizar_evento_relacionado(
            base, {"evento_id": str(evento_id)}, {"estado": "ejecutado", "archivo_id": "archivo-1"}
        )
        self.assertEqual(base.eventos.documentos[0]["estado"], "ejecutado")
        self.assertEqual(base.eventos.documentos[0]["archivo_id"], "archivo-1")


if __name__ == "__main__":
    unittest.main()
