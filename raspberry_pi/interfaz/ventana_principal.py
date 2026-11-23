"""Interfaz de monitor para las peticiones que llegan a una Raspberry.

La ventana conserva la responsabilidad de coordinar la interfaz y los eventos
de Qt. La captura queda encapsulada en ``ControladorCamara`` y la comunicación
HTTP en ``ClienteAPI``; así un fallo de red o multimedia no debe cerrar la
aplicación que supervisa a la cámara. Este módulo no consulta MongoDB: recibe
órdenes de FastAPI mediante consulta periódica y muestra en pantalla los resultados de la
captura local.
"""
from __future__ import annotations

# Path reconstruye rutas locales antes de abrir una captura y evita depender de
# una ruta completa recibida por la red.
from pathlib import Path

# QtCore aporta temporizadores, URLs, constantes y el decorador Slot; QtGui
# representa pixmaps y el evento nativo de cierre de una ventana.
from PySide6.QtCore import Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QCloseEvent, QPixmap
# Estos objetos separan la reproducción (QMediaPlayer), su salida audible y el
# control que presenta el video. Son APIs de PySide6, no clases propias.
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
# PySide6 administra controles, disposiciones y mensajes sin dibujarlos manualmente.
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
from comunicacion.cliente_api import ClienteAPI, ErrorAPI


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
        cliente: ClienteAPI,
        intervalo_consulta_ms: int,
        duracion_video_segundos: int,
        intervalo_configuracion_pir_ms: int = 30000,
    ) -> None:
        """Construye la ventana, conserva sus colaboradores y programa consulta periódica.

        ``controlador``, ``gestor`` y ``cliente`` son objetos ya creados por
        ``inicio.py``; recibirlos es inyección de dependencias y hace explícita la
        relación entre clases. ``peticiones`` contiene el historial visible de la
        sesión, mientras que ``peticion_en_ejecucion`` y su ruta asocian el
        proceso actual con el archivo que se está creando. ``QTimer`` ejecuta el
        la consulta periódica dentro del ciclo de eventos sin bloquear la respuesta de la
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
        self._cerrando = False
        self._camara_reservada = False
        self.setWindowTitle("Cámara Trampa - Monitor Raspberry")
        self.resize(900, 570)
        # Primero se crean los controles, luego se intenta abrir la cámara para
        # que un problema de hardware pueda mostrarse en una ventana visible.
        self._crear_interfaz()
        self._verificar_camara()
        # El temporizador usa el ciclo de PySide6: la ventana se mantiene abierta
        # y vuelve a intentar aunque FastAPI esté temporalmente desconectado.
        self.temporizador = QTimer(self)
        # ``tiempo de espera`` es una señal emitida por Qt al vencer el intervalo;
        # ``connect`` asocia el método a la señal para ejecutarlo en el hilo
        # de la interfaz, sin crear un ``while`` que la bloquee.
        self.temporizador.timeout.connect(self.consultar_peticiones)
        self.temporizador.start(intervalo_consulta_ms)
        # Se consulta una vez al arrancar para no esperar el primer intervalo.
        self.consultar_peticiones()

    def _crear_interfaz(self) -> None:
        """Crea los controles, sus disposiciones, señales y el visor local.

        Las etiquetas, tablas y botones son controles de Qt. Sus disposiciones
        ajustan el tamaño y la posición de los controles al redimensionar la ventana;
        por ello no se usan coordenadas fijas. Las señales conectan las acciones del usuario con métodos de esta clase. Qt los invoca al recibir cada señal, sin un bucle manual de eventos. ``QVideoWidget``
        recibe la salida visual de ``QMediaPlayer`` y ``QAudioOutput`` su audio.
        """
        # El control central ocupa la zona principal de QMainWindow. La disposición vertical adapta los controles al tamaño de la ventana.
        contenedor = QWidget()
        self.setCentralWidget(contenedor)
        diseno = QVBoxLayout(contenedor)
        titulo = QLabel("CÁMARA TRAMPA - RASPBERRY")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.estado_servidor = QLabel("Estado: comprobando conexión con FastAPI")
        self.estado_servidor.setFrameShape(QFrame.Shape.StyledPanel)
        self.estado_servidor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        camara = QLabel(f"Cámara: {self.gestor.camara_id}")
        camara.setAlignment(Qt.AlignmentFlag.AlignCenter)
        diseno.addWidget(titulo)
        diseno.addWidget(self.estado_servidor)
        diseno.addWidget(camara)

        # La tabla es de sólo lectura: representa el historial de solicitudes,
        # no un editor de documentos de MongoDB ni de Ani_cam.
        self.tabla = QTableWidget(0, 4)
        # El identificador se conserva en UserRole y en el historial Python,
        # pero no ocupa una columna visual: la vista muestra sólo los datos que
        # el operador necesita para identificar y abrir cada captura.
        self.tabla.setHorizontalHeaderLabels(["Tipo", "Fecha", "Estado", "Visualizar"])
        # La selección por filas permite tratar una petición completa como una
        # unidad. Deshabilitar edición evita que un texto visual parezca cambiar
        # el documento que FastAPI conserva en MongoDB.
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.visor_imagen = QLabel("Selecciona una petición ejecutada para ver su archivo local")
        self.visor_imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Un visor compacto deja más área útil al historial sin alterar la
        # proporción de fotos ni videos, que Qt escala dentro de este espacio.
        self.visor_imagen.setMinimumSize(280, 190)
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
        # Qt Multimedia informa los fallos de códec, archivo o servidor mediante
        # señales asíncronas. Conectarlas evita dejar el error solo en consola y
        # permite volver al visor de imágenes sin terminar la ventana principal.
        self.reproductor.errorOccurred.connect(self._manejar_error_multimedia)
        self.reproductor.mediaStatusChanged.connect(self._actualizar_estado_multimedia)
        visor = QWidget()
        diseno_visor = QVBoxLayout(visor)
        diseno_visor.addWidget(self.visor_imagen)
        diseno_visor.addWidget(self.visor_video)

        # QSplitter permite que el usuario ajuste el espacio entre historial y
        # vista previa sin recalcular posiciones manualmente.
        panel = QSplitter(Qt.Orientation.Horizontal)
        panel.addWidget(self.tabla)
        panel.addWidget(visor)
        panel.setSizes([560, 300])
        diseno.addWidget(panel, 1)

        # La consulta periódica ya activa conserva la actualización automática. Cada fila
        # incorpora su propia acción de visualización para no depender de un
        # botón global ni de la selección actual de otra fila.

    def _verificar_camara(self) -> None:
        """Intenta detectar la cámara al arrancar sin impedir abrir la ventana.

        Esta comprobación temprana ofrece un diagnóstico útil si falta la cámara
        CSI. Capturar ``ErrorCamara`` es manejo controlado de excepciones: se
        informa el problema en la barra de estado, pero no se derriba Qt ni se
        impide que el usuario vea la interfaz o corrija el hardware.
        """
        try:
            self.controlador.inicializar()
        except ErrorCamara as excepcion:
            # El usuario puede ver el problema y la aplicación continúa activa
            # para reintentar en la próxima petición o tras corregir el hardware.
            self.statusBar().showMessage(str(excepcion))

    def consultar_peticiones(self) -> None:
        """Ejecuta un ciclo de consulta periódica para recuperar una orden pendiente.

        La consulta periódica consiste en preguntar periódicamente, en lugar de mantener
        una conexión abierta. Cada disparo de ``QTimer`` invoca este método y
        usa GET, que sólo lee la petición pendiente más antigua de esta cámara.
        Si hay una orden, FastAPI devuelve JSON; si no la hay, no se modifica la
        interfaz. El guardia de ejecución evita que dos ciclos inicien capturas
        simultáneas sobre el mismo recurso físico. Si la red falla, se muestra el
        error y el ciclo siguiente podrá reintentar la cadena Raspberry -> FastAPI.
        """
        # Una sola cámara no ejecuta dos órdenes a la vez; la siguiente consulta periódica
        # se realiza cuando termina la foto o el video actual.
        if self.peticion_en_ejecucion is not None:
            return

        try:
            peticion = self.cliente.obtener_pendiente(self.gestor.camara_id)
        except ErrorAPI as excepcion:
            self.estado_servidor.setText("Estado: desconectada de FastAPI")
            self.statusBar().showMessage(str(excepcion))
            return
        self.estado_servidor.setText("Estado: conectada a FastAPI")
        if peticion:
            # Sólo cuando FastAPI entrega JSON de una orden se inicia una
            # captura; una respuesta sin orden simplemente espera el ciclo siguiente del temporizador.
            self._ejecutar_peticion(peticion)

    def _ejecutar_peticion(self, peticion: dict) -> None:
        """Selecciona foto o video y deja el resultado asociado a la petición.

        ``peticion`` es el diccionario JSON recibido de FastAPI. Primero se lo
        agrega al historial como fila provisional y se reserva una ruta local.
        Para una foto, la captura es inmediata; para un video, se inicia la grabación y
        ``QTimer.singleShot`` programa su final sin detener el ciclo de eventos.
        La estructura ya fue validada por FastAPI, pero un tipo inesperado se
        informa como error controlado para que no quede pendiente indefinidamente
        ni cierre la interfaz.
        """
        if not self.controlador.reservar_captura():
            return
        self._camara_reservada = True
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
        except ErrorCamara as excepcion:
            self._finalizar_error(str(excepcion))

    def _finalizar_video(self) -> None:
        """Cierra la grabación cuando vence la duración configurada.

        Es el método de respuesta que ejecuta el temporizador de una sola vez. Detiene primero
        el flujo de Picamera2/ffmpeg para completar el MP4 y sólo después informa
        a FastAPI que la petición terminó correctamente.
        """
        try:
            self.controlador.detener_video()
            # El archivo sólo se informa como éxito después de detener ffmpeg;
            # antes de ese momento el MP4 todavía podría estar incompleto.
            self._finalizar_exito()
        except ErrorCamara as excepcion:
            self._finalizar_error(str(excepcion))

    def _finalizar_exito(self) -> None:
        """Envía a FastAPI una captura local válida para su subida privada a B2."""
        if not self.peticion_en_ejecucion or not self.ruta_archivo_en_ejecucion:
            return
        ruta = self.ruta_archivo_en_ejecucion
        try:
            # La comprobación precede cualquier transferencia. El archivo queda
            # conservado en SD; FastAPI recibe una copia y posee las claves B2.
            if not ruta.is_file() or ruta.stat().st_size <= 0:
                raise ErrorAPI("La captura local no existe o está vacía.")
            respuesta = self.cliente.subir_archivo_capturado(
                self.peticion_en_ejecucion["_id"], ruta
            )
        except ErrorAPI as excepcion:
            # El archivo local no se borra. Se informa error para no presentar
            # como ejecutada una captura cuya nube no fue confirmada.
            self.peticion_en_ejecucion["mensaje_error"] = str(excepcion)
            self.estado_servidor.setText("Estado: captura local pendiente de informar")
            try:
                respuesta = self.cliente.informar_resultado(
                    self.peticion_en_ejecucion["_id"], "error", mensaje_error=str(excepcion)
                )
                self._reemplazar_peticion(respuesta)
            except ErrorAPI as error_resultado:
                # No se oculta el segundo fallo: puede indicar que FastAPI no
                # logró reconciliar el archivo que B2 ya aceptó. La copia local
                # permanece en SD y el detalle queda visible para diagnosticar.
                detalle = f"{excepcion} | No se pudo informar el resultado: {error_resultado}"
                self.peticion_en_ejecucion["mensaje_error"] = detalle
                self.statusBar().showMessage(detalle)
        else:
            self._reemplazar_peticion(respuesta)
        self._limpiar_ejecucion()

    def _finalizar_error(self, mensaje: str) -> None:
        """Informa un resultado ``error`` sin interrumpir la consulta periódica posterior.

        Recibe un mensaje comprensible producido por cámara o video e intenta
        persistir ese estado mediante PUT. Si FastAPI tampoco responde, conserva
        ambos detalles en la fila local. Limpiar el estado transitorio al final
        permite que el siguiente ciclo de consulta atienda una nueva orden.
        """
        if not self.peticion_en_ejecucion:
            return
        try:
            respuesta = self.cliente.informar_resultado(
                self.peticion_en_ejecucion["_id"], "error", mensaje_error=mensaje
            )
        except ErrorAPI as excepcion:
            # La captura falló y además no pudo notificarse. Se conserva ambos
            # detalles visualmente; una intervención humana podrá crear otra orden.
            self.peticion_en_ejecucion["mensaje_error"] = f"{mensaje} | {excepcion}"
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
        if self._camara_reservada:
            self.controlador.liberar_captura()
            self._camara_reservada = False
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
        """Proyecta el historial de la sesión en controles de solo lectura.

        La tabla es una representación visual de la lista ``peticiones``. Cada
        celda muestra texto, y además guarda el diccionario completo en
        ``UserRole``: Qt permite adjuntar datos no visibles a un elemento para
        recuperarlos luego al seleccionar esa fila.
        """
        self.tabla.setRowCount(len(self.peticiones))
        for fila, peticion in enumerate(self.peticiones):
            valores = [
                # El servidor conserva ``foto`` como valor técnico; la tabla lo
                # traduce a la denominación pedida sin modificar el documento.
                {"foto": "Fotografía", "video": "Video"}.get(peticion.get("tipo", ""), peticion.get("tipo", "")),
                peticion.get("fecha_hora", ""),
                peticion.get("estado", "pendiente"),
            ]
            for columna, valor in enumerate(valores):
                # UserRole conserva la petición completa fuera del texto visible
                # para recuperar sus metadatos al seleccionar una fila.
                elemento = QTableWidgetItem(str(valor))
                elemento.setData(Qt.ItemDataRole.UserRole, peticion)
                self.tabla.setItem(fila, columna, elemento)
            # La clausura captura el diccionario de esta iteración como valor por
            # defecto; así cada botón abre su archivo y no el de la última fila.
            boton = QPushButton("Visualizar")
            boton.setEnabled(
                peticion.get("estado") == "ejecutado" and bool(peticion.get("nombre_archivo"))
            )
            boton.setToolTip(
                "Abrir la captura local" if boton.isEnabled() else "El archivo todavía no está disponible."
            )
            boton.clicked.connect(lambda _, p=peticion: self._visualizar_peticion(p))
            self.tabla.setCellWidget(fila, 3, boton)
        self.tabla.resizeColumnsToContents()

    def _visualizar_peticion(self, peticion: dict) -> None:
        """Muestra un JPEG o delega un MP4 al servidor de Qt Multimedia.

        La ruta se reconstruye dentro del directorio de la cámara actual, no se
        usa la ruta enviada por HTTP, para evitar que un dato remoto determine qué
        archivo local abrir. Una foto se carga como ``QPixmap`` y se escala sin
        deformar su proporción. Para video, ``QMediaPlayer`` recibe una URL local
        y entrega los cuadros a ``QVideoWidget``; su decodificación es asíncrona,
        por lo que los errores posteriores llegan a los métodos conectados a las señales multimedia.
        """
        # La petición llega desde el botón de su fila. Aunque el ID sea interno
        # y no se muestre, se conserva en el diccionario para relacionar archivo
        # local, resultado y la petición que FastAPI registró.
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
            # QMediaPlayer delega la decodificación al componente multimedia de Qt
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
            "La aplicación seguirá abierta. Comprueba el códec del MP4 y el servidor "
            f"multimedia de Qt.\n\nDetalle técnico: {mensaje}",
        )

    @Slot(QMediaPlayer.MediaStatus)
    def _actualizar_estado_multimedia(self, estado: QMediaPlayer.MediaStatus) -> None:
        """Informa estados finales sin interferir con la captura ni la consulta periódica.

        ``mediaStatusChanged`` emite cambios del reproductor (carga, fin o medio
        inválido). Este método sólo reacciona a ``InvalidMedia`` y deja intacta la
        cámara: reproducir un archivo y capturar una orden son tareas separadas.
        """
        if estado == QMediaPlayer.MediaStatus.InvalidMedia:
            # Algunos componentes multimedia emiten InvalidMedia antes de un error detallado.
            # Se muestra una guía clara aunque no entreguen un mensaje adicional.
            self.statusBar().showMessage(
                "Qt Multimedia no pudo abrir el video; revise las dependencias de reproducción."
            )

    def closeEvent(self, evento: QCloseEvent) -> None:
        """Libera temporizador, reproductor, HTTP y cámara al cerrar la ventana.

        ``closeEvent`` es el nombre impuesto por QMainWindow: Qt lo invoca antes
        de destruir la ventana. Detener primero los servicios evita que un
        función de retorno pendiente use recursos que ya están siendo liberados.
        """
        # La marca se establece antes de cerrar GPIO. Así una señal de Qt que
        # hubiese quedado en cola durante el cierre no inicia otra captura.
        self._cerrando = True
        self.temporizador.stop()
        # Detener primero el temporizador evita que se dispare una nueva consulta periódica
        # mientras la sesión HTTP y la cámara ya se están cerrando.
        self.reproductor.stop()
        self.cliente.cerrar()
        evento.accept()
