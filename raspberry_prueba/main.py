"""Punto de entrada de la prueba local de Camara Trampa para Raspberry Pi."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from almacenamiento.gestor_archivos import GestorArchivos
from camara.controlador_camara import ControladorCamara
from config import CAMARA_ID, PHOTO_SIZE, VIDEO_BITRATE
from interfaz.ventana_principal import VentanaPrincipal


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Camara Trampa")

    gestor = GestorArchivos(CAMARA_ID)
    controlador = ControladorCamara(PHOTO_SIZE, VIDEO_BITRATE)
    ventana = VentanaPrincipal(controlador, gestor)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
