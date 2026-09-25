"""Ventana PySide6 para capturar y consultar archivos locales."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from almacenamiento.gestor_archivos import ArchivoCaptura, GestorArchivos
from camara.controlador_camara import ControladorCamara, ErrorCamara


class VentanaPrincipal(QMainWindow):
    """Ofrece las acciones minimas de prueba de la camara y su almacenamiento."""

    def __init__(self, controlador: ControladorCamara, gestor: GestorArchivos) -> None:
        super().__init__()
        self.controlador = controlador
        self.gestor = gestor
        self._ruta_imagen: Path | None = None
        self._ruta_video_grabando: Path | None = None

        self.setWindowTitle("Camara Trampa - Prueba Raspberry Pi")
        self.resize(1050, 650)
        self._crear_interfaz()
        self._actualizar_estado_botones()
        self.verificar_camara()
        self.actualizar_archivos()

    def _crear_interfaz(self) -> None:
        contenedor = QWidget()
        self.setCentralWidget(contenedor)
        diseno = QVBoxLayout(contenedor)
        diseno.setContentsMargins(18, 18, 18, 18)
        diseno.setSpacing(12)

        titulo = QLabel("CAMARA TRAMPA")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        diseno.addWidget(titulo)

        self.estado_camara = QLabel("Estado de camara: COMPROBANDO")
        self.estado_camara.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.estado_camara.setFrameShape(QFrame.Shape.StyledPanel)
        self.estado_camara.setMinimumHeight(34)
        diseno.addWidget(self.estado_camara)

        acciones = QHBoxLayout()
        self.boton_foto = QPushButton("Tomar foto")
        self.boton_iniciar = QPushButton("Iniciar video")
        self.boton_detener = QPushButton("Detener video")
        self.boton_archivos = QPushButton("Ver archivos")
        for boton in (self.boton_foto, self.boton_iniciar, self.boton_detener, self.boton_archivos):
            boton.setMinimumHeight(38)
            acciones.addWidget(boton)
        diseno.addLayout(acciones)

        self.tabla_archivos = QTableWidget(0, 4)
        self.tabla_archivos.setHorizontalHeaderLabels(["Nombre", "Tipo", "Fecha", "Hora"])
        self.tabla_archivos.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_archivos.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_archivos.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_archivos.setAlternatingRowColors(True)
        self.tabla_archivos.horizontalHeader().setStretchLastSection(True)
        self.tabla_archivos.setColumnWidth(0, 230)

        self.etiqueta_imagen = QLabel("Selecciona una foto para visualizarla")
        self.etiqueta_imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.etiqueta_imagen.setMinimumSize(430, 300)
        self.etiqueta_imagen.setFrameShape(QFrame.Shape.StyledPanel)
        self.etiqueta_imagen.setWordWrap(True)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(430, 300)
        self.video_widget.hide()
        self.reproductor = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.reproductor.setAudioOutput(self.audio)
        self.reproductor.setVideoOutput(self.video_widget)

        self.boton_reproducir = QPushButton("Reproducir video seleccionado")
        self.boton_detener_reproduccion = QPushButton("Detener reproduccion")
        self.boton_reproducir.setEnabled(False)
        self.boton_detener_reproduccion.setEnabled(False)

        visor = QWidget()
        diseno_visor = QVBoxLayout(visor)
        diseno_visor.setContentsMargins(0, 0, 0, 0)
        diseno_visor.addWidget(self.etiqueta_imagen)
        diseno_visor.addWidget(self.video_widget)
        diseno_visor.addWidget(self.boton_reproducir)
        diseno_visor.addWidget(self.boton_detener_reproduccion)

        panel = QSplitter(Qt.Orientation.Horizontal)
        panel.addWidget(self.tabla_archivos)
        panel.addWidget(visor)
        panel.setSizes([510, 500])
        diseno.addWidget(panel, 1)

        self.boton_foto.clicked.connect(self.tomar_foto)
        self.boton_iniciar.clicked.connect(self.iniciar_video)
        self.boton_detener.clicked.connect(self.detener_video)
        self.boton_archivos.clicked.connect(self.actualizar_archivos)
        self.tabla_archivos.itemSelectionChanged.connect(self._mostrar_archivo_seleccionado)
        self.boton_reproducir.clicked.connect(self.reproducir_video)
        self.boton_detener_reproduccion.clicked.connect(self.detener_reproduccion)

    def verificar_camara(self) -> None:
        try:
            self.controlador.inicializar()
        except ErrorCamara as exc:
            self.estado_camara.setText("Estado de camara: NO DISPONIBLE")
            self.statusBar().showMessage(str(exc))
            self._mostrar_error(str(exc))
        else:
            self.estado_camara.setText("Estado de camara: DISPONIBLE")
            self.statusBar().showMessage("Camara lista para capturar.")
        self._actualizar_estado_botones()

    def tomar_foto(self) -> None:
        destino = self.gestor.siguiente_ruta_foto()
        try:
            self.controlador.tomar_foto(destino)
        except ErrorCamara as exc:
            self._mostrar_error(str(exc))
            return

        self.statusBar().showMessage(f"Foto tomada correctamente: {destino.name}")
        self.actualizar_archivos(seleccionar=destino)

    def iniciar_video(self) -> None:
        destino = self.gestor.siguiente_ruta_video()
        try:
            self.controlador.iniciar_video(destino)
        except ErrorCamara as exc:
            self._mostrar_error(str(exc))
            return

        self._ruta_video_grabando = destino
        self.statusBar().showMessage(f"Video iniciado: {destino.name}")
        self._actualizar_estado_botones()

    def detener_video(self) -> None:
        try:
            self.controlador.detener_video()
        except ErrorCamara as exc:
            self._mostrar_error(str(exc))
        else:
            nombre = self._ruta_video_grabando.name if self._ruta_video_grabando else "video"
            self.statusBar().showMessage(f"Video detenido: {nombre}")
            self.actualizar_archivos(seleccionar=self._ruta_video_grabando)
        finally:
            self._ruta_video_grabando = None
            self._actualizar_estado_botones()

    def actualizar_archivos(self, seleccionar: Path | None = None) -> None:
        archivos = self.gestor.listar_archivos()
        self.tabla_archivos.setRowCount(len(archivos))
        fila_a_seleccionar: int | None = None

        for fila, archivo in enumerate(archivos):
            item_nombre = QTableWidgetItem(archivo.nombre)
            item_nombre.setData(Qt.ItemDataRole.UserRole, str(archivo.ruta))
            item_nombre.setData(Qt.ItemDataRole.UserRole + 1, archivo.tipo)
            self.tabla_archivos.setItem(fila, 0, item_nombre)
            self.tabla_archivos.setItem(fila, 1, QTableWidgetItem(archivo.tipo))
            self.tabla_archivos.setItem(fila, 2, QTableWidgetItem(archivo.fecha))
            self.tabla_archivos.setItem(fila, 3, QTableWidgetItem(archivo.hora))
            if seleccionar and archivo.ruta == seleccionar:
                fila_a_seleccionar = fila

        if fila_a_seleccionar is not None:
            self.tabla_archivos.selectRow(fila_a_seleccionar)
        self.statusBar().showMessage(f"Archivos encontrados: {len(archivos)}")

    def _archivo_seleccionado(self) -> tuple[Path, str] | None:
        filas = self.tabla_archivos.selectionModel().selectedRows()
        if not filas:
            return None
        item = self.tabla_archivos.item(filas[0].row(), 0)
        return Path(item.data(Qt.ItemDataRole.UserRole)), item.data(Qt.ItemDataRole.UserRole + 1)

    def _mostrar_archivo_seleccionado(self) -> None:
        seleccionado = self._archivo_seleccionado()
        self.reproductor.stop()
        self.boton_detener_reproduccion.setEnabled(False)
        if seleccionado is None:
            return

        ruta, tipo = seleccionado
        if tipo == "Foto":
            self._ruta_imagen = ruta
            self.video_widget.hide()
            self.etiqueta_imagen.show()
            self._mostrar_imagen_escalada()
            self.boton_reproducir.setEnabled(False)
            return

        self._ruta_imagen = None
        self.etiqueta_imagen.setText(f"Video seleccionado: {ruta.name}")
        self.etiqueta_imagen.show()
        self.video_widget.hide()
        self.boton_reproducir.setEnabled(True)

    def _mostrar_imagen_escalada(self) -> None:
        if self._ruta_imagen is None:
            return
        pixmap = QPixmap(str(self._ruta_imagen))
        if pixmap.isNull():
            self.etiqueta_imagen.setText("No se pudo cargar la fotografia seleccionada.")
            return
        tamanio = self.etiqueta_imagen.size()
        self.etiqueta_imagen.setPixmap(
            pixmap.scaled(tamanio, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def reproducir_video(self) -> None:
        seleccionado = self._archivo_seleccionado()
        if seleccionado is None or seleccionado[1] != "Video":
            return
        ruta, _ = seleccionado
        self.etiqueta_imagen.hide()
        self.video_widget.show()
        self.reproductor.setSource(QUrl.fromLocalFile(str(ruta)))
        self.reproductor.play()
        self.boton_detener_reproduccion.setEnabled(True)
        self.statusBar().showMessage(f"Reproduciendo: {ruta.name}")

    def detener_reproduccion(self) -> None:
        self.reproductor.stop()
        self.boton_detener_reproduccion.setEnabled(False)
        self.statusBar().showMessage("Reproduccion detenida.")

    def _actualizar_estado_botones(self) -> None:
        lista = self.controlador.disponible
        grabando = self.controlador.grabando
        self.boton_foto.setEnabled(lista and not grabando)
        self.boton_iniciar.setEnabled(lista and not grabando)
        self.boton_detener.setEnabled(grabando)

    def _mostrar_error(self, mensaje: str) -> None:
        self.statusBar().showMessage(mensaje)
        QMessageBox.warning(self, "Error de camara", mensaje)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._mostrar_imagen_escalada()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.reproductor.stop()
        self.controlador.cerrar()
        event.accept()
