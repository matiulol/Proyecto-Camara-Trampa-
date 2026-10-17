# Qt aporta constantes de alineación y roles para guardar datos en las tablas.
from PySide6.QtCore import QObject, QRunnable, QSignalBlocker, QThreadPool, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
# Widgets de PySide6 usados para construir login, pestañas, formularios,
# tablas y mensajes del dashboard.
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSlider,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# ClienteApi concentra las llamadas HTTP a FastAPI y ErrorApi representa errores
# listos para mostrar en mensajes de la interfaz.
from services.cliente_api import ClienteApi, ErrorApi


class SenalesConsultaPeticiones(QObject):
    """Transporta al hilo visual el resultado de una consulta HTTP en segundo plano.

    ``QRunnable`` no es un ``QObject`` y por ello no expone señales propias. Este
    objeto separa el trabajo de red del widget: Qt entrega las señales al hilo de
    la interfaz, que es el único autorizado a modificar la tabla.
    """

    completada = Signal(list)
    fallida = Signal(str)


class ConsultaPeticiones(QRunnable):
    """Ejecuta el GET existente de peticiones fuera del ciclo visual de Qt."""

    def __init__(self, url_base: str, tiempo_espera: int) -> None:
        super().__init__()
        self.url_base = url_base
        self.tiempo_espera = tiempo_espera
        self.senales = SenalesConsultaPeticiones()

    @Slot()
    def run(self) -> None:
        """Consulta FastAPI sin bloquear botones, redibujado ni reproducción."""
        cliente = ClienteApi(self.url_base, self.tiempo_espera)
        try:
            self.senales.completada.emit(cliente.listar_peticiones())
        except ErrorApi as exc:
            self.senales.fallida.emit(str(exc))
        finally:
            # La sesión pertenece exclusivamente a esta tarea de trabajo; cerrar
            # su conexión no altera la sesión HTTP utilizada por otros controles.
            cliente.sesion.close()


def clasificar_archivo_multimedia(archivo: dict, peticion: dict) -> str | None:
    """Normaliza los metadatos de archivo sin alterar los valores del backend.

    Las peticiones conservan ``foto`` y ``video``, pero el endpoint de carga
    guarda los archivos confirmados como ``imagen`` o ``video`` y agrega su MIME.
    Considerar ambos contratos, además de la extensión, evita que una captura
    JPEG válida sea descartada por una diferencia de vocabulario.
    """
    tipo = str(archivo.get("tipo") or peticion.get("tipo") or "").lower()
    contenido = str(archivo.get("tipo_contenido") or "").lower()
    nombre = str(archivo.get("nombre_archivo") or peticion.get("nombre_archivo") or "").lower()
    extension = nombre.rsplit(".", 1)[-1] if "." in nombre else ""
    if tipo in {"foto", "fotografía", "fotografia", "imagen"} or contenido.startswith("image/") or extension in {"jpg", "jpeg", "png"}:
        return "imagen"
    if tipo == "video" or contenido.startswith("video/") or extension == "mp4":
        return "video"
    return None


def decodificar_imagen(contenido: bytes) -> QPixmap | None:
    """Crea un ``QPixmap`` desde bytes descargados sin escribir archivos locales."""
    imagen = QPixmap()
    return imagen if imagen.loadFromData(contenido) else None


def origen_archivo(archivo: dict) -> str:
    """Devuelve el origen sólo cuando MongoDB guarda una relación inequívoca.

    ``id_camara`` identifica dónde se consulta un archivo, no qué flujo lo
    generó. Por eso el origen se determina exclusivamente a partir de
    ``peticion_id`` o ``id_evento`` y nunca a partir del nombre del archivo.
    """
    tiene_peticion = bool(archivo.get("peticion_id"))
    tiene_evento = bool(archivo.get("id_evento"))
    if tiene_peticion and not tiene_evento:
        return "Petición"
    if tiene_evento and not tiene_peticion:
        return "Evento"
    return "Desconocido"


def fecha_archivo(archivo: dict) -> str:
    """Obtiene la primera fecha real disponible sin completar datos ausentes."""
    for campo in ("fecha_hora", "fecha_captura", "fecha_creacion", "created_at"):
        if archivo.get(campo):
            return str(archivo[campo])
    return "No disponible"


