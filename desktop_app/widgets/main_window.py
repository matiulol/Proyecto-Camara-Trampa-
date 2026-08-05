from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.api_client import check_backend_connection


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Camara Trampa")
        self.setMinimumSize(420, 240)

        title = QLabel("Camara Trampa")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")

        description = QLabel(
            "Primera version de la aplicacion para monitoreo con camaras trampa."
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)

        self.result_label = QLabel("Estado: sin comprobar")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.check_button = QPushButton("Comprobar conexion")
        self.check_button.clicked.connect(self.check_connection)

        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addSpacing(12)
        layout.addWidget(self.check_button)
        layout.addWidget(self.result_label)
        layout.addStretch()

        self.setLayout(layout)

    def check_connection(self):
        ok, message = check_backend_connection()
        self.result_label.setText(message)
        self.result_label.setStyleSheet(
            "color: #18794e;" if ok else "color: #b42318;"
        )
