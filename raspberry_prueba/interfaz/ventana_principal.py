"""Interfaz de monitor para las peticiones que llegan a una Raspberry.

La ventana conserva la responsabilidad de coordinar la interfaz y los eventos
de Qt. La captura queda encapsulada en ``ControladorCamara`` y la comunicación
HTTP en ``ClienteBackend``; así un fallo de red o multimedia no debe cerrar la
aplicación que supervisa a la cámara. Este módulo no consulta MongoDB: recibe
órdenes de FastAPI mediante polling y muestra en pantalla los resultados de la
captura local.
"""
from __future__ import annotations

# Path reconstruye rutas locales antes de abrir una captura y evita depender de
# una ruta completa recibida por la red.
from pathlib import Path

# QtCore aporta temporizadores, URLs, constantes y el decorador Slot; QtGui
# representa pixmaps y el evento nativo de cierre de una ventana.
from PySide6.QtCore import Qt, QTimer, QUrl, Slot, Signal
from PySide6.QtGui import QCloseEvent, QPixmap
# Estos objetos separan la reproducción (QMediaPlayer), su salida audible y el
# widget que presenta el video. Son APIs de PySide6, no clases propias.
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
# Los widgets construyen controles, layouts y mensajes sin dibujar manualmente.
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
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

# Los colaboradores encapsulan responsabilidades de almacenamiento, hardware y
# red; la ventana los coordina mediante composición.
from almacenamiento.gestor_archivos import GestorArchivos
from camara.controlador_camara import ControladorCamara, ErrorCamara
from comunicacion.cliente_backend import ClienteBackend, ErrorBackend
from sensor.sensor_pir import SensorPIR, ErrorPIR


