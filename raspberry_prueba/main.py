"""Punto de entrada de la prueba local de Camara Trampa para Raspberry Pi."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from almacenamiento.gestor_archivos import GestorArchivos
from camara.controlador_camara import ControladorCamara
from comunicacion.cliente_backend import ClienteBackend
from config import CAMARA_ID, DURACION_VIDEO_SEGUNDOS, INTERVALO_CONSULTA_MS, PHOTO_SIZE, URL_BACKEND, VIDEO_BITRATE
from interfaz.ventana_principal import VentanaPrincipal


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Camara Trampa")

    gestor = GestorArchivos(CAMARA_ID)
    controlador = ControladorCamara(PHOTO_SIZE, VIDEO_BITRATE)
    # La URL y el identificador se leen desde configuración para que el mismo
    # programa pueda instalarse en otras Raspberry sin editar esta función.
    cliente = ClienteBackend(URL_BACKEND)
    ventana = VentanaPrincipal(controlador, gestor, cliente, INTERVALO_CONSULTA_MS, DURACION_VIDEO_SEGUNDOS)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
