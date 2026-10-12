"""Cliente HTTP del Dashboard para consumir la API FastAPI de ANICAM."""

from __future__ import annotations

# URL base del backend FastAPI, definida en un archivo de configuración para que
# la ventana principal no tenga rutas escritas directamente.
from config.settings import API_BASE_URL

# requests se usa como cliente HTTP simple para comunicar PySide6 con FastAPI.
import requests
from requests import Response
from requests.exceptions import ConnectionError, HTTPError, RequestException, Timeout


class ErrorApi(RuntimeError):
    # Excepción propia del dashboard. Convierte errores técnicos de requests en
    # mensajes claros que se pueden mostrar con QMessageBox.
    pass


class ClienteApi:
    """Encapsula las peticiones HTTP para no mezclar red con widgets PySide6.

    La interfaz usa esta composición en lugar de llamar a ``requests`` desde
    cada botón. Así timeout, rutas y conversión de errores permanecen uniformes.
    """
    def __init__(self, url_base: str = API_BASE_URL, tiempo_espera: int = 8) -> None:
        # Guarda la URL sin barra final para construir rutas consistentes.
        self.url_base = url_base.rstrip("/")
        # Tiempo máximo de espera por operación HTTP para que la interfaz no
        # quede bloqueada demasiado tiempo si FastAPI no responde.
        self.tiempo_espera = tiempo_espera
        # La sesión reutiliza conexiones HTTP mientras la app está abierta.
        self.sesion = requests.Session()

    def iniciar_sesion(self, usuario: str, contrasena: str) -> dict:
        # Envía credenciales al endpoint existente de autenticación. No se agrega
        # JWT en esta etapa porque el backend actual usa login básico.
        datos = self._solicitud(
            "post",
            "/autenticacion/iniciar-sesion",
            json={"usuario": usuario, "contraseña": contrasena},
        )
        return datos["usuario"]

    def listar_camaras(self) -> list[dict]:
        # Obtiene las cámaras para la pestaña Cámaras y también para el selector
        # usado al crear peticiones.
        return self._solicitud("get", "/camaras")

    def crear_camara(self, datos: dict) -> dict:
        # Crea una cámara con _id manual como camara001, respetando la colección
        # Ani_cam.camaras existente.
        return self._solicitud("post", "/camaras", json=datos)

    def obtener_camara(self, camara_id: str) -> dict:
        # Consulta una cámara puntual seleccionada en la tabla.
        return self._solicitud("get", f"/camaras/{camara_id}")

    def modificar_camara(self, camara_id: str, datos: dict) -> dict:
        # Envía cambios parciales de una cámara al backend.
        return self._solicitud("put", f"/camaras/{camara_id}", json=datos)

    def eliminar_camara(self, camara_id: str) -> dict:
        # Elimina una cámara desde la pestaña Cámaras. No toca eventos ni peticiones.
        return self._solicitud("delete", f"/camaras/{camara_id}")

    def crear_peticion(self, camara_id: str, tipo: str) -> dict:
        # Crea una petición en Ani_cam.peticiones. El backend completa estado
        # "pendiente" y fecha_hora para que todas las solicitudes nazcan igual.
        return self._solicitud(
            "post",
            "/peticiones",
            json={"camara_id": camara_id, "tipo": tipo},
        )

    def listar_peticiones(self) -> list[dict]:
        # Obtiene el historial de peticiones para mostrar estado y fecha/hora.
        return self._solicitud("get", "/peticiones")

    def obtener_peticion(self, peticion_id: str) -> dict:
        # Consulta una petición individual por su ObjectId serializado.
        return self._solicitud("get", f"/peticiones/{peticion_id}")

    def actualizar_peticion(self, peticion_id: str, estado: str) -> dict:
        # Actualiza solo el estado de una petición. Los estados válidos los
        # controla FastAPI: pendiente, ejecutado o error.
        return self._solicitud("put", f"/peticiones/{peticion_id}", json={"estado": estado})

    def listar_eventos(self) -> list[dict]:
        # Los eventos son solo consulta visual. El dashboard no tiene métodos
        # para crear, editar ni eliminar eventos.
        return self._solicitud("get", "/eventos")

    def obtener_evento(self, evento_id: str) -> dict:
        # Consulta un evento puntual existente en MongoDB para mostrar el detalle.
        return self._solicitud("get", f"/eventos/{evento_id}")

    def listar_archivos_camara(self, camara_id: str) -> list[dict]:
        return self._solicitud("get", f"/archivos/camara/{camara_id}")

    def listar_archivos_peticion(self, peticion_id: str) -> list[dict]:
        return self._solicitud("get", f"/archivos/peticion/{peticion_id}")

    def listar_archivos_evento(self, evento_id: str) -> list[dict]:
        return self._solicitud("get", f"/archivos/evento/{evento_id}")

    def enlace_visualizacion(self, archivo_id: str) -> dict:
        """Pide una URL B2 efímera solo al momento de abrir el archivo."""
        return self._solicitud("get", f"/archivos/{archivo_id}/visualizacion")

    def _solicitud(self, metodo: str, ruta: str, **argumentos) -> dict | list:
        # Envuelve todas las llamadas HTTP para centralizar timeout, armado de URL
        # y traducción de errores a mensajes entendibles.
        try:
            respuesta = self.sesion.request(
                metodo,
                f"{self.url_base}{ruta}",
                timeout=self.tiempo_espera,
                **argumentos,
            )
            respuesta.raise_for_status()
            if respuesta.content:
                return respuesta.json()
            return {}
        except RequestException as exc:
            raise ErrorApi(self._mensaje_error(exc)) from exc

    def _mensaje_error(self, exc: RequestException) -> str:
        # Traduce fallas de conexión o errores HTTP a textos en español para
        # mantener la interfaz clara para el usuario.
        if isinstance(exc, (ConnectionError, Timeout)):
            return "No se pudo conectar con FastAPI. Verifica que el backend este iniciado."
        if isinstance(exc, HTTPError) and exc.response is not None:
            return self._mensaje_desde_respuesta(exc.response)
        return "No se pudo completar la accion."

    def _mensaje_desde_respuesta(self, respuesta: Response) -> str:
        # FastAPI suele devolver {"detail": "..."}. Esta función extrae ese texto
        # y agrega mensajes por defecto para códigos frecuentes.
        try:
            datos = respuesta.json()
        except ValueError:
            datos = {}
        detalle = datos.get("detail") or datos.get("mensaje") or datos.get("message")
        if isinstance(detalle, list):
            return "Revisa los datos ingresados."
        if detalle:
            return str(detalle)
        if respuesta.status_code == 401:
            return "Usuario o contraseña incorrectos."
        if respuesta.status_code == 404:
            return "No se encontro el registro solicitado."
        if respuesta.status_code == 409:
            return "Ya existe un registro con esos datos."
        return "El servidor rechazo la solicitud."


def comprobar_conexion_backend() -> tuple[bool, str]:
    """Comprueba conectividad consultando un endpoint que requiere MongoDB."""
    try:
        ClienteApi().listar_camaras()
    except ErrorApi as exc:
        return False, str(exc)
    return True, "Backend conectado correctamente"