class VentanaPrincipal(QMainWindow):
    """Ventana derivada de ``QMainWindow`` que supervisa una cámara.

    ``QMainWindow`` es una clase base de PySide6 para una ventana principal: ya
    proporciona barra de estado, un área central y el ciclo de vida de cierre.
    La herencia permite reutilizar esas capacidades y especializarlas aquí. A la
    vez, esta clase usa composición: recibe objetos especializados para cámara,
    almacenamiento y HTTP en vez de implementar esas responsabilidades dentro
    de los controles visuales. Así la ventana es coordinadora de eventos, no
    dueña de las reglas de hardware o de red.
    """

    def __init__(
        self,
        controlador: ControladorCamara,
        gestor: GestorArchivos,
        cliente: ClienteBackend,
        intervalo_consulta_ms: int,
        duracion_video_segundos: int,
        sensor_pir: SensorPIR | None = None,
        intervalo_configuracion_pir_ms: int = 30000,
    ) -> None:
        """Construye la ventana, conserva sus colaboradores y programa polling.

        ``controlador``, ``gestor`` y ``cliente`` son objetos ya creados por
        ``main.py``; recibirlos es inyección de dependencias y hace explícita la
        relación entre clases. ``peticiones`` contiene el historial visible de la
        sesión, mientras que ``peticion_en_ejecucion`` y su ruta asocian el
        proceso actual con el archivo que se está creando. ``QTimer`` ejecuta el
        polling dentro del ciclo de eventos sin bloquear la respuesta de la
        interfaz ni crear un bucle manual.
        """
        super().__init__()
        self.controlador = controlador
        self.gestor = gestor
        self.cliente = cliente
        # Este estado sólo vive mientras la ventana está abierta. Permite
        # relacionar la respuesta de FastAPI con la captura que la originó.
        # QTimer trabaja en milisegundos; por eso se conserva una conversión de
        # la duración legible configurada en segundos.
        self.duracion_video_ms = duracion_video_segundos * 1000
        # La lista alimenta la tabla. Las otras dos referencias son el estado
        # transitorio de una única orden que la cámara está procesando ahora.
        self.peticiones: list[dict] = []
        self.peticion_en_ejecucion: dict | None = None
        self.ruta_archivo_en_ejecucion: Path | None = None
        self.sensor_pir = sensor_pir
        self.configuracion_pir = {"pir_habilitado": False, "pir_tipo_captura": "foto", "pir_cooldown_segundos": 10}
        self.ultimo_movimiento_ms = 0
        self.setWindowTitle("Cámara Trampa - Monitor Raspberry")
        self.resize(900, 570)
        # Primero se crean los widgets, luego se intenta abrir la cámara para
        # que un problema de hardware pueda mostrarse en una ventana visible.
        self._crear_interfaz()
        self._verificar_camara()
        # El temporizador usa el ciclo de PySide6: la ventana se mantiene abierta
        # y vuelve a intentar aunque FastAPI esté temporalmente desconectado.
        self.temporizador = QTimer(self)
        # ``timeout`` es una señal emitida por Qt al vencer el intervalo;
        # ``connect`` registra el método que actuará como slot en el mismo hilo
        # de la interfaz, sin crear un ``while`` que la bloquee.
        self.temporizador.timeout.connect(self.consultar_peticiones)
        self.temporizador.start(intervalo_consulta_ms)
        self.movimiento_detectado.connect(self._procesar_movimiento)
        self.temporizador_pir = QTimer(self)
        self.temporizador_pir.timeout.connect(self._actualizar_configuracion_pir)
        self.temporizador_pir.start(intervalo_configuracion_pir_ms)
        if self.sensor_pir:
            try:
                self.sensor_pir.iniciar()
            except ErrorPIR as exc:
                self.statusBar().showMessage(str(exc))
        # Se consulta una vez al arrancar para no esperar el primer intervalo.
        self.consultar_peticiones()
        self._actualizar_configuracion_pir()

    def _actualizar_configuracion_pir(self) -> None:
        """Obtiene configuración por cámara; ante red caída conserva la última."""
        try:
            camara = self.cliente.obtener_camara(self.gestor.camara_id)
            self.configuracion_pir = {clave: camara.get(clave, valor) for clave, valor in self.configuracion_pir.items()}
        except ErrorBackend:
            self.statusBar().showMessage("No se pudo actualizar la configuración PIR.")

    @Slot()
    def _procesar_movimiento(self) -> None:
        """Aplica cooldown solo al PIR; nunca bloquea ni altera órdenes manuales."""
        if not self.sensor_pir or not self.configuracion_pir["pir_habilitado"] or self.peticion_en_ejecucion:
            return
        from time import monotonic
        actual = monotonic()
        if actual - self.ultimo_movimiento_ms < self.configuracion_pir["pir_cooldown_segundos"]:
            return
        self.ultimo_movimiento_ms = actual
        try:
            peticion = self.cliente.crear_peticion_pir(self.gestor.camara_id, self.configuracion_pir["pir_tipo_captura"])
            self._ejecutar_peticion(peticion)
        except ErrorBackend as exc:
            self.statusBar().showMessage(str(exc))

    def _crear_interfaz(self) -> None:
        """Crea widgets, layouts, señales y el visor de resultados locales.

        Un widget representa un control visual (etiqueta, tabla o botón). Los
        layouts administran sus tamaños y posiciones al redimensionar la ventana;
        por ello no se usan coordenadas fijas. Las señales conectan una acción
        del usuario o un cambio de selección con métodos de esta ventana, que
        actúan como *slots*, evitando un bucle manual de eventos. ``QVideoWidget``
        recibe la salida visual de ``QMediaPlayer`` y ``QAudioOutput`` su audio.
        """
        # El widget central es el único contenido principal de QMainWindow. El
        # layout vertical adapta automáticamente los controles si se redimensiona
        # la ventana o cambia el tamaño de letra del sistema.
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
        diseno.addWidget(titulo)
        diseno.addWidget(self.estado_backend)
        diseno.addWidget(camara)

        # La tabla es de sólo lectura: representa el historial de solicitudes,
        # no un editor de documentos de MongoDB ni de Ani_cam.
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["ID", "Tipo", "Estado", "Fecha y hora", "Resultado"])
        # La selección por filas permite tratar una petición completa como una
        # unidad. Deshabilitar edición evita que un texto visual parezca cambiar
        # el documento que FastAPI conserva en MongoDB.
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.visor_imagen = QLabel("Selecciona una petición ejecutada para ver su archivo local")
        self.visor_imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.visor_imagen.setMinimumSize(360, 260)
        self.visor_imagen.setFrameShape(QFrame.Shape.StyledPanel)
        self.visor_video = QVideoWidget()
        self.visor_video.hide()
        # El reproductor es padre de la ventana; Qt lo destruirá con ella. La
        # salida de audio y el visor reciben, respectivamente, sus canales de
        # audio y video a través de esta composición.
        self.reproductor = QMediaPlayer(self)
        self.salida_audio = QAudioOutput(self)
        self.reproductor.setAudioOutput(self.salida_audio)
        self.reproductor.setVideoOutput(self.visor_video)
        # Qt Multimedia informa los fallos de códec, archivo o backend mediante
        # señales asíncronas. Conectarlas evita dejar el error solo en consola y
        # permite volver al visor de imágenes sin terminar la ventana principal.
        self.reproductor.errorOccurred.connect(self._manejar_error_multimedia)
        self.reproductor.mediaStatusChanged.connect(self._actualizar_estado_multimedia)
        self.boton_ver = QPushButton("Ver foto o reproducir video")
        self.boton_ver.setEnabled(False)
        visor = QWidget()
        diseno_visor = QVBoxLayout(visor)
        diseno_visor.addWidget(self.visor_imagen)
        diseno_visor.addWidget(self.visor_video)
        diseno_visor.addWidget(self.boton_ver)

        # QSplitter permite que el usuario ajuste el espacio entre historial y
        # vista previa sin recalcular posiciones manualmente.
        panel = QSplitter(Qt.Orientation.Horizontal)
        panel.addWidget(self.tabla)
        panel.addWidget(visor)
        diseno.addWidget(panel, 1)

        actualizar = QPushButton("Consultar ahora")
        # Además del polling automático, este botón permite al usuario solicitar
        # un GET inmediato. Ambos caminos reutilizan el mismo método para que el
        # comportamiento y el manejo de errores sean consistentes.
        actualizar.clicked.connect(self.consultar_peticiones)
        diseno.addWidget(actualizar)

        # Las señales traducen eventos del widget en métodos de esta ventana.
        # Qt se ocupa de invocarlos dentro de su ciclo de eventos.
        self.tabla.itemSelectionChanged.connect(self._preparar_visualizacion)
        self.boton_ver.clicked.connect(self._visualizar_seleccion)

    def _verificar_camara(self) -> None:
        """Intenta detectar la cámara al arrancar sin impedir abrir la ventana.

        Esta comprobación temprana ofrece un diagnóstico útil si falta la cámara
        CSI. Capturar ``ErrorCamara`` es manejo controlado de excepciones: se
        informa el problema en la barra de estado, pero no se derriba Qt ni se
        impide que el usuario vea la interfaz o corrija el hardware.
        """
        try:
            self.controlador.inicializar()
        except ErrorCamara as exc:
            # El usuario puede ver el problema y la aplicación continúa activa
            # para reintentar en la próxima petición o tras corregir el hardware.
            self.statusBar().showMessage(str(exc))

    def consultar_peticiones(self) -> None:
        """Ejecuta un ciclo de polling para recuperar una orden pendiente.

        El polling consiste en preguntar periódicamente, en lugar de mantener
        una conexión abierta. Cada disparo de ``QTimer`` invoca este método y
        usa GET, que sólo lee la petición pendiente más antigua de esta cámara.
        Si hay una orden, FastAPI devuelve JSON; si no la hay, no se modifica la
        interfaz. El guardia de ejecución evita que dos ticks inicien capturas
        simultáneas sobre el mismo recurso físico. Si la red falla, se muestra el
        error y el próximo tick podrá reintentar la cadena Raspberry -> FastAPI.
        """
        # Una sola cámara no ejecuta dos órdenes a la vez; el siguiente polling
        # se realiza cuando termina la foto o el video actual.
        if self.peticion_en_ejecucion is not None:
            return

        try:
            peticion = self.cliente.obtener_pendiente(self.gestor.camara_id)
        except ErrorBackend as exc:
            self.estado_backend.setText("Estado: desconectada de FastAPI")
            self.statusBar().showMessage(str(exc))
            return
        self.estado_backend.setText("Estado: conectada a FastAPI")
        if peticion:
            # Sólo cuando FastAPI entrega JSON de una orden se inicia una
            # captura; una respuesta sin orden simplemente espera el próximo tick.
            self._ejecutar_peticion(peticion)

    def _ejecutar_peticion(self, peticion: dict) -> None:
        """Selecciona foto o video y deja el resultado asociado a la petición.

        ``peticion`` es el diccionario JSON recibido de FastAPI. Primero se lo
        agrega al historial como fila provisional y se reserva una ruta local.
        Para foto la captura es inmediata; para video se inicia la grabación y
        ``QTimer.singleShot`` programa su final sin detener el ciclo de eventos.
        La estructura ya fue validada por FastAPI, pero un tipo inesperado se
        informa como error controlado para que no quede pendiente indefinidamente
        ni cierre la interfaz.
        """
        self.peticion_en_ejecucion = peticion
        # Insertar primero permite mostrar al usuario que la orden fue recibida
        # incluso mientras la foto o el video todavía se está procesando.
        self.peticiones.insert(0, peticion)
        self._actualizar_tabla()
        try:
            if peticion["tipo"] == "foto":
                # Pedir la ruta antes de capturar preserva la regla de nombres
                # secuenciales y permite informar exactamente qué archivo nació.
                self.ruta_archivo_en_ejecucion = self.gestor.siguiente_ruta_foto()
                self.controlador.tomar_foto(self.ruta_archivo_en_ejecucion)
                self._finalizar_exito()
            elif peticion["tipo"] == "video":
                self.ruta_archivo_en_ejecucion = self.gestor.siguiente_ruta_video()
                self.controlador.iniciar_video(self.ruta_archivo_en_ejecucion)
                # singleShot programa el fin sin bloquear la interfaz durante
                # el video. Al vencer, Qt llama al método de finalización.
                QTimer.singleShot(self.duracion_video_ms, self._finalizar_video)
            else:
                self._finalizar_error("La petición recibida tiene un tipo no permitido.")
        except ErrorCamara as exc:
            self._finalizar_error(str(exc))

    def _finalizar_video(self) -> None:
        """Cierra la grabación cuando vence la duración configurada.

        Es el *slot* que ejecuta el temporizador de una sola vez. Detiene primero
        el flujo de Picamera2/ffmpeg para completar el MP4 y sólo después informa
        a FastAPI que la petición terminó correctamente.
        """
        try:
            self.controlador.detener_video()
            # El archivo sólo se informa como éxito después de detener ffmpeg;
            # antes de ese momento el MP4 todavía podría estar incompleto.
            self._finalizar_exito()
        except ErrorCamara as exc:
            self._finalizar_error(str(exc))

    def _finalizar_exito(self) -> None:
        """Envía a FastAPI una captura local válida para su subida privada a B2."""
        if not self.peticion_en_ejecucion or not self.ruta_archivo_en_ejecucion:
            return
        ruta = self.ruta_archivo_en_ejecucion
        try:
            # La comprobación precede cualquier transferencia. El archivo queda
            # conservado en SD; FastAPI recibe una copia y posee las claves B2.
            if not ruta.is_file() or ruta.stat().st_size <= 0:
                raise ErrorBackend("La captura local no existe o está vacía.")
            respuesta = self.cliente.subir_archivo_capturado(
                self.peticion_en_ejecucion["_id"], ruta
            )
        except ErrorBackend as exc:
            # El archivo local no se borra. Se informa error para no presentar
            # como ejecutada una captura cuya nube no fue confirmada.
            self.peticion_en_ejecucion["mensaje_error"] = str(exc)
            self.estado_backend.setText("Estado: captura local pendiente de informar")
            try:
                respuesta = self.cliente.informar_resultado(
                    self.peticion_en_ejecucion["_id"], "error", mensaje_error=str(exc)
                )
                self._reemplazar_peticion(respuesta)
            except ErrorBackend:
                pass
        else:
            self._reemplazar_peticion(respuesta)
        self._limpiar_ejecucion()

    def _finalizar_error(self, mensaje: str) -> None:
        """Informa un resultado ``error`` sin derribar el polling posterior.

        Recibe un mensaje comprensible producido por cámara o video e intenta
        persistir ese estado mediante PUT. Si FastAPI tampoco responde, conserva
        ambos detalles en la fila local. Limpiar el estado transitorio al final
        permite que el siguiente tick del polling atienda una nueva orden.
        """
        if not self.peticion_en_ejecucion:
            return
        try:
            respuesta = self.cliente.informar_resultado(
                self.peticion_en_ejecucion["_id"], "error", mensaje_error=mensaje
            )
        except ErrorBackend as exc:
            # La captura falló y además no pudo notificarse. Se conserva ambos
            # detalles visualmente; una intervención humana podrá crear otra orden.
            self.peticion_en_ejecucion["mensaje_error"] = f"{mensaje} | {exc}"
        else:
            self._reemplazar_peticion(respuesta)
        self.statusBar().showMessage(mensaje)
        self._limpiar_ejecucion()

    def _limpiar_ejecucion(self) -> None:
        """Restablece el estado transitorio y vuelve a habilitar la próxima orden.

        No borra el historial: sólo elimina las referencias de la captura que
        acaba de terminar. Después actualiza la tabla para reflejar la respuesta
        definitiva de FastAPI o el error local que se haya producido.
        """
        self.peticion_en_ejecucion = None
        self.ruta_archivo_en_ejecucion = None
        self._actualizar_tabla()

    def _reemplazar_peticion(self, respuesta: dict) -> None:
        """Sustituye la fila provisional por la respuesta definitiva de FastAPI.

        La respuesta de PUT contiene el documento actualizado. Se busca por
        ``_id`` para modificar sólo la orden correspondiente, manteniendo el
        resto del historial de la sesión sin volver a descargarlo completo.
        """
        for indice, peticion in enumerate(self.peticiones):
            if peticion.get("_id") == respuesta.get("_id"):
                self.peticiones[indice] = respuesta
                return

    def _actualizar_tabla(self) -> None:
        """Proyecta el historial de la sesión en widgets de solo lectura.

        La tabla es una representación visual de la lista ``peticiones``. Cada
        celda muestra texto, y además guarda el diccionario completo en
        ``UserRole``: Qt permite adjuntar datos no visibles a un elemento para
        recuperarlos luego al seleccionar esa fila.
        """
        self.tabla.setRowCount(len(self.peticiones))
        for fila, peticion in enumerate(self.peticiones):
            resultado = peticion.get("nombre_archivo") or peticion.get("mensaje_error", "")
            valores = [
                peticion.get("_id", ""),
                peticion.get("tipo", ""),
                peticion.get("estado", "pendiente"),
                peticion.get("fecha_hora", ""),
                resultado,
            ]
            for columna, valor in enumerate(valores):
                # UserRole conserva la petición completa fuera del texto visible
                # para recuperar sus metadatos al seleccionar una fila.
                elemento = QTableWidgetItem(str(valor))
                elemento.setData(Qt.ItemDataRole.UserRole, peticion)
                self.tabla.setItem(fila, columna, elemento)

    def _preparar_visualizacion(self) -> None:
        """Habilita el visor sólo cuando la señal de selección indica una fila.

        Se ejecuta como *slot* de ``itemSelectionChanged``. Consultar el modelo
        de selección evita intentar abrir un archivo cuando el usuario no eligió
        ninguna petición.
        """
        self.boton_ver.setEnabled(bool(self.tabla.selectionModel().selectedRows()))

    def _visualizar_seleccion(self) -> None:
        """Muestra un JPEG o delega un MP4 al backend de Qt Multimedia.

        La ruta se reconstruye dentro del directorio de la cámara actual, no se
        usa la ruta enviada por HTTP, para evitar que un dato remoto determine qué
        archivo local abrir. Una foto se carga como ``QPixmap`` y se escala sin
        deformar su proporción. Para video, ``QMediaPlayer`` recibe una URL local
        y entrega los cuadros a ``QVideoWidget``; su decodificación es asíncrona,
        por lo que los errores posteriores llegan a los slots multimedia.
        """
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return
        peticion = self.tabla.item(filas[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        # La petición se recupera desde UserRole, no reconstruyéndola a partir de
        # las columnas de texto. Así se conservan campos que no son visibles.
        nombre = peticion.get("nombre_archivo")
        if not nombre or peticion.get("estado") != "ejecutado":
            QMessageBox.information(
                self,
                "Resultado",
                "La petición todavía no tiene un archivo local disponible.",
            )
            return
        directorio = self.gestor.directorio_fotos if peticion["tipo"] == "foto" else self.gestor.directorio_videos
        ruta = directorio / nombre
        if not ruta.exists():
            QMessageBox.warning(
                self,
                "Resultado",
                "El archivo ya no existe en el almacenamiento local.",
            )
            return
        if peticion["tipo"] == "foto":
            # QPixmap carga la imagen local y ``KeepAspectRatio`` evita que el
            # JPEG quede estirado si el tamaño del visor no coincide con la foto.
            self.visor_video.hide()
            self.visor_imagen.show()
            imagen = QPixmap(str(ruta))
            self.visor_imagen.setPixmap(
                imagen.scaled(
                    self.visor_imagen.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
            )
        else:
            # QMediaPlayer delega la decodificación al backend multimedia de Qt
            # disponible en Raspberry Pi OS. El archivo se pasa como URL local,
            # no como una URL HTTP, porque permanece en la tarjeta SD.
            self.visor_imagen.hide()
            self.visor_video.show()
            self.reproductor.stop()
            self.reproductor.setSource(QUrl.fromLocalFile(str(ruta)))
            self.reproductor.play()

    @Slot(QMediaPlayer.Error, str)
    def _manejar_error_multimedia(
        self, _error_multimedia: QMediaPlayer.Error, detalle: str
    ) -> None:
        """Muestra un fallo reproducible de Qt Multimedia sin cerrar ANICAM.

        Un error de decodificación llega después de llamar a ``play`` porque la
        reproducción es asíncrona. Se libera la reproducción actual y se deja la
        ventana operativa para que la Raspberry continúe atendiendo peticiones.
        ``@Slot`` documenta para Qt la firma de la señal y conecta el evento
        ``errorOccurred`` con este método de Python de manera explícita.
        """
        mensaje = detalle or self.reproductor.errorString() or "Error desconocido de Qt Multimedia."
        # Se vuelve a un estado visual seguro antes de mostrar el diálogo. Así un
        # MP4 con códec no disponible no deja visible un reproductor bloqueado.
        self.reproductor.stop()
        self.visor_video.hide()
        self.visor_imagen.show()
        self.visor_imagen.setText("No se pudo reproducir el video seleccionado.")
        self.statusBar().showMessage(f"Error de reproducción: {mensaje}")
        QMessageBox.warning(
            self,
            "No se pudo reproducir el video",
            "La aplicación seguirá abierta. Comprueba el códec del MP4 y el backend "
            f"multimedia de Qt.\n\nDetalle técnico: {mensaje}",
        )

    @Slot(QMediaPlayer.MediaStatus)
    def _actualizar_estado_multimedia(self, estado: QMediaPlayer.MediaStatus) -> None:
        """Informa estados finales sin interferir con la captura ni el polling.

        ``mediaStatusChanged`` emite cambios del reproductor (carga, fin o medio
        inválido). Este slot sólo reacciona a ``InvalidMedia`` y deja intacta la
        cámara: reproducir un archivo y capturar una orden son tareas separadas.
        """
        if estado == QMediaPlayer.MediaStatus.InvalidMedia:
            # Algunos backends emiten InvalidMedia antes de un error detallado.
            # Se muestra una guía clara aunque no entreguen un mensaje adicional.
            self.statusBar().showMessage(
                "Qt Multimedia no pudo abrir el video; revise las dependencias de reproducción."
            )

    def closeEvent(self, evento: QCloseEvent) -> None:
        """Libera temporizador, reproductor, HTTP y cámara al cerrar la ventana.

        ``closeEvent`` es el nombre impuesto por QMainWindow: Qt lo invoca antes
        de destruir la ventana. Detener primero los servicios evita que un
        callback pendiente use recursos que ya están siendo liberados.
        """
        self.temporizador.stop()
        # Detener primero el temporizador evita que un nuevo polling se dispare
        # mientras la sesión HTTP y la cámara ya se están cerrando.
        self.reproductor.stop()
        self.cliente.cerrar()
        self.controlador.cerrar()
        if self.sensor_pir:
            self.sensor_pir.cerrar()
        evento.accept()
    # GPIO Zero puede notificar desde otro hilo; Signal entrega el trabajo al
    # ciclo Qt para no tocar cámara ni widgets desde el callback GPIO.
    movimiento_detectado = Signal()
