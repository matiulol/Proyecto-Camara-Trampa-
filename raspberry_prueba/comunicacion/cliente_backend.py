"""Cliente HTTP entre la Raspberry y los endpoints FastAPI de ANICAM.

La Raspberry nunca importa PyMongo ni usa la URI de MongoDB. Este cliente
implementa el límite de responsabilidades: consulta trabajo pendiente e informa
el resultado a FastAPI, que es quien persiste los cambios en ``Ani_cam``. El
recorrido normal es Raspberry -> FastAPI -> MongoDB; al consultar el resultado,
la respuesta vuelve como MongoDB -> FastAPI -> Raspberry en formato JSON.
"""

from __future__ import annotations

# requests implementa HTTP y RequestException unifica errores de conexión,
# tiempos de espera y respuestas inválidas que la interfaz puede recuperar.
import requests
from requests.exceptions import RequestException


class ErrorBackend(RuntimeError):
    """Error recuperable de red que la interfaz muestra sin cerrarse.

    Es una excepción propia para que la ventana pueda diferenciar una falla de
    FastAPI de un error de cámara y decidir que el siguiente polling reintente.
    """


class ClienteBackend:
    """Cliente de una API REST para la Raspberry, sin acceso directo a MongoDB.

    Una clase agrupa URL, tiempo de espera y sesión HTTP para que la interfaz no
    repita detalles de red en cada botón o temporizador. ``requests.Session``
    reutiliza conexiones HTTP durante el polling; esto reduce trabajo de red sin
    cambiar el protocolo ni los endpoints. FastAPI actúa como intermediario:
    valida peticiones, aplica las reglas del backend y es el único componente
    que conoce la base ``Ani_cam``.
    """

    def __init__(self, url_base: str, tiempo_espera: int = 5) -> None:
        """Guarda la dirección de FastAPI, el límite de espera y una sesión HTTP.

        ``url_base`` debe contener protocolo, IP alcanzable y prefijo de API;
        ``rstrip`` evita una doble barra al anexar rutas. ``tiempo_espera`` evita
        que una desconexión congele indefinidamente el hilo de la interfaz. La
        sesión se crea una vez y se reutiliza durante toda la aplicación.
        """
        self.url_base = url_base.rstrip("/")
        self.tiempo_espera = tiempo_espera
        # La sesión conserva conexiones reutilizables. No almacena peticiones de
        # la cámara ni reemplaza a FastAPI: sólo evita negociar una conexión TCP
        # nueva en cada consulta del polling.
        self.sesion = requests.Session()

    def cerrar(self) -> None:
        """Libera conexiones HTTP reutilizables cuando se cierra la aplicación.

        ``Session.close`` no modifica peticiones ni datos de FastAPI; solamente
        libera los adaptadores y sockets mantenidos para acelerar el polling.
        La ventana llama a este método durante su cierre ordenado.
        """
        self.sesion.close()

    def obtener_pendiente(self, camara_id: str) -> dict | None:
        """Obtiene mediante GET la petición pendiente más antigua de una cámara.

        GET significa «leer sin modificar»: la Raspberry consulta cada cierto
        tiempo (polling) si FastAPI tiene una orden pendiente para ``camara_id``.
        El identificador se incorpora a la ruta para que FastAPI filtre antes de
        responder; una Raspberry no debe ejecutar órdenes dirigidas a otra. La
        respuesta JSON se transforma en ``dict`` o es ``None`` si no hay trabajo.
        """
        return self._solicitud("get", f"/peticiones/pendientes/{camara_id}")

    def informar_resultado(
        self,
        peticion_id: str,
        estado: str,
        nombre_archivo: str | None = None,
        ruta_local: str | None = None,
        mensaje_error: str | None = None,
    ) -> dict:
        """Envía con PUT el resultado final de una captura a FastAPI.

        PUT expresa que se actualiza una petición existente, identificada por
        ``peticion_id``. El cuerpo ``json`` serializa los valores como JSON para
        que FastAPI los valide y actualice MongoDB. Si fue correcta se envían
        nombre y ruta local; si falló se envía el mensaje que permitirá distinguir
        el problema desde el Dashboard. FastAPI responde con el documento ya
        actualizado, que la interfaz usa para refrescar su tabla.
        """
        return self._solicitud(
            "put",
            f"/peticiones/{peticion_id}/resultado",
            # ``json=`` serializa el diccionario y agrega el encabezado adecuado
            # para que FastAPI lo interprete como cuerpo JSON de la petición.
            json={
                "estado": estado,
                "nombre_archivo": nombre_archivo,
                "ruta_local": ruta_local,
                "mensaje_error": mensaje_error,
            },
        )

    def _solicitud(self, metodo: str, ruta: str, **datos) -> dict | None:
        """Centraliza URL, tiempo de espera, JSON y conversión de errores.

        Recibe el verbo HTTP (``get`` o ``put``), una ruta y datos opcionales
        como el cuerpo JSON. ``request`` envía la solicitud y espera la respuesta
        hasta ``tiempo_espera``; ``raise_for_status`` convierte respuestas HTTP
        4xx/5xx en excepción, por ejemplo 404 si no existe una petición o 500 si
        FastAPI no puede procesarla. Las fallas de red y HTTP se convierten a
        ``ErrorBackend`` para que el temporizador de Qt pueda reintentar en el
        siguiente polling en lugar de finalizar la aplicación.
        """
        try:
            # ``Session.request`` permite centralizar GET y PUT en un solo
            # método. El tiempo de espera impide que una red caída congele la
            # interfaz para siempre.
            respuesta = self.sesion.request(
                metodo, f"{self.url_base}{ruta}", timeout=self.tiempo_espera, **datos
            )
            # Si FastAPI responde 2xx, la solicitud fue aceptada. Para 4xx/5xx
            # se lanza una excepción y se sigue el camino de manejo de errores.
            respuesta.raise_for_status()
            # Algunos PUT/GET pueden no traer cuerpo. En ese caso se devuelve
            # None, en lugar de intentar decodificar JSON inexistente.
            return respuesta.json() if respuesta.content else None
        except RequestException as exc:
            # La ventana conoce ErrorBackend, no los detalles de requests. Esta
            # traducción mantiene la biblioteca HTTP aislada de la interfaz.
            raise ErrorBackend(f"No se pudo comunicar con FastAPI: {exc}") from exc
