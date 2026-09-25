"""Interfaz de monitor para las peticiones que llegan a una Raspberry."""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QAbstractItemView, QFrame, QLabel, QMainWindow, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from almacenamiento.gestor_archivos import GestorArchivos
from camara.controlador_camara import ControladorCamara, ErrorCamara
from comunicacion.cliente_backend import ClienteBackend, ErrorBackend


class VentanaPrincipal(QMainWindow):
    """Muestra y ejecuta automáticamente solicitudes del dashboard para una cámara."""

    def __init__(self, controlador: ControladorCamara, gestor: GestorArchivos, cliente: ClienteBackend, intervalo_consulta_ms: int, duracion_video_segundos: int) -> None:
        super().__init__()
        self.controlador, self.gestor, self.cliente = controlador, gestor, cliente
        self.duracion_video_ms = duracion_video_segundos * 1000
        self.peticiones: list[dict] = []
        self.peticion_en_ejecucion: dict | None = None
        self.ruta_archivo_en_ejecucion: Path | None = None
        self.setWindowTitle("Cámara Trampa - Monitor Raspberry")
        self.resize(900, 570)
        self._crear_interfaz()
        self._verificar_camara()
        # El temporizador usa el ciclo de PySide6: la ventana se mantiene abierta
        # y vuelve a intentar aunque FastAPI esté temporalmente desconectado.
        self.temporizador = QTimer(self)
        self.temporizador.timeout.connect(self.consultar_peticiones)
        self.temporizador.start(intervalo_consulta_ms)
        self.consultar_peticiones()

    def _crear_interfaz(self) -> None:
        contenedor = QWidget()
        self.setCentralWidget(contenedor)
        diseno = QVBoxLayout(contenedor)
        titulo = QLabel("CÁMARA TRAMPA - RASPBERRY")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.estado_backend = QLabel("Estado: comprobando conexión con FastAPI")
        self.estado_backend.setFrameShape(QFrame.Shape.StyledPanel)
        self.estado_backend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        camara = QLabel(f"Cámara: {self.gestor.camara_id}")
        camara.setAlignment(Qt.AlignmentFlag.AlignCenter)
        diseno.addWidget(titulo); diseno.addWidget(self.estado_backend); diseno.addWidget(camara)
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["ID", "Tipo", "Estado", "Fecha y hora", "Resultado"])
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.visor_imagen = QLabel("Selecciona una petición ejecutada para ver su archivo local")
        self.visor_imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.visor_imagen.setMinimumSize(360, 260)
        self.visor_imagen.setFrameShape(QFrame.Shape.StyledPanel)
        self.visor_video = QVideoWidget(); self.visor_video.hide()
        self.reproductor = QMediaPlayer(self); self.audio = QAudioOutput(self)
        self.reproductor.setAudioOutput(self.audio); self.reproductor.setVideoOutput(self.visor_video)
        self.boton_ver = QPushButton("Ver foto o reproducir video"); self.boton_ver.setEnabled(False)
        visor = QWidget(); diseno_visor = QVBoxLayout(visor)
        diseno_visor.addWidget(self.visor_imagen); diseno_visor.addWidget(self.visor_video); diseno_visor.addWidget(self.boton_ver)
        panel = QSplitter(Qt.Orientation.Horizontal); panel.addWidget(self.tabla); panel.addWidget(visor)
        diseno.addWidget(panel, 1)
        actualizar = QPushButton("Consultar ahora"); actualizar.clicked.connect(self.consultar_peticiones)
        diseno.addWidget(actualizar)
        self.tabla.itemSelectionChanged.connect(self._preparar_visualizacion)
        self.boton_ver.clicked.connect(self._visualizar_seleccion)

    def _verificar_camara(self) -> None:
        try: self.controlador.inicializar()
        except ErrorCamara as exc: self.statusBar().showMessage(str(exc))

    def consultar_peticiones(self) -> None:
        # Una sola cámara no ejecuta dos órdenes a la vez; el siguiente polling
        # se realiza cuando termina la foto o el video actual.
        if self.peticion_en_ejecucion is not None: return
        try: peticion = self.cliente.obtener_pendiente(self.gestor.camara_id)
        except ErrorBackend as exc:
            self.estado_backend.setText("Estado: desconectada de FastAPI"); self.statusBar().showMessage(str(exc)); return
        self.estado_backend.setText("Estado: conectada a FastAPI")
        if peticion: self._ejecutar_peticion(peticion)

    def _ejecutar_peticion(self, peticion: dict) -> None:
        self.peticion_en_ejecucion = peticion; self.peticiones.insert(0, peticion); self._actualizar_tabla()
        try:
            if peticion["tipo"] == "foto":
                self.ruta_archivo_en_ejecucion = self.gestor.siguiente_ruta_foto()
                self.controlador.tomar_foto(self.ruta_archivo_en_ejecucion); self._finalizar_exito()
            elif peticion["tipo"] == "video":
                self.ruta_archivo_en_ejecucion = self.gestor.siguiente_ruta_video()
                self.controlador.iniciar_video(self.ruta_archivo_en_ejecucion)
                QTimer.singleShot(self.duracion_video_ms, self._finalizar_video)
            else: self._finalizar_error("La petición recibida tiene un tipo no permitido.")
        except ErrorCamara as exc: self._finalizar_error(str(exc))

    def _finalizar_video(self) -> None:
        try: self.controlador.detener_video(); self._finalizar_exito()
        except ErrorCamara as exc: self._finalizar_error(str(exc))

    def _finalizar_exito(self) -> None:
        if not self.peticion_en_ejecucion or not self.ruta_archivo_en_ejecucion: return
        ruta = self.ruta_archivo_en_ejecucion
        try:
            respuesta = self.cliente.informar_resultado(self.peticion_en_ejecucion["_id"], "ejecutado", ruta.name, str(ruta.resolve()))
        except ErrorBackend as exc:
            self.peticion_en_ejecucion["mensaje_error"] = str(exc)
            self.estado_backend.setText("Estado: captura local pendiente de informar")
        else: self._reemplazar_peticion(respuesta)
        self._limpiar_ejecucion()

    def _finalizar_error(self, mensaje: str) -> None:
        if not self.peticion_en_ejecucion: return
        try: respuesta = self.cliente.informar_resultado(self.peticion_en_ejecucion["_id"], "error", mensaje_error=mensaje)
        except ErrorBackend as exc: self.peticion_en_ejecucion["mensaje_error"] = f"{mensaje} | {exc}"
        else: self._reemplazar_peticion(respuesta)
        self.statusBar().showMessage(mensaje); self._limpiar_ejecucion()

    def _limpiar_ejecucion(self) -> None:
        self.peticion_en_ejecucion = None; self.ruta_archivo_en_ejecucion = None; self._actualizar_tabla()

    def _reemplazar_peticion(self, respuesta: dict) -> None:
        for indice, peticion in enumerate(self.peticiones):
            if peticion.get("_id") == respuesta.get("_id"): self.peticiones[indice] = respuesta; return

    def _actualizar_tabla(self) -> None:
        self.tabla.setRowCount(len(self.peticiones))
        for fila, peticion in enumerate(self.peticiones):
            resultado = peticion.get("nombre_archivo") or peticion.get("mensaje_error", "")
            for columna, valor in enumerate([peticion.get("_id", ""), peticion.get("tipo", ""), peticion.get("estado", "pendiente"), peticion.get("fecha_hora", ""), resultado]):
                item = QTableWidgetItem(str(valor)); item.setData(Qt.ItemDataRole.UserRole, peticion); self.tabla.setItem(fila, columna, item)

    def _preparar_visualizacion(self) -> None:
        self.boton_ver.setEnabled(bool(self.tabla.selectionModel().selectedRows()))

    def _visualizar_seleccion(self) -> None:
        filas = self.tabla.selectionModel().selectedRows()
        if not filas: return
        peticion = self.tabla.item(filas[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        nombre = peticion.get("nombre_archivo")
        if not nombre or peticion.get("estado") != "ejecutado":
            QMessageBox.information(self, "Resultado", "La petición todavía no tiene un archivo local disponible."); return
        directorio = self.gestor.directorio_fotos if peticion["tipo"] == "foto" else self.gestor.directorio_videos
        ruta = directorio / nombre
        if not ruta.exists(): QMessageBox.warning(self, "Resultado", "El archivo ya no existe en el almacenamiento local."); return
        if peticion["tipo"] == "foto":
            self.visor_video.hide(); self.visor_imagen.show()
            self.visor_imagen.setPixmap(QPixmap(str(ruta)).scaled(self.visor_imagen.size(), Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.visor_imagen.hide(); self.visor_video.show(); self.reproductor.setSource(QUrl.fromLocalFile(str(ruta))); self.reproductor.play()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.temporizador.stop(); self.reproductor.stop(); self.controlador.cerrar(); event.accept()
