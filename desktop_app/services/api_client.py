from __future__ import annotations

from config.settings import API_BASE_URL
import requests
from requests import Response
from requests.exceptions import ConnectionError, HTTPError, RequestException, Timeout


class ApiError(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str = API_BASE_URL, timeout: int = 8) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def iniciar_sesion(self, usuario: str, contrasena: str) -> dict:
        data = self._request(
            "post",
            "/autenticacion/iniciar-sesion",
            json={"usuario": usuario, "contraseña": contrasena},
        )
        return data["usuario"]

    def listar_camaras(self) -> list[dict]:
        return self._request("get", "/camaras")

    def crear_camara(self, datos: dict) -> dict:
        return self._request("post", "/camaras", json=datos)

    def obtener_camara(self, camara_id: str) -> dict:
        return self._request("get", f"/camaras/{camara_id}")

    def modificar_camara(self, camara_id: str, datos: dict) -> dict:
        return self._request("put", f"/camaras/{camara_id}", json=datos)

    def eliminar_camara(self, camara_id: str) -> dict:
        return self._request("delete", f"/camaras/{camara_id}")

    def listar_eventos(self) -> list[dict]:
        return self._request("get", "/eventos")

    def crear_evento(self, datos: dict) -> dict:
        return self._request("post", "/eventos", json=datos)

    def obtener_evento(self, evento_id: str) -> dict:
        return self._request("get", f"/eventos/{evento_id}")

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                timeout=self.timeout,
                **kwargs,
            )
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}
        except RequestException as exc:
            raise ApiError(self._mensaje_error(exc)) from exc

    def _mensaje_error(self, exc: RequestException) -> str:
        if isinstance(exc, (ConnectionError, Timeout)):
            return "No se pudo conectar con FastAPI. Verifica que el backend este iniciado."
        if isinstance(exc, HTTPError) and exc.response is not None:
            return self._mensaje_desde_respuesta(exc.response)
        return "No se pudo completar la accion."

    def _mensaje_desde_respuesta(self, response: Response) -> str:
        try:
            data = response.json()
        except ValueError:
            data = {}
        detail = data.get("detail") or data.get("mensaje") or data.get("message")
        if isinstance(detail, list):
            return "Revisa los datos ingresados."
        if detail:
            return str(detail)
        if response.status_code == 401:
            return "Usuario o contraseña incorrectos."
        if response.status_code == 404:
            return "No se encontro el registro solicitado."
        if response.status_code == 409:
            return "Ya existe un registro con esos datos."
        return "El servidor rechazo la solicitud."


def check_backend_connection() -> tuple[bool, str]:
    try:
        ApiClient().listar_camaras()
    except ApiError as exc:
        return False, str(exc)
    return True, "Backend conectado correctamente"
