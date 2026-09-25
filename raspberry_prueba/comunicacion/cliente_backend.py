"""Cliente HTTP pequeño para el flujo de peticiones de la Raspberry."""

from __future__ import annotations

import requests
from requests.exceptions import RequestException


class ErrorBackend(RuntimeError):
    """Error recuperable de comunicación que la interfaz muestra sin cerrarse."""


class ClienteBackend:
    """Consulta pedidos pendientes e informa resultados sin acceder a MongoDB."""

    def __init__(self, url_base: str, tiempo_espera: int = 5) -> None:
        self.url_base = url_base.rstrip("/")
        self.tiempo_espera = tiempo_espera
        self.sesion = requests.Session()

    def obtener_pendiente(self, camara_id: str) -> dict | None:
        # FastAPI filtra por cámara, de modo que cada dispositivo recibe solo las
        # solicitudes destinadas a su cámara asociada.
        return self._solicitud("get", f"/peticiones/pendientes/{camara_id}")

    def informar_resultado(
        self,
        peticion_id: str,
        estado: str,
        nombre_archivo: str | None = None,
        ruta_local: str | None = None,
        mensaje_error: str | None = None,
    ) -> dict:
        # El resultado se envía a FastAPI, que actualiza peticiones y crea el
        # registro correspondiente en archivos dentro de Ani_cam.
        return self._solicitud(
            "put",
            f"/peticiones/{peticion_id}/resultado",
            json={
                "estado": estado,
                "nombre_archivo": nombre_archivo,
                "ruta_local": ruta_local,
                "mensaje_error": mensaje_error,
            },
        )

    def _solicitud(self, metodo: str, ruta: str, **datos) -> dict | None:
        try:
            respuesta = self.sesion.request(
                metodo, f"{self.url_base}{ruta}", timeout=self.tiempo_espera, **datos
            )
            respuesta.raise_for_status()
            return respuesta.json() if respuesta.content else None
        except RequestException as exc:
            raise ErrorBackend(f"No se pudo comunicar con FastAPI: {exc}") from exc
