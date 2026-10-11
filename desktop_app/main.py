"""Punto de entrada del Dashboard PySide6 de ANICAM."""

import sys

from PySide6.QtWidgets import QApplication

from widgets.ventana_principal import VentanaPrincipal


def iniciar_aplicacion() -> int:
    """Crea la aplicación Qt, aplica el estilo y muestra la ventana principal.

    ``QApplication`` es el objeto que administra el ciclo de eventos, ventanas
    y señales de PySide6. El Dashboard no inicia FastAPI: se conecta al backend
    ya disponible mediante el cliente HTTP de la ventana.
    """
    # QApplication debe existir antes de crear cualquier widget: centraliza el
    # ciclo de eventos, las señales y los recursos compartidos de Qt. ``argv``
    # permite a Qt procesar sus opciones de línea de comandos si las hubiera.
    aplicacion = QApplication(sys.argv)

    # La hoja de estilos es una configuración global: los selectores se aplican
    # a los widgets creados por VentanaPrincipal sin acoplar el diseño visual a
    # cada método de la interfaz.
    aplicacion.setStyleSheet(
        """
        QWidget { font-family: Segoe UI, Arial; font-size: 13px; }
        QLineEdit, QComboBox, QTextEdit, QDateEdit, QTimeEdit {
            padding: 6px;
            border: 1px solid #b8c4bd;
            border-radius: 4px;
        }
        QPushButton {
            padding: 7px 12px;
            border: 1px solid #597267;
            border-radius: 4px;
            background: #eef5f1;
        }
        QPushButton:hover { background: #dfece6; }
        QTableWidget { gridline-color: #d6ded9; selection-background-color: #cfe3d8; }
        """
    )
    # VentanaPrincipal hereda de QMainWindow y, por composición, crea su
    # ClienteApi para comunicarse con FastAPI. El punto de entrada sólo arma
    # esos objetos; no contiene reglas del Dashboard ni llamadas HTTP.
    ventana = VentanaPrincipal()
    ventana.show()

    # ``exec`` entrega el control al ciclo de eventos hasta que se cierren las
    # ventanas. Su código de salida se devuelve al sistema operativo para que
    # el cierre de la aplicación sea ordenado y verificable desde una terminal.
    return aplicacion.exec()


if __name__ == "__main__":
    # SystemExit conserva el código devuelto por Qt como código del proceso.
    raise SystemExit(iniciar_aplicacion())