class VisorMultimedia(QWidget):
    """Visor lateral reutilizable con estado y red propios por sección."""

    def __init__(self, mensaje_inicial: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._url_visualizacion_actual: QUrl | None = None

        self.imagen = QLabel(mensaje_inicial)
        self.imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.imagen.setMinimumWidth(260)
        self.imagen.setStyleSheet("border: 1px solid #b8c4bd;")

        self.video = QVideoWidget()
        self.video.hide()
        self.reproductor = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.5)
        self.reproductor.setAudioOutput(self.audio)
        self.reproductor.setVideoOutput(self.video)
        self.reproductor.errorOccurred.connect(self._manejar_error)

        self.red = QNetworkAccessManager(self)
        self.red.finished.connect(self._cargar_imagen_recibida)

        self.boton_abrir_navegador = QPushButton("Abrir en navegador")
        self.boton_abrir_navegador.setEnabled(False)
        self.boton_abrir_navegador.clicked.connect(self.abrir_en_navegador)
        self.boton_reproducir = QPushButton("Reproducir")
        self.boton_pausar = QPushButton("Pausar")
        self.volumen = QSlider(Qt.Orientation.Horizontal)
        self.volumen.setRange(0, 100)
        self.volumen.setValue(50)
        self.boton_reproducir.clicked.connect(self.reproductor.play)
        self.boton_pausar.clicked.connect(self.reproductor.pause)
        self.volumen.valueChanged.connect(lambda valor: self.audio.setVolume(valor / 100))
        self._actualizar_controles_video(False)

        distribucion = QVBoxLayout(self)
        distribucion.setContentsMargins(0, 0, 0, 0)
        distribucion.addWidget(self.imagen)
        distribucion.addWidget(self.video)
        controles_video = QHBoxLayout()
        controles_video.addWidget(self.boton_reproducir)
        controles_video.addWidget(self.boton_pausar)
        controles_video.addWidget(QLabel("Volumen"))
        controles_video.addWidget(self.volumen)
        distribucion.addLayout(controles_video)
        distribucion.addWidget(self.boton_abrir_navegador)

    def presentar(self, archivo: dict, peticion: dict, respuesta: dict) -> None:
        """Carga la URL temporal en esta instancia, sin afectar otros visores."""
        tipo = clasificar_archivo_multimedia(archivo, peticion)
        enlace = QUrl(str(respuesta.get("url", "")))
        if not enlace.isValid() or enlace.scheme() not in {"http", "https"}:
            self.reiniciar("El enlace temporal del archivo no está disponible.")
            return

        self._url_visualizacion_actual = enlace
        self.boton_abrir_navegador.setEnabled(True)
        self.reproductor.stop()
        if tipo == "imagen":
            self._actualizar_controles_video(False)
            self.video.hide()
            self.imagen.show()
            self.imagen.setPixmap(QPixmap())
            self.imagen.setText("Cargando fotografía…")
            self.red.get(QNetworkRequest(enlace))
        elif tipo == "video":
            self._actualizar_controles_video(True)
            self.imagen.hide()
            self.video.show()
            self.reproductor.setSource(enlace)
            self.reproductor.play()
        else:
            self.mostrar_mensaje("El tipo de archivo seleccionado no se puede visualizar.")

    @Slot(QNetworkReply)
    def _cargar_imagen_recibida(self, respuesta: QNetworkReply) -> None:
        """Convierte la respuesta asíncrona en una imagen proporcional."""
        # Una descarga anterior puede terminar después de que el usuario eligió
        # otro archivo. Cada visor conserva su propia URL; ignorar respuestas
        # que ya no coinciden impide que una imagen vieja reemplace la actual.
        if respuesta.url() != self._url_visualizacion_actual:
            respuesta.deleteLater()
            return
        if respuesta.error() != QNetworkReply.NetworkError.NoError:
            codigo_http = respuesta.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            mensaje = (
                "La URL temporal de la fotografía venció o no autoriza el acceso."
                if codigo_http in {401, 403}
                else "No se pudo cargar la fotografía seleccionada."
            )
            self.mostrar_mensaje(mensaje)
            respuesta.deleteLater()
            return

        imagen = decodificar_imagen(bytes(respuesta.readAll()))
        if imagen is None:
            self.mostrar_mensaje("El archivo seleccionado no es una fotografía válida.")
        else:
            self.imagen.setPixmap(
                imagen.scaled(
                    self.imagen.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        respuesta.deleteLater()

    @Slot(QMediaPlayer.Error, str)
    def _manejar_error(self, _error: QMediaPlayer.Error, detalle: str) -> None:
        """Informa fallos de URL, códec o backend dentro del visor."""
        self.reproductor.stop()
        mensaje = "No se pudo reproducir el video seleccionado."
        if detalle or self.reproductor.errorString():
            mensaje += " Comprueba que la URL temporal siga vigente y que Qt Multimedia admita el códec MP4."
        self.mostrar_mensaje(mensaje)

    def _actualizar_controles_video(self, habilitados: bool) -> None:
        self.boton_reproducir.setEnabled(habilitados)
        self.boton_pausar.setEnabled(habilitados)
        self.volumen.setEnabled(habilitados)

    def abrir_en_navegador(self) -> None:
        """Abre exclusivamente el enlace temporal ya presentado por esta instancia."""
        if self._url_visualizacion_actual and not QDesktopServices.openUrl(self._url_visualizacion_actual):
            self.mostrar_mensaje("No se pudo abrir el archivo en el navegador.")

    def reiniciar(self, mensaje: str) -> None:
        """Olvida el archivo actual antes de cambiar el contexto de la tabla."""
        self._url_visualizacion_actual = None
        self.boton_abrir_navegador.setEnabled(False)
        self.mostrar_mensaje(mensaje)

    def mostrar_mensaje(self, mensaje: str) -> None:
        """Restablece el visor a un estado seguro y legible."""
        self.reproductor.stop()
        self._actualizar_controles_video(False)
        self.video.hide()
        self.imagen.show()
        self.imagen.setPixmap(QPixmap())
        self.imagen.setText(mensaje)


class VentanaPrincipal(QMainWindow):
    """Ventana principal derivada de ``QMainWindow`` para login y Dashboard.

    La herencia aporta el contenedor de una ventana principal Qt. La clase usa
    composición con ``ClienteApi`` para separar interfaz y comunicación HTTP.
    """
    def __init__(self):
        super().__init__()
        self.api = ClienteApi()
        self.usuario_actual: dict | None = None
        self.camaras: list[dict] = []
        self.peticiones: list[dict] = []
        self.eventos: list[dict] = []
        # Un único trabajo en curso evita acumular GET si FastAPI tarda más que
        # el intervalo. El temporizador sólo programa consultas: nunca realiza
        # la operación HTTP dentro del hilo que dibuja la ventana.
        self._consulta_peticiones_activa = False
        self._ultimo_error_peticiones = ""
        self._pool_consultas = QThreadPool.globalInstance()
        self._dashboard_activo = False
        self.setWindowTitle("AniCAM")
        self.setMinimumSize(1040, 660)
        self._mostrar_login()

    def _mostrar_login(self) -> None:
        # Construye una pantalla de inicio de sesión simple.
        pantalla = QWidget()
        pantalla.setObjectName("login")
        layout = QVBoxLayout(pantalla)
        layout.setContentsMargins(80, 80, 80, 80)

        title = QLabel("AniCAM")
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
        except ErrorApi as exc:
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
        self._dashboard_activo = True
        self.refrescar_todo()
        # Cinco segundos mantiene el historial actualizado sin generar tráfico
        # excesivo. El mecanismo reutiliza ``listar_peticiones`` y los endpoints
        # existentes; no consulta directamente a la Raspberry ni a MongoDB.
        self.temporizador_peticiones = QTimer(self)
        self.temporizador_peticiones.setInterval(5000)
        self.temporizador_peticiones.timeout.connect(self.refrescar_peticiones)
        self.temporizador_peticiones.start()

    def _crear_tab_camaras(self) -> QWidget:
        # Se conserva el CRUD existente y, debajo, se consulta el historial real
        # de la cámara elegida sin abrir selectores ni visores emergentes.
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
        self.tabla_camaras.itemSelectionChanged.connect(self._cargar_archivos_camara_seleccionada)

        self.estado_archivos_camara_label = QLabel(
            "Selecciona una cámara para consultar sus archivos."
        )
        self.tabla_archivos_camara = QTableWidget(0, 6)
        self.tabla_archivos_camara.setHorizontalHeaderLabels(
            ["Nombre", "Tipo", "Fecha", "Origen", "Estado", "Visualizar"]
        )
        self._configurar_tabla(self.tabla_archivos_camara)
        self.tabla_archivos_camara.setMinimumWidth(620)
        self.archivos_camara: list[dict] = []
        self._camara_archivos_id: str | None = None

        # Es una instancia independiente del mismo componente usado en
        # Peticiones: una visualización aquí no cambia el estado de los demás.
        self.visor_multimedia_camaras = VisorMultimedia(
            "Selecciona un archivo y presiona «Visualizar».", self
        )
        self.visor_camaras = self.visor_multimedia_camaras.imagen

        panel_archivos = QSplitter(Qt.Orientation.Horizontal)
        panel_archivos.addWidget(self.tabla_archivos_camara)
        panel_archivos.addWidget(self.visor_multimedia_camaras)
        # Recalcular tablas y visores de multimedia en cada píxel hacía pesado
        # el arrastre. El divisor se mueve con una guía y aplica el tamaño final
        # al soltarlo, sin interferir con las actualizaciones de datos.
        panel_archivos.setOpaqueResize(False)
        panel_archivos.setStretchFactor(0, 0)
        panel_archivos.setStretchFactor(1, 1)
        panel_archivos.setCollapsible(0, False)
        panel_archivos.setCollapsible(1, False)

        layout.addLayout(botones)
        layout.addWidget(self.tabla_camaras)
        layout.addWidget(self.estado_archivos_camara_label)
        layout.addWidget(panel_archivos, 1)
        return tab

    def _crear_tab_peticiones(self) -> QWidget:
        # La petición se crea en FastAPI; luego una Raspberry asociada la obtiene
        # por polling. El Dashboard no se comunica directamente con la cámara.
        tab = QWidget()
        # La referencia identifica la pestaña de Peticiones para su propio
        # visor lateral; Eventos conserva una instancia y contexto distintos.
        self.tab_peticiones = tab
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
        self.tabla_peticiones = QTableWidget(0, 7)
        self.tabla_peticiones.setHorizontalHeaderLabels(
            ["ID", "Cámara", "Tipo", "Estado", "Fecha y hora", "Resultado", "Visualizar"]
        )
        self._configurar_tabla(self.tabla_peticiones)
        self.tabla_peticiones.setMinimumWidth(700)

        # Esta instancia comparte la implementación con Cámaras, pero conserva
        # su propia URL, reproductor, descarga y controles.
        self.visor_multimedia_peticiones = VisorMultimedia(
            "Selecciona una petición para ver su archivo.", self
        )
        # Alias de compatibilidad para los controles ya existentes de Peticiones.
        self.visor_peticiones = self.visor_multimedia_peticiones.imagen
        self.video_peticiones = self.visor_multimedia_peticiones.video
        self.reproductor_peticiones = self.visor_multimedia_peticiones.reproductor
        self.audio_peticiones = self.visor_multimedia_peticiones.audio
        self.red_multimedia = self.visor_multimedia_peticiones.red
        self.boton_abrir_navegador = self.visor_multimedia_peticiones.boton_abrir_navegador
        self.boton_reproducir = self.visor_multimedia_peticiones.boton_reproducir
        self.boton_pausar = self.visor_multimedia_peticiones.boton_pausar
        self.volumen_peticiones = self.visor_multimedia_peticiones.volumen

        panel = QSplitter(Qt.Orientation.Horizontal)
        panel.addWidget(self.tabla_peticiones)
        panel.addWidget(self.visor_multimedia_peticiones)
        panel.setOpaqueResize(False)
        panel.setStretchFactor(0, 0)
        panel.setStretchFactor(1, 1)
        panel.setCollapsible(0, False)
        panel.setCollapsible(1, False)

        layout.addLayout(seleccion)
        layout.addLayout(botones)
        layout.addWidget(self.estado_peticiones_label)
        layout.addWidget(panel, 1)
        # La selección queda disponible para consultar datos, pero no se conecta
        # al visor: descargar o reproducir una captura requiere el botón
        # ``Visualizar`` de la fila de forma explícita.
        return tab

    def _crear_tab_eventos(self) -> QWidget:
        # Los eventos quedan como historial visual de solo lectura. La interfaz
        # ya no ofrece botones para crear, editar ni eliminar documentos.
        tab = QWidget()
        self.tab_eventos = tab
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
        self.tabla_eventos = QTableWidget(0, 8)
        self.tabla_eventos.setHorizontalHeaderLabels(
            ["ID", "Cámara", "Fecha", "Hora", "Tipo", "Descripción", "Estado", "Visualizar"]
        )
        self._configurar_tabla(self.tabla_eventos)

        # Eventos reutiliza el componente multimedia, pero esta instancia tiene
        # su propia URL, red y reproductor. No comparte selección ni estado con
        # la pestaña de Peticiones.
        self.visor_multimedia_eventos = VisorMultimedia(
            "Selecciona un evento y presiona «Visualizar».", self
        )
        self.visor_eventos = self.visor_multimedia_eventos.imagen
        panel = QSplitter(Qt.Orientation.Horizontal)
        panel.addWidget(self.tabla_eventos)
        panel.addWidget(self.visor_multimedia_eventos)
        panel.setOpaqueResize(False)
        panel.setStretchFactor(0, 0)
        panel.setStretchFactor(1, 1)
        panel.setCollapsible(0, False)
        panel.setCollapsible(1, False)

        layout.addLayout(botones)
        layout.addWidget(self.estado_eventos_label)
        layout.addWidget(panel, 1)
        return tab

    def _configurar_tabla(self, tabla: QTableWidget) -> None:
        # Configura todas las tablas del dashboard con selección por fila y sin
        # edición directa. Los cambios deben pasar por FastAPI para validar datos.
        tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Los anchos son una decisión del usuario durante la sesión. ``Stretch``
        # y ``resizeColumnsToContents`` los sobrescribían al redimensionar o al
        # actualizar datos; Interactive conserva el ajuste manual.
        encabezado = tabla.horizontalHeader()
        encabezado.setStretchLastSection(False)
        encabezado.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

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
        except ErrorApi as exc:
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

    def _cargar_archivos_camara_seleccionada(self) -> None:
        """Consulta los metadatos de la cámara marcada, sin pedir URLs B2."""
        camara = self._camara_seleccionada()
        if not camara:
            return
        camara_id = str(camara.get("_id", ""))
        if not camara_id:
            return

        # Cambiar de cámara nunca abre ni descarga un archivo automáticamente.
        self._camara_archivos_id = camara_id
        self.visor_multimedia_camaras.reiniciar(
            "Selecciona un archivo y presiona «Visualizar»."
        )
        try:
            self.archivos_camara = self.api.listar_archivos_camara(camara_id)
        except ErrorApi:
            self.archivos_camara = []
            self.tabla_archivos_camara.setRowCount(0)
            self.estado_archivos_camara_label.setText(
                "No se pudieron consultar los archivos de la cámara seleccionada."
            )
            return

        self._sincronizar_tabla_archivos_camara()

    def _sincronizar_tabla_archivos_camara(self) -> None:
        """Presenta exactamente los metadatos disponibles en ``archivos``."""
        self.tabla_archivos_camara.setRowCount(len(self.archivos_camara))
        for fila, archivo in enumerate(self.archivos_camara):
            tipo = clasificar_archivo_multimedia(archivo, {}) or "Desconocido"
            valores = [
                archivo.get("nombre_archivo") or "No disponible",
                tipo.capitalize(),
                fecha_archivo(archivo),
                origen_archivo(archivo),
                archivo.get("estado_subida") or archivo.get("estado") or "No disponible",
            ]
            self._llenar_fila(self.tabla_archivos_camara, fila, valores, archivo)
            disponible = bool(archivo.get("_id"))
            self._boton_visualizar_archivo_camara(
                fila, archivo, disponible
            )

        if self.archivos_camara:
            self.estado_archivos_camara_label.setText("")
        else:
            self.estado_archivos_camara_label.setText(
                "La cámara seleccionada no tiene archivos registrados."
            )

    def _boton_visualizar_archivo_camara(
        self, fila: int, archivo: dict, habilitado: bool
    ) -> None:
        """Agrega el único disparador explícito de carga para el visor Cámara."""
        boton = QPushButton("Visualizar")
        boton.setEnabled(habilitado)
        boton.setToolTip(
            "Visualizar este archivo en el panel lateral."
            if habilitado
            else "El archivo no contiene un identificador para obtener su enlace temporal."
        )
        boton.clicked.connect(lambda: self._visualizar_archivo_camara(archivo))
        self.tabla_archivos_camara.setCellWidget(fila, 5, boton)

    def _visualizar_archivo_camara(self, archivo: dict) -> None:
        """Obtiene el enlace sólo tras el clic explícito de una fila de Cámara."""
        self._visualizar_archivo_en_visor(
            self.visor_multimedia_camaras, archivo
        )

    def refrescar_peticiones(self) -> None:
        """Programa una actualización sin bloquear la interfaz del Dashboard.

        La tarea usa el mismo ``ClienteApi.listar_peticiones`` que usaba el
        botón manual, pero lo desplaza a un hilo del pool. Si una consulta sigue
        activa, se espera su resultado en vez de duplicar tráfico de red.
        """
        if self._consulta_peticiones_activa:
            return
        if not self._dashboard_activo:
            return
        self._consulta_peticiones_activa = True
        tarea = ConsultaPeticiones(self.api.url_base, self.api.tiempo_espera)
        tarea.senales.completada.connect(self._recibir_peticiones)
        tarea.senales.fallida.connect(self._informar_error_peticiones)
        self._pool_consultas.start(tarea)

    @Slot(list)
    def _recibir_peticiones(self, peticiones: list[dict]) -> None:
        """Sincroniza el modelo recibido y conserva selección y celdas estables."""
        self._consulta_peticiones_activa = False
        if not self._dashboard_activo:
            return
        self._ultimo_error_peticiones = ""
        self.peticiones = peticiones
        self._sincronizar_tabla_peticiones()

    @Slot(str)
    def _informar_error_peticiones(self, mensaje: str) -> None:
        """Registra un fallo de polling una vez, sin diálogos repetitivos."""
        self._consulta_peticiones_activa = False
        if not self._dashboard_activo:
            return
        if mensaje != self._ultimo_error_peticiones:
            self.statusBar().showMessage(f"No se pudieron actualizar las peticiones: {mensaje}")
            self._ultimo_error_peticiones = mensaje

    def _sincronizar_tabla_peticiones(self) -> None:
        """Actualiza sólo las celdas necesarias y restaura la fila seleccionada.

        La identidad visible de cada fila es el ``_id`` de FastAPI. Cuando el
        orden no cambia, se reutilizan los elementos y botones existentes; esto
        evita parpadeos mientras una petición pasa de pendiente a ejecutada.
        """
        seleccionada = self._peticion_seleccionada()
        seleccionada_id = seleccionada.get("_id") if seleccionada else None
        ids_actuales = [
            self.tabla_peticiones.item(fila, 0).text()
            for fila in range(self.tabla_peticiones.rowCount())
            if self.tabla_peticiones.item(fila, 0)
        ]
        ids_nuevos = [str(peticion.get("_id", "")) for peticion in self.peticiones]
        estructura_cambio = ids_actuales != ids_nuevos
        self.tabla_peticiones.setUpdatesEnabled(False)
        # Bloquear sólo durante la sincronización evita que restaurar una fila
        # dispare otra descarga o reinicie un video que ya estaba reproduciéndose.
        bloqueador = QSignalBlocker(self.tabla_peticiones)
        try:
            if estructura_cambio:
                self.tabla_peticiones.setRowCount(len(self.peticiones))

            nombres_camaras = self._nombres_camaras_por_id()
            for fila, peticion in enumerate(self.peticiones):
                camara_id = peticion.get("camara_id", "")
                valores = [
                    peticion.get("_id", ""), self._camara_visible(camara_id, nombres_camaras),
                    peticion.get("tipo", ""), peticion.get("estado", ""),
                    peticion.get("fecha_hora", ""),
                    peticion.get("nombre_archivo") or peticion.get("mensaje_error", ""),
                ]
                for columna, valor in enumerate(valores):
                    item = self.tabla_peticiones.item(fila, columna)
                    if item is None:
                        item = QTableWidgetItem()
                        self.tabla_peticiones.setItem(fila, columna, item)
                    if item.text() != str(valor):
                        item.setText(str(valor))
                    item.setData(Qt.ItemDataRole.UserRole, peticion)
                disponible = peticion.get("estado") == "ejecutado" and bool(peticion.get("archivo_id"))
                boton = self.tabla_peticiones.cellWidget(fila, 6)
                if estructura_cambio or boton is None:
                    self._boton_archivos(self.tabla_peticiones, fila, 6, "peticion", peticion.get("_id", ""), disponible)
                else:
                    boton.setEnabled(disponible)
                    boton.setToolTip("No hay un archivo disponible." if not disponible else "Consultar archivos disponibles")
        finally:
            self.tabla_peticiones.setUpdatesEnabled(True)

        if seleccionada_id:
            for fila, peticion in enumerate(self.peticiones):
                if peticion.get("_id") == seleccionada_id:
                    self.tabla_peticiones.selectRow(fila)
                    break
        del bloqueador

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
        except ErrorApi as exc:
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
            self._boton_archivos(self.tabla_eventos, fila, 7, "evento", evento.get("_id", ""), True)

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

    def _boton_archivos(self, tabla: QTableWidget, fila: int, columna: int, origen: str, identificador: str, habilitado: bool) -> None:
        """Añade acceso a archivos sin asumir que eventos o peticiones los tengan."""
        boton = QPushButton("Visualizar")
        boton.setEnabled(habilitado)
        boton.setToolTip("No hay un archivo disponible." if not habilitado else "Consultar archivos disponibles")
        boton.clicked.connect(lambda: self._mostrar_archivos(origen, identificador))
        tabla.setCellWidget(fila, columna, boton)

    def _mostrar_archivos(self, origen: str, identificador: str) -> None:
        """Muestra archivos de Peticiones y Eventos en visores independientes."""
        visor = (
            self.visor_multimedia_eventos
            if origen == "evento"
            else self.visor_multimedia_peticiones
        )
        cambiar_a_peticiones = origen == "peticion"
        try:
            if origen == "evento":
                archivos = self.api.listar_archivos_evento(identificador)
            elif origen == "peticion":
                archivos = self.api.listar_archivos_peticion(identificador)
            else:
                archivos = self.api.listar_archivos_camara(identificador)
        except ErrorApi:
            visor.reiniciar("No se pudo obtener la lista de archivos.")
            return
        disponibles = [a for a in archivos if a.get("estado_subida") == "confirmada" and a.get("_id")]
        if not disponibles:
            visor.reiniciar("No hay archivos disponibles para visualizar.")
            return
        if len(disponibles) == 1:
            if cambiar_a_peticiones:
                # Conserva la ruta pública de Peticiones y sus integraciones.
                self._visualizar_archivo(disponibles[0])
            else:
                self._visualizar_archivo_en_visor(visor, disponibles[0])
            return
        dialogo = QDialog(self)
        dialogo.setWindowTitle(
            "Seleccionar archivo del evento" if origen == "evento" else "Seleccionar archivo"
        )
        layout = QVBoxLayout(dialogo)
        for archivo in disponibles:
            etiqueta = f"{archivo.get('nombre_archivo', 'Archivo')} — {archivo.get('tipo', '')} — {archivo.get('fecha_hora', '')}"
            boton = QPushButton(etiqueta)
            boton.clicked.connect(
                lambda _, a=archivo: self._elegir_archivo(
                    dialogo, a, visor, cambiar_a_peticiones
                )
            )
            layout.addWidget(boton)
        dialogo.exec()

    def _elegir_archivo(
        self,
        dialogo: QDialog,
        archivo: dict,
        visor: VisorMultimedia,
        cambiar_a_peticiones: bool,
    ) -> None:
        """Carga el archivo elegido en el visor asociado a su sección."""
        dialogo.accept()
        if cambiar_a_peticiones:
            self._visualizar_archivo(archivo)
        else:
            self._visualizar_archivo_en_visor(visor, archivo)

    def _visualizar_archivo(self, archivo: dict, peticion: dict | None = None) -> None:
        """Conserva el visor propio de Peticiones para sus flujos existentes."""
        self._visualizar_archivo_en_visor(
            self.visor_multimedia_peticiones, archivo, peticion or {}, True
        )

    def _visualizar_archivo_en_visor(
        self,
        visor: VisorMultimedia,
        archivo: dict,
        peticion: dict | None = None,
        cambiar_a_peticiones: bool = False,
    ) -> None:
        """Obtiene una URL temporal una sola vez y la entrega al visor indicado."""
        try:
            respuesta = self.api.enlace_visualizacion(archivo["_id"])
        except ErrorApi:
            visor.reiniciar("No se pudo obtener el enlace temporal del archivo.")
            return
        if cambiar_a_peticiones:
            self.tabs.setCurrentWidget(self.tab_peticiones)
        visor.presentar(archivo, peticion or {}, respuesta)

    def _presentar_archivo_en_visor(
        self, archivo: dict, peticion: dict, respuesta: dict
    ) -> None:
        """Adaptador del visor de Peticiones para sus llamadas ya existentes."""
        self.tabs.setCurrentWidget(self.tab_peticiones)
        self.visor_multimedia_peticiones.presentar(archivo, peticion, respuesta)

    @Slot(QNetworkReply)
    def _cargar_imagen_recibida(self, respuesta: QNetworkReply) -> None:
        self.visor_multimedia_peticiones._cargar_imagen_recibida(respuesta)

    @Slot(QMediaPlayer.Error, str)
    def _manejar_error_visor(self, _error: QMediaPlayer.Error, detalle: str) -> None:
        self.visor_multimedia_peticiones._manejar_error(_error, detalle)

    def _actualizar_controles_video(self, habilitados: bool) -> None:
        self.visor_multimedia_peticiones._actualizar_controles_video(habilitados)

    def _abrir_visualizacion_en_navegador(self) -> None:
        self.visor_multimedia_peticiones.abrir_en_navegador()

    def _mostrar_mensaje_visor(self, mensaje: str) -> None:
        self.visor_multimedia_peticiones.mostrar_mensaje(mensaje)

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
        dialogo = DialogoCamara(self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.api.crear_camara(dialogo.datos())
        except ErrorApi as exc:
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
        except ErrorApi as exc:
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
        except ErrorApi as exc:
            QMessageBox.warning(self, "Editar cámara", str(exc))
            return
        dialogo = DialogoCamara(self, camara)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.api.modificar_camara(camara["_id"], dialogo.datos())
        except ErrorApi as exc:
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
        except ErrorApi as exc:
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
        except ErrorApi as exc:
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
        except ErrorApi as exc:
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
        except ErrorApi as exc:
            QMessageBox.warning(self, "Consultar evento", str(exc))
            return
        QMessageBox.information(self, "Evento", self._detalle_evento(evento))

    def _detalle_camara(self, camara: dict) -> str:
        """Formatea la cámara y su configuración PIR para consulta de solo lectura.

        El backend conserva estos campos por cámara. Se comprueba su presencia
        antes de mostrarlos para que documentos históricos no aparezcan como si
        tuvieran una configuración que nunca se guardó.
        """
        pir_habilitado = camara.get("pir_habilitado")
        tipo_pir = camara.get("pir_tipo_captura")
        cooldown = camara.get("pir_cooldown_segundos")

        if pir_habilitado is None:
            detalle_pir = "Estado del sensor: No disponible en este registro."
        elif pir_habilitado:
            tipo_visible = {"foto": "Fotografía", "video": "Video"}.get(
                tipo_pir, "No disponible"
            )
            cooldown_visible = (
                f"{cooldown} segundos" if isinstance(cooldown, int) else "No disponible"
            )
            detalle_pir = (
                "Estado del sensor: Habilitado\n"
                f"Tipo de captura automática: {tipo_visible}\n"
                f"Cooldown entre capturas automáticas: {cooldown_visible}"
            )
        else:
            detalle_pir = (
                "Estado del sensor: Deshabilitado\n"
                "No se realizarán capturas automáticas por detección de movimiento.\n"
                "Tipo de captura automática: No aplica\n"
                "Cooldown entre capturas automáticas: No aplica"
            )

        return (
            f"ID: {camara.get('_id', '')}\n"
            f"Nombre: {camara.get('nombre', '')}\n"
            f"Ubicación: {camara.get('ubicacion', '')}\n"
            f"Estado: {camara.get('estado', '')}\n"
            f"Fecha de instalación: {camara.get('fecha_instalacion', '')}\n\n"
            "Sensor de movimiento (PIR)\n"
            f"{detalle_pir}\n"
            "El cooldown es el tiempo de espera entre capturas automáticas provocadas por movimiento.\n"
            "Rango permitido: mínimo 3 segundos y máximo 3600 segundos.\n"
            "Las peticiones manuales siguen funcionando independientemente de esta configuración."
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
        self._dashboard_activo = False
        if hasattr(self, "temporizador_peticiones"):
            self.temporizador_peticiones.stop()
        if hasattr(self, "reproductor_peticiones"):
            self.reproductor_peticiones.stop()
        if hasattr(self, "visor_multimedia_eventos"):
            self.visor_multimedia_eventos.reproductor.stop()
        if hasattr(self, "visor_multimedia_camaras"):
            self.visor_multimedia_camaras.reproductor.stop()
        self.usuario_actual = None
        self.camaras = []
        self.peticiones = []
        self.eventos = []
        self._mostrar_login()

    def closeEvent(self, evento: QCloseEvent) -> None:
        """Detiene actividad asíncrona y libera HTTP al cerrar el Dashboard.

        Las consultas de peticiones pueden terminar después de que el usuario
        pulse cerrar. Marcar primero el Dashboard como inactivo hace que los
        slots ignoren esas respuestas tardías; cerrar la sesión HTTP libera los
        recursos de red sin alterar datos de FastAPI o MongoDB.
        """
        self._dashboard_activo = False
        if hasattr(self, "temporizador_peticiones"):
            self.temporizador_peticiones.stop()
        for atributo in (
            "visor_multimedia_peticiones",
            "visor_multimedia_eventos",
            "visor_multimedia_camaras",
        ):
            visor = getattr(self, atributo, None)
            if visor is not None:
                try:
                    visor.reproductor.stop()
                except RuntimeError:
                    # Tras cerrar sesión Qt puede haber destruido el widget
                    # central anterior. No es un fallo de reproducción ni debe
                    # impedir cerrar la sesión HTTP que todavía sigue vigente.
                    continue
        cerrar = getattr(self.api, "cerrar", None)
        if callable(cerrar):
            cerrar()
        evento.accept()


class DialogoCamara(QDialog):
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
        # Esta configuración persiste en la cámara elegida y la Raspberry la
        # consulta; no es un control meramente visual del Dashboard.
        self.pir_habilitado_input = QCheckBox("Activar detección PIR")
        self.pir_tipo_input = QComboBox()
        self.pir_tipo_input.addItems(["foto", "video"])
        self.pir_cooldown_input = QSpinBox()
        self.pir_cooldown_input.setRange(3, 3600)
        self.pir_cooldown_input.setValue(10)
        self.fecha_input.setPlaceholderText("dd-mm-aaaa")

        form.addRow("ID", self.id_input)
        form.addRow("Nombre", self.nombre_input)
        form.addRow("Ubicación", self.ubicacion_input)
        form.addRow("Estado", self.estado_input)
        form.addRow("Fecha de instalación", self.fecha_input)
        form.addRow("Sensor PIR", self.pir_habilitado_input)
        form.addRow("Captura por PIR", self.pir_tipo_input)
        form.addRow("Cooldown PIR (segundos)", self.pir_cooldown_input)

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
            self.pir_habilitado_input.setChecked(camara.get("pir_habilitado", False))
            self.pir_tipo_input.setCurrentText(camara.get("pir_tipo_captura", "foto"))
            self.pir_cooldown_input.setValue(camara.get("pir_cooldown_segundos", 10))

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
        # Devuelve un diccionario listo para enviar al ClienteApi. Al editar no se
        # incluye _id porque el identificador viaja en la URL.
        datos = {
            "nombre": self.nombre_input.text().strip(),
            "ubicacion": self.ubicacion_input.text().strip(),
            "estado": self.estado_input.currentText(),
            "fecha_instalacion": self.fecha_input.text().strip(),
            "pir_habilitado": self.pir_habilitado_input.isChecked(),
            "pir_tipo_captura": self.pir_tipo_input.currentText(),
            "pir_cooldown_segundos": self.pir_cooldown_input.value(),
        }
        if not self.camara:
            datos["_id"] = self.id_input.text().strip()
        return datos
