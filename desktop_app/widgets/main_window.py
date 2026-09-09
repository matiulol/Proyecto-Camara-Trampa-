from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from services.api_client import ApiClient, ApiError


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.api = ApiClient()
        self.usuario_actual: dict | None = None
        self.camaras: list[dict] = []
        self.eventos: list[dict] = []
        self.setWindowTitle("Camara Trampa Inteligente")
        self.setMinimumSize(960, 620)
        self._mostrar_login()

    def _mostrar_login(self) -> None:
        pantalla = QWidget()
        pantalla.setObjectName("login")
        layout = QVBoxLayout(pantalla)
        layout.setContentsMargins(80, 80, 80, 80)

        title = QLabel("Camara Trampa Inteligente")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")

        self.usuario_input = QLineEdit()
        self.usuario_input.setPlaceholderText("Usuario")
        self.usuario_input.setText("admin")

        self.contrasena_input = QLineEdit()
        self.contrasena_input.setPlaceholderText("Contraseña")
        self.contrasena_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.contrasena_input.setText("admin123")
        self.contrasena_input.returnPressed.connect(self._iniciar_sesion)

        boton = QPushButton("Iniciar sesion")
        boton.clicked.connect(self._iniciar_sesion)

        layout.addStretch()
        layout.addWidget(title)
        layout.addSpacing(18)
        layout.addWidget(QLabel("Usuario"))
        layout.addWidget(self.usuario_input)
        layout.addWidget(QLabel("Contraseña"))
        layout.addWidget(self.contrasena_input)
        layout.addSpacing(12)
        layout.addWidget(boton)
        layout.addStretch()
        self.setCentralWidget(pantalla)

    def _iniciar_sesion(self) -> None:
        try:
            self.usuario_actual = self.api.iniciar_sesion(
                self.usuario_input.text().strip(),
                self.contrasena_input.text(),
            )
        except ApiError as exc:
            QMessageBox.warning(self, "Inicio de sesion", str(exc))
            return
        self._mostrar_dashboard()

    def _mostrar_dashboard(self) -> None:
        contenedor = QWidget()
        layout = QVBoxLayout(contenedor)

        encabezado = QHBoxLayout()
        usuario = self.usuario_actual or {}
        titulo = QLabel(f"Dashboard - {usuario.get('usuario', '')}")
        titulo.setStyleSheet("font-size: 22px; font-weight: bold;")
        cerrar = QPushButton("Cerrar sesion")
        cerrar.clicked.connect(self._cerrar_sesion)
        encabezado.addWidget(titulo)
        encabezado.addStretch()
        encabezado.addWidget(cerrar)
        layout.addLayout(encabezado)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._crear_tab_camaras(), "Camaras")
        self.tabs.addTab(self._crear_tab_eventos(), "Eventos")
        layout.addWidget(self.tabs)
        self.setCentralWidget(contenedor)
        self.refrescar_todo()

    def _crear_tab_camaras(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        botones = QHBoxLayout()
        agregar = QPushButton("Agregar camara")
        consultar = QPushButton("Consultar camara")
        editar = QPushButton("Editar camara")
        eliminar = QPushButton("Eliminar camara")
        actualizar = QPushButton("Actualizar")
        agregar.clicked.connect(self._agregar_camara)
        consultar.clicked.connect(self._consultar_camara)
        editar.clicked.connect(self._editar_camara)
        eliminar.clicked.connect(self._eliminar_camara)
        actualizar.clicked.connect(self.refrescar_camaras)
        for boton in (agregar, consultar, editar, eliminar, actualizar):
            botones.addWidget(boton)
        botones.addStretch()

        self.tabla_camaras = QTableWidget(0, 5)
        self.tabla_camaras.setHorizontalHeaderLabels(
            ["ID", "Nombre", "Ubicacion", "Estado", "Fecha de instalacion"]
        )
        self._configurar_tabla(self.tabla_camaras)

        layout.addLayout(botones)
        layout.addWidget(self.tabla_camaras)
        return tab

    def _crear_tab_eventos(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        botones = QHBoxLayout()
        agregar = QPushButton("Agregar evento")
        consultar = QPushButton("Consultar evento")
        actualizar = QPushButton("Actualizar")
        agregar.clicked.connect(self._agregar_evento)
        consultar.clicked.connect(self._consultar_evento)
        actualizar.clicked.connect(self.refrescar_eventos)
        for boton in (agregar, consultar, actualizar):
            botones.addWidget(boton)
        botones.addStretch()

        self.tabla_eventos = QTableWidget(0, 7)
        self.tabla_eventos.setHorizontalHeaderLabels(
            ["ID", "Camara", "Fecha", "Hora", "Tipo", "Descripcion", "Estado"]
        )
        self._configurar_tabla(self.tabla_eventos)

        layout.addLayout(botones)
        layout.addWidget(self.tabla_eventos)
        return tab

    def _configurar_tabla(self, tabla: QTableWidget) -> None:
        tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabla.horizontalHeader().setStretchLastSection(True)

    def refrescar_todo(self) -> None:
        self.refrescar_camaras()
        self.refrescar_eventos()

    def refrescar_camaras(self) -> None:
        try:
            self.camaras = self.api.listar_camaras()
        except ApiError as exc:
            QMessageBox.warning(self, "Camaras", str(exc))
            return
        self.tabla_camaras.setRowCount(len(self.camaras))
        for fila, camara in enumerate(self.camaras):
            valores = [
                camara.get("_id", ""),
                camara.get("nombre", ""),
                camara.get("ubicacion", ""),
                camara.get("estado", ""),
                camara.get("fecha_instalacion", ""),
            ]
            self._llenar_fila(self.tabla_camaras, fila, valores, camara)

    def refrescar_eventos(self) -> None:
        try:
            if not self.camaras:
                self.camaras = self.api.listar_camaras()
            self.eventos = self.api.listar_eventos()
        except ApiError as exc:
            QMessageBox.warning(self, "Eventos", str(exc))
            return

        nombres_camaras = {camara["_id"]: camara["nombre"] for camara in self.camaras}
        self.tabla_eventos.setRowCount(len(self.eventos))
        for fila, evento in enumerate(self.eventos):
            camara_id = evento.get("camara_id", "")
            nombre_camara = nombres_camaras.get(camara_id)
            camara_visible = f"{nombre_camara} ({camara_id})" if nombre_camara else camara_id
            valores = [
                evento.get("_id", ""),
                camara_visible,
                evento.get("fecha", ""),
                evento.get("hora", ""),
                evento.get("tipo", ""),
                evento.get("descripcion", ""),
                evento.get("estado", ""),
            ]
            self._llenar_fila(self.tabla_eventos, fila, valores, evento)

    def _llenar_fila(
        self,
        tabla: QTableWidget,
        fila: int,
        valores: list[str],
        datos: dict,
    ) -> None:
        for columna, valor in enumerate(valores):
            item = QTableWidgetItem(str(valor))
            item.setData(Qt.ItemDataRole.UserRole, datos)
            tabla.setItem(fila, columna, item)
        tabla.resizeColumnsToContents()

    def _camara_seleccionada(self) -> dict | None:
        fila = self.tabla_camaras.currentRow()
        if fila < 0:
            return None
        item = self.tabla_camaras.item(fila, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _evento_seleccionado(self) -> dict | None:
        fila = self.tabla_eventos.currentRow()
        if fila < 0:
            return None
        item = self.tabla_eventos.item(fila, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _agregar_camara(self) -> None:
        dialogo = CamaraDialog(self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.api.crear_camara(dialogo.datos())
        except ApiError as exc:
            QMessageBox.warning(self, "Agregar camara", str(exc))
            return
        self.refrescar_todo()

    def _consultar_camara(self) -> None:
        camara = self._camara_seleccionada()
        if camara is None:
            QMessageBox.information(self, "Consultar camara", "Selecciona una camara.")
            return
        try:
            camara = self.api.obtener_camara(camara["_id"])
        except ApiError as exc:
            QMessageBox.warning(self, "Consultar camara", str(exc))
            return
        QMessageBox.information(self, "Camara", self._detalle_camara(camara))

    def _editar_camara(self) -> None:
        camara = self._camara_seleccionada()
        if camara is None:
            QMessageBox.information(self, "Editar camara", "Selecciona una camara.")
            return
        try:
            camara = self.api.obtener_camara(camara["_id"])
        except ApiError as exc:
            QMessageBox.warning(self, "Editar camara", str(exc))
            return
        dialogo = CamaraDialog(self, camara)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.api.modificar_camara(camara["_id"], dialogo.datos())
        except ApiError as exc:
            QMessageBox.warning(self, "Editar camara", str(exc))
            return
        self.refrescar_todo()

    def _eliminar_camara(self) -> None:
        camara = self._camara_seleccionada()
        if camara is None:
            QMessageBox.information(self, "Eliminar camara", "Selecciona una camara.")
            return
        respuesta = QMessageBox.question(
            self,
            "Eliminar camara",
            f"Eliminar la camara {camara['_id']}?",
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        try:
            self.api.eliminar_camara(camara["_id"])
        except ApiError as exc:
            QMessageBox.warning(self, "Eliminar camara", str(exc))
            return
        self.refrescar_todo()

    def _agregar_evento(self) -> None:
        if not self.camaras:
            self.refrescar_camaras()
        if not self.camaras:
            QMessageBox.information(
                self,
                "Agregar evento",
                "Primero debe existir al menos una camara.",
            )
            return
        dialogo = EventoDialog(self.camaras, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.api.crear_evento(dialogo.datos())
        except ApiError as exc:
            QMessageBox.warning(self, "Agregar evento", str(exc))
            return
        self.refrescar_eventos()

    def _consultar_evento(self) -> None:
        evento = self._evento_seleccionado()
        if evento is None:
            QMessageBox.information(self, "Consultar evento", "Selecciona un evento.")
            return
        try:
            evento = self.api.obtener_evento(evento["_id"])
        except ApiError as exc:
            QMessageBox.warning(self, "Consultar evento", str(exc))
            return
        QMessageBox.information(self, "Evento", self._detalle_evento(evento))

    def _detalle_camara(self, camara: dict) -> str:
        return (
            f"ID: {camara.get('_id', '')}\n"
            f"Nombre: {camara.get('nombre', '')}\n"
            f"Ubicacion: {camara.get('ubicacion', '')}\n"
            f"Estado: {camara.get('estado', '')}\n"
            f"Fecha de instalacion: {camara.get('fecha_instalacion', '')}"
        )

    def _detalle_evento(self, evento: dict) -> str:
        nombres_camaras = {camara["_id"]: camara["nombre"] for camara in self.camaras}
        camara_id = evento.get("camara_id", "")
        camara_visible = nombres_camaras.get(camara_id, camara_id)
        return (
            f"ID: {evento.get('_id', '')}\n"
            f"Camara: {camara_visible}\n"
            f"Camara ID: {camara_id}\n"
            f"Fecha: {evento.get('fecha', '')}\n"
            f"Hora: {evento.get('hora', '')}\n"
            f"Tipo: {evento.get('tipo', '')}\n"
            f"Descripcion: {evento.get('descripcion', '')}\n"
            f"Estado: {evento.get('estado', '')}"
        )

    def _cerrar_sesion(self) -> None:
        self.usuario_actual = None
        self.camaras = []
        self.eventos = []
        self._mostrar_login()


class CamaraDialog(QDialog):
    def __init__(self, parent: QWidget, camara: dict | None = None) -> None:
        super().__init__(parent)
        self.camara = camara
        self.setWindowTitle("Camara")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.id_input = QLineEdit()
        self.nombre_input = QLineEdit()
        self.ubicacion_input = QLineEdit()
        self.estado_input = QComboBox()
        self.estado_input.addItems(["activa", "inactiva", "mantenimiento"])
        self.fecha_input = QLineEdit()
        self.fecha_input.setPlaceholderText("dd-mm-aaaa")

        form.addRow("ID", self.id_input)
        form.addRow("Nombre", self.nombre_input)
        form.addRow("Ubicacion", self.ubicacion_input)
        form.addRow("Estado", self.estado_input)
        form.addRow("Fecha de instalacion", self.fecha_input)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(botones)
        if camara:
            self.id_input.setText(camara.get("_id", ""))
            self.id_input.setReadOnly(True)
            self.nombre_input.setText(camara.get("nombre", ""))
            self.ubicacion_input.setText(camara.get("ubicacion", ""))
            self.estado_input.setCurrentText(camara.get("estado", "activa"))
            self.fecha_input.setText(camara.get("fecha_instalacion", ""))

    def accept(self) -> None:
        campos = [
            self.nombre_input.text().strip(),
            self.ubicacion_input.text().strip(),
            self.fecha_input.text().strip(),
        ]
        if not self.camara and not self.id_input.text().strip():
            QMessageBox.warning(self, "Camara", "El ID es obligatorio.")
            return
        if any(not campo for campo in campos):
            QMessageBox.warning(self, "Camara", "Completa todos los campos.")
            return
        super().accept()

    def datos(self) -> dict:
        datos = {
            "nombre": self.nombre_input.text().strip(),
            "ubicacion": self.ubicacion_input.text().strip(),
            "estado": self.estado_input.currentText(),
            "fecha_instalacion": self.fecha_input.text().strip(),
        }
        if not self.camara:
            datos["_id"] = self.id_input.text().strip()
        return datos


class EventoDialog(QDialog):
    def __init__(self, camaras: list[dict], parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Evento")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.camara_input = QComboBox()
        for camara in camaras:
            self.camara_input.addItem(
                f"{camara.get('nombre', '')} ({camara.get('_id', '')})",
                camara.get("_id", ""),
            )
        self.fecha_input = QDateEdit()
        self.fecha_input.setDisplayFormat("yyyy-MM-dd")
        self.fecha_input.setDate(QDate.currentDate())
        self.hora_input = QTimeEdit()
        self.hora_input.setDisplayFormat("HH:mm:ss")
        self.hora_input.setTime(QTime.currentTime())
        self.tipo_input = QComboBox()
        self.tipo_input.addItems(["foto", "video"])
        self.descripcion_input = QTextEdit()
        self.descripcion_input.setFixedHeight(80)
        self.estado_input = QLineEdit("nuevo")

        form.addRow("Camara", self.camara_input)
        form.addRow("Fecha", self.fecha_input)
        form.addRow("Hora", self.hora_input)
        form.addRow("Tipo", self.tipo_input)
        form.addRow("Descripcion", self.descripcion_input)
        form.addRow("Estado", self.estado_input)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(botones)

    def accept(self) -> None:
        if not self.descripcion_input.toPlainText().strip() or not self.estado_input.text().strip():
            QMessageBox.warning(self, "Evento", "Completa descripcion y estado.")
            return
        super().accept()

    def datos(self) -> dict:
        return {
            "camara_id": self.camara_input.currentData(),
            "fecha": self.fecha_input.date().toString("yyyy-MM-dd"),
            "hora": self.hora_input.time().toString("HH:mm:ss"),
            "tipo": self.tipo_input.currentText(),
            "descripcion": self.descripcion_input.toPlainText().strip(),
            "estado": self.estado_input.text().strip(),
        }
