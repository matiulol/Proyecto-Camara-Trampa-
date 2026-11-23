"""Cliente HTTP del Panel de control para consumir la API FastAPI de ANICAM."""

from __future__ import annotations

# URL base del servidor FastAPI, definida en un archivo de configuración para que
# la ventana principal no tenga rutas escritas directamente.
from configuracion.ajustes import URL_BASE_API

# requests se usa como cliente HTTP simple para comunicar PySide6 con FastAPI.
import requests
from requests import Response
from requests.exceptions import ConnectionError, HTTPError, RequestException, Timeout


class ErrorAPI(RuntimeError):
    """Error de comunicación que la interfaz puede presentar al usuario."""
    # Excepción propia del panel de control. Convierte errores técnicos de requests en
    # mensajes claros que se pueden mostrar con QMessageBox.
    pass


class ClienteAPI:
    """Encapsula las peticiones HTTP para no mezclar red con controles PySide6.

    La interfaz usa esta composición en lugar de llamar a ``requests`` desde
    cada botón. Así tiempo de espera, rutas y conversión de errores permanecen uniformes.
    """
    def __init__(self, url_base: str = URL_BASE_API, tiempo_espera: int = 8) -> None:
        """Configura la URL base, el tiempo de espera y una sesión HTTP reutilizable.

        ``url_base`` debe incluir el prefijo de API vigente; no se valida hasta
        que una operación realiza una solicitud.
        """
        # Guarda la URL sin barra final para construir rutas consistentes.
        self.url_base = url_base.rstrip("/")
        # Tiempo máximo de espera por operación HTTP para que la interfaz no
        # quede bloqueada demasiado tiempo si FastAPI no responde.
        self.tiempo_espera = tiempo_espera
        # La sesión reutiliza conexiones HTTP mientras la app está abierta.
        self.sesion = requests.Session()

    def cerrar(self) -> None:
        """Libera conexiones HTTP al cerrar definitivamente el Panel de control.

        La sesión principal vive durante toda la ventana para reutilizar sus
        conexiones; cerrarla aquí evita dejar adaptadores y sockets abiertos al
        finalizar la aplicación. No modifica datos ni solicitudes de FastAPI.
        """
        self.sesion.close()

    def iniciar_sesion(self, usuario: str, contrasena: str) -> dict:
        """Envía el inicio de sesión y devuelve el objeto público de usuario."""
        # Envía credenciales al ruta HTTP existente de autenticación. No se agrega
        # JWT en esta etapa porque el servidor actual usa inicio de sesión básico.
        datos = self._solicitud(
            "post",
            "/autenticacion/iniciar-sesion",
            json={"usuario": usuario, "contraseña": contrasena},
        )
        return datos["usuario"]

    def listar_camaras(self) -> list[dict]:
        """Obtiene las cámaras registradas para tablas y selectores."""
        # Obtiene las cámaras para la pestaña Cámaras y también para el selector
        # usado al crear peticiones.
        return self._solicitud("get", "/camaras")

    def crear_camara(self, datos: dict) -> dict:
        """Envía al servidor los campos validados para crear una cámara."""
        # Crea una cámara con _id manual como camara001, respetando la colección
        # Ani_cam.camaras existente.
        return self._solicitud("post", "/camaras", json=datos)

    def obtener_camara(self, camara_id: str) -> dict:
        """Consulta los datos actuales de una cámara identificada por texto."""
        # Consulta una cámara puntual seleccionada en la tabla.
        return self._solicitud("get", f"/camaras/{camara_id}")

    def modificar_camara(self, camara_id: str, datos: dict) -> dict:
        """Envía los campos editados para actualizar una cámara existente."""
        # Envía cambios parciales de una cámara al servidor.
        return self._solicitud("put", f"/camaras/{camara_id}", json=datos)

    def eliminar_camara(self, camara_id: str) -> dict:
        """Solicita la eliminación de una cámara sin alterar sus historiales."""
        # Elimina una cámara desde la pestaña Cámaras. No toca eventos ni peticiones.
        return self._solicitud("delete", f"/camaras/{camara_id}")

    def crear_peticion(self, camara_id: str, tipo: str) -> dict:
        """Crea una petición manual de foto o video para una cámara."""
        # Crea una petición en Ani_cam.peticiones. El servidor completa estado
        # "pendiente" y fecha_hora para que todas las solicitudes nazcan igual.
        return self._solicitud(
            "post",
            "/peticiones",
            json={"camara_id": camara_id, "tipo": tipo},
        )

    def listar_peticiones(self) -> list[dict]:
        """Obtiene el historial de peticiones que presenta el Panel de control."""
        # Obtiene el historial de peticiones para mostrar estado y fecha/hora.
        return self._solicitud("get", "/peticiones")

    def obtener_peticion(self, peticion_id: str) -> dict:
        """Consulta una petición por su identificador BSON serializado."""
        # Consulta una petición individual por su ObjectId serializado.
        return self._solicitud("get", f"/peticiones/{peticion_id}")

    def actualizar_peticion(self, peticion_id: str, estado: str) -> dict:
        """Solicita el cambio de estado permitido para una petición existente."""
        # Actualiza solo el estado de una petición. Los estados válidos los
        # controla FastAPI: pendiente, ejecutado o error.
        return self._solicitud("put", f"/peticiones/{peticion_id}", json={"estado": estado})

    def listar_eventos(self) -> list[dict]:
        """Obtiene los eventos existentes para la pestaña de historial."""
        # Los eventos son solo consulta visual. El panel de control no tiene métodos
        # para crear, editar ni eliminar eventos.
        return self._solicitud("get", "/eventos")

    def obtener_evento(self, evento_id: str) -> dict:
        """Consulta un evento puntual por su identificador BSON serializado."""
        # Consulta un evento puntual existente en MongoDB para mostrar el detalle.
        return self._solicitud("get", f"/eventos/{evento_id}")

    def listar_archivos_camara(self, camara_id: str) -> list[dict]:
        """Lista metadatos de captura asociados a una cámara."""
        return self._solicitud("get", f"/archivos/camara/{camara_id}")

    def listar_archivos_peticion(self, peticion_id: str) -> list[dict]:
        """Lista metadatos asociados a una petición manual o histórica."""
        return self._solicitud("get", f"/archivos/peticion/{peticion_id}")

    def listar_archivos_evento(self, evento_id: str) -> list[dict]:
        """Lista los archivos asociados a un evento, incluidos eventos PIR."""
        return self._solicitud("get", f"/archivos/evento/{evento_id}")

    def enlace_visualizacion(self, archivo_id: str) -> dict:
        """Pide una URL B2 efímera solo al momento de abrir el archivo."""
        return self._solicitud("get", f"/archivos/{archivo_id}/visualizacion")

    def _solicitud(self, metodo: str, ruta: str, **argumentos) -> dict | list:
        """Ejecuta una llamada HTTP y convierte fallos de red en ``ErrorAPI``.

        El método recibe el verbo, la ruta relativa a la API y los argumentos
        admitidos por ``requests``; devuelve JSON o un diccionario vacío si la
        respuesta no tiene contenido.
        """
        # Envuelve todas las llamadas HTTP para centralizar tiempo de espera, armado de URL
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
        except RequestException as excepcion:
            raise ErrorAPI(self._mensaje_error(excepcion)) from excepcion

    def _mensaje_error(self, excepcion: RequestException) -> str:
        """Selecciona un mensaje en español según el tipo de error HTTP o de red."""
        # Traduce fallas de conexión o errores HTTP a textos en español para
        # mantener la interfaz clara para el usuario.
        if isinstance(excepcion, (ConnectionError, Timeout)):
            return "No se pudo conectar con FastAPI. Verifica que el servidor esté iniciado."
        if isinstance(excepcion, HTTPError) and excepcion.response is not None:
            return self._mensaje_desde_respuesta(excepcion.response)
        return "No se pudo completar la acción."

    def _mensaje_desde_respuesta(self, respuesta: Response) -> str:
        """Extrae el detalle FastAPI o aplica un mensaje para estados comunes."""
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
            return "No se encontró el registro solicitado."
        if respuesta.status_code == 409:
            return "Ya existe un registro con esos datos."
        return "El servidor rechazó la solicitud."


def comprobar_conexion_servidor() -> tuple[bool, str]:
    """Comprueba la conectividad con el servidor mediante una ruta que requiere MongoDB."""
    cliente = ClienteAPI()
    try:
        cliente.listar_camaras()
    except ErrorAPI as excepcion:
        return False, str(excepcion)
    finally:
        # Esta comprobación crea una sesión temporal, a diferencia de la sesión
        # que conserva la ventana durante toda su vida útil.
        cliente.cerrar()
    return True, "Servidor conectado correctamente"
