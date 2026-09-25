# Qt aporta constantes de alineación y roles para guardar datos en las tablas.
from PySide6.QtCore import Qt
# Widgets de PySide6 usados para construir login, pestañas, formularios,
# tablas y mensajes del dashboard.
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
    QVBoxLayout,
    QWidget,
)

# ApiClient concentra las llamadas HTTP a FastAPI y ApiError representa errores
# listos para mostrar en mensajes de la interfaz.
from services.api_client import ApiClient, ApiError


class MainWindow(QMainWindow):
    # Ventana principal de la aplicación PySide6. Maneja el login y el dashboard,
    # pero delega todas las llamadas HTTP al ApiClient para no mezclar UI con red.
    def __init__(self):
        super().__init__()
        self.api = ApiClient()
        self.usuario_actual: dict | None = None
        self.camaras: list[dict] = []
        self.peticiones: list[dict] = []
        self.eventos: list[dict] = []
        self.setWindowTitle("Cámara Trampa Inteligente")
        self.setMinimumSize(1040, 660)
        self._mostrar_login()

    def _mostrar_login(self) -> None:
        # Construye una pantalla de inicio de sesión simple.
        pantalla = QWidget()
        pantalla.setObjectName("login")
        layout = QVBoxLayout(pantalla)
        layout.setContentsMargins(80, 80, 80, 80)

        title = QLabel("Cámara Trampa Inteligente")
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

        boton = QPushButton("Iniciar sesión")
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
        # Envía las credenciales al backend. Si FastAPI rechaza el login, el
        # dashboard no se muestra y el usuario recibe un mensaje claro.
        try:
            self.usuario_actual = self.api.iniciar_sesion(
                self.usuario_input.text().strip(),
                self.contrasena_input.text(),
            )
        except ApiError as exc:
            QMessageBox.warning(self, "Inicio de sesión", str(exc))
            return
        self._mostrar_dashboard()

    def _mostrar_dashboard(self) -> None:
        # Crea el dashboard después del login. Las pestañas reflejan la separación
        # conceptual pedida: Cámaras, Peticiones y Eventos.
        contenedor = QWidget()
        layout = QVBoxLayout(contenedor)

        encabezado = QHBoxLayout()
        usuario = self.usuario_actual or {}
        titulo = QLabel(f"Dashboard - {usuario.get('usuario', '')}")
        titulo.setStyleSheet("font-size: 22px; font-weight: bold;")
        cerrar = QPushButton("Cerrar sesión")
        cerrar.clicked.connect(self._cerrar_sesion)
        encabezado.addWidget(titulo)
        encabezado.addStretch()
        encabezado.addWidget(cerrar)
        layout.addLayout(encabezado)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._crear_tab_camaras(), "Cámaras")
        self.tabs.addTab(self._crear_tab_peticiones(), "Peticiones")
        self.tabs.addTab(self._crear_tab_eventos(), "Eventos")
        layout.addWidget(self.tabs)
        self.setCentralWidget(contenedor)
        self.refrescar_todo()

    def _crear_tab_camaras(self) -> QWidget:
        # Pestaña de administración de cámaras. Se conserva el CRUD que ya existía
        # porque las peticiones dependen de seleccionar cámaras registradas.
        tab = QWidget()
        layout = QVBoxLayout(tab)

        botones = QHBoxLayout()
        agregar = QPushButton("Agregar cámara")
        consultar = QPushButton("Consultar cámara")
        editar = QPushButton("Editar cámara")
        eliminar = QPushButton("Eliminar cámara")
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
            ["ID", "Nombre", "Ubicación", "Estado", "Fecha de instalación"]
        )
        self._configurar_tabla(self.tabla_camaras)

        layout.addLayout(botones)
        layout.addWidget(self.tabla_camaras)
        return tab

    def _crear_tab_peticiones(self) -> QWidget:
        # Pestaña nueva para solicitar acciones a una cámara. En esta etapa solo
        # crea documentos en MongoDB; todavía no hay comunicación con Raspberry.
        tab = QWidget()
        layout = QVBoxLayout(tab)

        seleccion = QHBoxLayout()
        seleccion.addWidget(QLabel("Cámara:"))
        self.camara_peticion_input = QComboBox()
        seleccion.addWidget(self.camara_peticion_input, 1)

        solicitar_foto = QPushButton("Solicitar foto")
        solicitar_video = QPushButton("Solicitar video")
        solicitar_foto.clicked.connect(lambda: self._crear_peticion("foto"))
        solicitar_video.clicked.connect(lambda: self._crear_peticion("video"))
        seleccion.addWidget(solicitar_foto)
        seleccion.addWidget(solicitar_video)

        botones = QHBoxLayout()
        consultar = QPushButton("Consultar petición")
        actualizar = QPushButton("Actualizar")
        consultar.clicked.connect(self._consultar_peticion)
        actualizar.clicked.connect(self.refrescar_peticiones)
        botones.addWidget(consultar)
        botones.addWidget(actualizar)
        botones.addStretch()

        self.estado_peticiones_label = QLabel("")
        self.tabla_peticiones = QTableWidget(0, 6)
        self.tabla_peticiones.setHorizontalHeaderLabels(
            ["ID", "Cámara", "Tipo", "Estado", "Fecha y hora", "Resultado"]
        )
        self._configurar_tabla(self.tabla_peticiones)

        layout.addLayout(seleccion)
        layout.addLayout(botones)
        layout.addWidget(self.estado_peticiones_label)
        layout.addWidget(self.tabla_peticiones)
        return tab

    def _crear_tab_eventos(self) -> QWidget:
        # Los eventos quedan como historial visual de solo lectura. La interfaz
        # ya no ofrece botones para crear, editar ni eliminar documentos.
        tab = QWidget()
        layout = QVBoxLayout(tab)

        botones = QHBoxLayout()
        consultar = QPushButton("Consultar evento")
        actualizar = QPushButton("Actualizar")
        consultar.clicked.connect(self._consultar_evento)
        actualizar.clicked.connect(self.refrescar_eventos)
        botones.addWidget(consultar)
        botones.addWidget(actualizar)
        botones.addStretch()

        self.estado_eventos_label = QLabel("")
        self.tabla_eventos = QTableWidget(0, 7)
        self.tabla_eventos.setHorizontalHeaderLabels(
            ["ID", "Cámara", "Fecha", "Hora", "Tipo", "Descripción", "Estado"]
        )
        self._configurar_tabla(self.tabla_eventos)

        layout.addLayout(botones)
        layout.addWidget(self.estado_eventos_label)
        layout.addWidget(self.tabla_eventos)
        return tab

    def _configurar_tabla(self, tabla: QTableWidget) -> None:
        # Configura todas las tablas del dashboard con selección por fila y sin
        # edición directa. Los cambios deben pasar por FastAPI para validar datos.
        tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabla.horizontalHeader().setStretchLastSection(True)

    def refrescar_todo(self) -> None:
        # Carga las tres áreas del dashboard. Primero cámaras, porque peticiones y
        # eventos necesitan sus nombres para mostrar información más clara.
        self.refrescar_camaras()
        self.refrescar_peticiones()
        self.refrescar_eventos()

    def refrescar_camaras(self) -> None:
        # Consulta cámaras desde FastAPI y repuebla tanto la tabla como el selector
        # que se usa para crear nuevas peticiones.
        try:
            self.camaras = self.api.listar_camaras()
        except ApiError as exc:
            QMessageBox.warning(self, "Cámaras", str(exc))
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
        self._actualizar_selector_peticiones()

    def refrescar_peticiones(self) -> None:
        # Consulta el historial actualizado. El resultado ahora refleja la respuesta
        # que la Raspberry informó a FastAPI, sin comunicarse con ella directamente.
        try:
            self.peticiones = self.api.listar_peticiones()
        except ApiError as exc:
            QMessageBox.warning(self, "Peticiones", str(exc))
            return

        nombres_camaras = self._nombres_camaras_por_id()
        self.tabla_peticiones.setRowCount(len(self.peticiones))
        for fila, peticion in enumerate(self.peticiones):
            camara_id = peticion.get("camara_id", "")
            valores = [
                peticion.get("_id", ""),
                self._camara_visible(camara_id, nombres_camaras),
                peticion.get("tipo", ""),
                peticion.get("estado", ""),
                peticion.get("fecha_hora", ""),
                peticion.get("nombre_archivo") or peticion.get("mensaje_error", ""),
            ]
            self._llenar_fila(self.tabla_peticiones, fila, valores, peticion)

        self.estado_peticiones_label.setText(
            "No hay peticiones registradas." if not self.peticiones else ""
        )

    def refrescar_eventos(self) -> None:
        # Consulta eventos existentes. La pestaña es de solo lectura, así que esta
        # función nunca inserta documentos en Ani_cam.eventos.
        try:
            if not self.camaras:
                self.camaras = self.api.listar_camaras()
            self.eventos = self.api.listar_eventos()
        except ApiError as exc:
            QMessageBox.warning(self, "Eventos", str(exc))
            return

        nombres_camaras = self._nombres_camaras_por_id()
        self.tabla_eventos.setRowCount(len(self.eventos))
        for fila, evento in enumerate(self.eventos):
            camara_id = evento.get("camara_id", "")
            valores = [
                evento.get("_id", ""),
                self._camara_visible(camara_id, nombres_camaras),
                evento.get("fecha", ""),
                evento.get("hora", ""),
                evento.get("tipo", ""),
                evento.get("descripcion", ""),
                evento.get("estado", ""),
            ]
            self._llenar_fila(self.tabla_eventos, fila, valores, evento)

        self.estado_eventos_label.setText(
            "No hay eventos registrados." if not self.eventos else ""
        )

    def _llenar_fila(
        self,
        tabla: QTableWidget,
        fila: int,
        valores: list[str],
        datos: dict,
    ) -> None:
        # Carga una fila de tabla y guarda el documento original en UserRole.
        # Eso permite consultar el registro completo aunque la tabla muestre textos.
        for columna, valor in enumerate(valores):
            item = QTableWidgetItem(str(valor))
            item.setData(Qt.ItemDataRole.UserRole, datos)
            tabla.setItem(fila, columna, item)
        tabla.resizeColumnsToContents()

    def _actualizar_selector_peticiones(self) -> None:
        # Rellena el combo de cámaras de la pestaña Peticiones con los IDs reales
        # usados por MongoDB, por ejemplo camara001.
        self.camara_peticion_input.clear()
        for camara in self.camaras:
            camara_id = camara.get("_id", "")
            nombre = camara.get("nombre", "")
            self.camara_peticion_input.addItem(f"{camara_id} - {nombre}", camara_id)

    def _nombres_camaras_por_id(self) -> dict[str, str]:
        # Construye un diccionario auxiliar para mostrar "Nombre (camara001)" en
        # tablas de peticiones y eventos sin alterar los documentos originales.
        return {camara["_id"]: camara["nombre"] for camara in self.camaras}

    def _camara_visible(self, camara_id: str, nombres_camaras: dict[str, str]) -> str:
        # Devuelve una etiqueta legible para la cámara. Si no se encuentra el
        # nombre, se mantiene el ID para no ocultar información útil.
        nombre_camara = nombres_camaras.get(camara_id)
        return f"{nombre_camara} ({camara_id})" if nombre_camara else camara_id

    def _camara_seleccionada(self) -> dict | None:
        # Lee la cámara seleccionada en la tabla de Cámaras.
        fila = self.tabla_camaras.currentRow()
        if fila < 0:
            return None
        item = self.tabla_camaras.item(fila, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _peticion_seleccionada(self) -> dict | None:
        # Lee la petición seleccionada en la tabla de Peticiones.
        fila = self.tabla_peticiones.currentRow()
        if fila < 0:
            return None
        item = self.tabla_peticiones.item(fila, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _evento_seleccionado(self) -> dict | None:
        # Lee el evento seleccionado en la tabla de Eventos.
        fila = self.tabla_eventos.currentRow()
        if fila < 0:
            return None
        item = self.tabla_eventos.item(fila, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _agregar_camara(self) -> None:
        # Abre el formulario de alta de cámara y luego refresca el dashboard para
        # que la nueva cámara aparezca también en el selector de peticiones.
        dialogo = CamaraDialog(self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.api.crear_camara(dialogo.datos())
        except ApiError as exc:
            QMessageBox.warning(self, "Agregar cámara", str(exc))
            return
        self.refrescar_todo()

    def _consultar_camara(self) -> None:
        # Consulta el detalle de la cámara seleccionada directamente al backend.
        camara = self._camara_seleccionada()
        if camara is None:
            QMessageBox.information(self, "Consultar cámara", "Selecciona una cámara.")
            return
        try:
            camara = self.api.obtener_camara(camara["_id"])
        except ApiError as exc:
            QMessageBox.warning(self, "Consultar cámara", str(exc))
            return
        QMessageBox.information(self, "Cámara", self._detalle_camara(camara))

    def _editar_camara(self) -> None:
        # Recupera la cámara actualizada, muestra el formulario y envía solamente
        # los datos modificables al backend.
        camara = self._camara_seleccionada()
        if camara is None:
            QMessageBox.information(self, "Editar cámara", "Selecciona una cámara.")
            return
        try:
            camara = self.api.obtener_camara(camara["_id"])
        except ApiError as exc:
            QMessageBox.warning(self, "Editar cámara", str(exc))
            return
        dialogo = CamaraDialog(self, camara)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.api.modificar_camara(camara["_id"], dialogo.datos())
        except ApiError as exc:
            QMessageBox.warning(self, "Editar cámara", str(exc))
            return
        self.refrescar_todo()

    def _eliminar_camara(self) -> None:
        # Pide confirmación antes de eliminar una cámara. No elimina eventos ni
        # peticiones históricas porque pertenecen a otras colecciones.
        camara = self._camara_seleccionada()
        if camara is None:
            QMessageBox.information(self, "Eliminar cámara", "Selecciona una cámara.")
            return
        respuesta = QMessageBox.question(
            self,
            "Eliminar cámara",
            f"¿Eliminar la cámara {camara['_id']}?",
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        try:
            self.api.eliminar_camara(camara["_id"])
        except ApiError as exc:
            QMessageBox.warning(self, "Eliminar cámara", str(exc))
            return
        self.refrescar_todo()

    def _crear_peticion(self, tipo: str) -> None:
        # Crea una petición de foto o video para la cámara seleccionada en el
        # combo. La respuesta queda en estado pendiente hasta una etapa futura.
        camara_id = self.camara_peticion_input.currentData()
        if not camara_id:
            QMessageBox.information(
                self,
                "Crear petición",
                "Primero debe existir al menos una cámara.",
            )
            return
        try:
            self.api.crear_peticion(camara_id, tipo)
        except ApiError as exc:
            QMessageBox.warning(self, "Crear petición", str(exc))
            return
        QMessageBox.information(self, "Peticiones", "Petición creada correctamente.")
        self.refrescar_peticiones()

    def _consultar_peticion(self) -> None:
        # Muestra el detalle de una petición existente sin modificar su estado.
        peticion = self._peticion_seleccionada()
        if peticion is None:
            QMessageBox.information(
                self,
                "Consultar petición",
                "Selecciona una petición.",
            )
            return
        try:
            peticion = self.api.obtener_peticion(peticion["_id"])
        except ApiError as exc:
            QMessageBox.warning(self, "Consultar petición", str(exc))
            return
        QMessageBox.information(self, "Petición", self._detalle_peticion(peticion))

    def _consultar_evento(self) -> None:
        # Consulta un evento existente. No hay alta, edición ni eliminación de
        # eventos desde el dashboard.
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
        # Formatea una cámara para mostrarla en una ventana de información.
        return (
            f"ID: {camara.get('_id', '')}\n"
            f"Nombre: {camara.get('nombre', '')}\n"
            f"Ubicación: {camara.get('ubicacion', '')}\n"
            f"Estado: {camara.get('estado', '')}\n"
            f"Fecha de instalación: {camara.get('fecha_instalacion', '')}"
        )

    def _detalle_peticion(self, peticion: dict) -> str:
        # Formatea una petición para que el usuario vea claramente cámara, tipo,
        # estado y fecha/hora de creación.
        nombres_camaras = self._nombres_camaras_por_id()
        camara_id = peticion.get("camara_id", "")
        return (
            f"ID: {peticion.get('_id', '')}\n"
            f"Cámara: {self._camara_visible(camara_id, nombres_camaras)}\n"
            f"Tipo: {peticion.get('tipo', '')}\n"
            f"Estado: {peticion.get('estado', '')}\n"
            f"Fecha y hora: {peticion.get('fecha_hora', '')}"
        )

    def _detalle_evento(self, evento: dict) -> str:
        # Formatea un evento de solo lectura. Se muestra como actividad registrada,
        # no como una petición pendiente de ejecución.
        nombres_camaras = self._nombres_camaras_por_id()
        camara_id = evento.get("camara_id", "")
        return (
            f"ID: {evento.get('_id', '')}\n"
            f"Cámara: {self._camara_visible(camara_id, nombres_camaras)}\n"
            f"Cámara ID: {camara_id}\n"
            f"Fecha: {evento.get('fecha', '')}\n"
            f"Hora: {evento.get('hora', '')}\n"
            f"Tipo: {evento.get('tipo', '')}\n"
            f"Descripción: {evento.get('descripcion', '')}\n"
            f"Estado: {evento.get('estado', '')}"
        )

    def _cerrar_sesion(self) -> None:
        # Limpia el estado local al cerrar sesión para evitar que datos de un
        # usuario queden visibles al volver a la pantalla de login.
        self.usuario_actual = None
        self.camaras = []
        self.peticiones = []
        self.eventos = []
        self._mostrar_login()


class CamaraDialog(QDialog):
    # Formulario reutilizado para crear y editar cámaras.
    def __init__(self, parent: QWidget, camara: dict | None = None) -> None:
        super().__init__(parent)
        self.camara = camara
        self.setWindowTitle("Cámara")

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
        form.addRow("Ubicación", self.ubicacion_input)
        form.addRow("Estado", self.estado_input)
        form.addRow("Fecha de instalación", self.fecha_input)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(botones)

        # Cuando se edita una cámara existente, el ID queda bloqueado porque es la
        # clave primaria manual usada por MongoDB y por las relaciones con peticiones.
        if camara:
            self.id_input.setText(camara.get("_id", ""))
            self.id_input.setReadOnly(True)
            self.nombre_input.setText(camara.get("nombre", ""))
            self.ubicacion_input.setText(camara.get("ubicacion", ""))
            self.estado_input.setCurrentText(camara.get("estado", "activa"))
            self.fecha_input.setText(camara.get("fecha_instalacion", ""))

    def accept(self) -> None:
        # Valida campos mínimos antes de cerrar el diálogo. La validación final de
        # formato también se realiza en FastAPI con los modelos Pydantic.
        campos = [
            self.nombre_input.text().strip(),
            self.ubicacion_input.text().strip(),
            self.fecha_input.text().strip(),
        ]
        if not self.camara and not self.id_input.text().strip():
            QMessageBox.warning(self, "Cámara", "El ID es obligatorio.")
            return
        if any(not campo for campo in campos):
            QMessageBox.warning(self, "Cámara", "Completa todos los campos.")
            return
        super().accept()

    def datos(self) -> dict:
        # Devuelve un diccionario listo para enviar al ApiClient. Al editar no se
        # incluye _id porque el identificador viaja en la URL.
        datos = {
            "nombre": self.nombre_input.text().strip(),
            "ubicacion": self.ubicacion_input.text().strip(),
            "estado": self.estado_input.currentText(),
            "fecha_instalacion": self.fecha_input.text().strip(),
        }
        if not self.camara:
            datos["_id"] = self.id_input.text().strip()
        return datos
