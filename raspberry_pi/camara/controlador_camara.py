"""Adaptador entre ANICAM y la cámara CSI controlada por Picamera2.

Este módulo aísla la dependencia de hardware. El resto de la aplicación conoce
operaciones de alto nivel —tomar foto, iniciar video y cerrar— sin depender de
los detalles de libcamera, del codificador H.264 ni de ffmpeg.
"""

from __future__ import annotations

# Path representa las rutas de forma portable y permite asegurar la carpeta de
# destino antes de pedir a Picamera2 que escriba una captura.
from pathlib import Path
from threading import Lock


class ErrorCamara(RuntimeError):
    """Fallo recuperable de cámara que la interfaz puede informar sin cerrarse.

    Heredar de ``RuntimeError`` preserva el comportamiento normal de una
    excepción, pero da a la interfaz un tipo propio para distinguir los fallos
    del hardware de los de red o de la reproducción multimedia.
    """


class ControladorCamara:
    """Encapsula el ciclo de vida de una cámara Raspberry Pi con Picamera2.

    Esta clase representa el adaptador entre el programa y el dispositivo CSI.
    Su responsabilidad es traducir operaciones del dominio, como ``tomar_foto``
    o ``iniciar_video``, a llamadas de Picamera2. La composición conserva los
    objetos de Picamera2 como atributos privados: solamente esta clase puede
    iniciar o detener el dispositivo físico. Ese encapsulamiento impide que la
    interfaz deje una grabación, un codificador o la cámara abiertos por error.
    """

    def __init__(self, tamano_foto: tuple[int, int], tasa_bits_video: int) -> None:
        """Guarda la configuración de captura sin abrir el hardware todavía.

        Recibe resolución y tasa de bits desde ``configuracion.py`` y crea atributos
        privados para los recursos que aparecerán después. El constructor no
        abre Picamera2: aplazar ese paso permite crear la interfaz aun cuando la
        cámara no esté conectada y facilita importar este módulo en una PC.
        """
        self.tamano_foto = tamano_foto
        self.tasa_bits_video = tasa_bits_video
        # Estos recursos se crean recién en ``inicializar``. Mantenerlos como
        # atributos privados centraliza su ciclo de vida en este controlador:
        # otros objetos pueden pedir una foto o un video, pero no manipular
        # directamente la cámara, el codificador ni la salida de ffmpeg.
        self._camara = None
        self._codificador = None
        self._salida = None
        self._grabando = False
        # La cámara CSI es un recurso único. Tanto las órdenes manuales como el
        # PIR deben reservarla antes de comenzar una captura para no superponer
        # llamadas de Picamera2 desde hilos distintos.
        self._candado_captura = Lock()

    @property
    def grabando(self) -> bool:
        """Expone el estado sin permitir que otros objetos lo modifiquen."""
        return self._grabando

    @property
    def disponible(self) -> bool:
        """Indica si Picamera2 ya creó el recurso de cámara físico."""
        return self._camara is not None

    def reservar_captura(self) -> bool:
        """Reserva en forma no bloqueante el uso exclusivo de la cámara."""
        return self._candado_captura.acquire(blocking=False)

    def liberar_captura(self) -> None:
        """Libera una reserva obtenida con :meth:`reservar_captura`."""
        if self._candado_captura.locked():
            self._candado_captura.release()

    def inicializar(self) -> None:
        """Abre la cámara CSI y aplica una configuración apta para foto y video.

        La importación diferida de Picamera2 permite ejecutar pruebas de módulos
        que no usan hardware desde otra computadora. ``create_video_configuration``
        crea el flujo principal de cuadros con la resolución indicada; después
        ``configure`` aplica esa configuración al dispositivo y ``start`` hace
        que la cámara entregue imágenes. Si ya está inicializada, se retorna sin
        recrear el recurso físico. Cualquier excepción se convierte en
        ``ErrorCamara`` para que la interfaz pueda mostrarla y seguir abierta.
        """
        # Una misma instancia reutiliza la cámara para varias órdenes. Evitar
        # abrirla dos veces impide competir por el dispositivo CSI y conserva la
        # configuración que ya está activa.
        if self._camara is not None:
            return

        try:
            # La importación se retrasa hasta necesitar el hardware. Así el
            # módulo puede importarse para pruebas en una PC sin Picamera2.
            from picamera2 import Picamera2

            camara = Picamera2()
            self._camara = camara
            # Picamera2 separa la creación y la aplicación de la configuración.
            # ``main`` es el flujo principal de cuadros; aquí se fija sólo su
            # resolución porque el formato final del video se define después
            # mediante H264Encoder y FfmpegOutput.
            configuracion = camara.create_video_configuration(main={"size": self.tamano_foto})
            camara.configure(configuracion)
            # Desde este punto la cámara empieza a producir cuadros. Todavía no
            # se guarda nada: ``capture_file`` o ``start_recording`` decidirán
            # si esos cuadros terminan en una foto o en un archivo de video.
            camara.start()
        except Exception as excepcion:
            # Si la inicialización queda a mitad de camino, ``cerrar`` libera
            # cualquier recurso que sí haya sido creado antes de informar el
            # error a la interfaz.
            self.cerrar()
            raise ErrorCamara(self._mensaje_error("No se pudo inicializar la cámara", excepcion)) from excepcion

    def tomar_foto(self, destino: Path) -> None:
        """Captura un JPEG en ``destino`` y traduce fallos de hardware a ANICAM.

        Recibe una ruta calculada por ``GestorArchivos``. Primero garantiza que
        la cámara existe y que la carpeta está disponible; luego ``capture_file``
        pide a Picamera2 una imagen y la escribe como archivo. No devuelve bytes
        porque la decisión del proyecto es conservar fotos y videos en la SD y
        enviar a FastAPI sólo sus metadatos y resultado.
        """
        self.inicializar()
        try:
            # La ruta llega desde GestorArchivos, que evita sobrescribir otra
            # captura. Aun así se asegura su directorio por si fue eliminado
            # entre la reserva de la ruta y el momento de guardar.
            destino.parent.mkdir(parents=True, exist_ok=True)
            # Picamera2 escribe el JPEG directamente en la tarjeta SD; no se
            # carga toda la imagen en la interfaz ni se envía por HTTP.
            self._camara.capture_file(str(destino))
        except Exception as excepcion:
            raise ErrorCamara(self._mensaje_error("No se pudo tomar la foto", excepcion)) from excepcion

    def iniciar_video(self, destino: Path) -> None:
        """Inicia una grabación H.264 encapsulada como MP4 mediante ffmpeg.

        ``H264Encoder`` transforma los cuadros sin comprimir de la cámara en el
        códec H.264; ``FfmpegOutput`` entrega ese flujo a ffmpeg, que lo guarda
        como un MP4 reproducible. Se recibe una ruta de destino, se crea su
        carpeta si hace falta y se conservan referencias privadas al codificador
        y la salida mientras dura la grabación porque Picamera2 las necesita
        hasta ``stop_recording``. El guardia ``_grabando`` evita que dos
        peticiones usen el mismo hardware simultáneamente.
        """
        if self._grabando:
            raise ErrorCamara("Ya hay una grabación en curso.")

        self.inicializar()
        try:
            # Estas dependencias se importan sólo en una grabación. H264Encoder
            # comprime los cuadros y FfmpegOutput los encapsula como MP4 usando
            # ffmpeg instalado en el sistema de la Raspberry.
            from picamera2.encoders import H264Encoder
            from picamera2.outputs import FfmpegOutput

            destino.parent.mkdir(parents=True, exist_ok=True)
            # La tasa de bits configurada controla el equilibrio entre calidad
            # visual y espacio ocupado. La salida recibe la ruta final del MP4.
            codificador = H264Encoder(bitrate=self.tasa_bits_video)
            salida = FfmpegOutput(str(destino))
            # La cámara entrega cuadros al codificador y éste a la salida. Las
            # referencias se guardan para mantener vivos ambos objetos hasta que
            # ``detener_video`` termine correctamente la grabación.
            self._camara.start_recording(codificador, salida)
            self._codificador = codificador
            self._salida = salida
            self._grabando = True
        except Exception as excepcion:
            # No se marca la grabación como activa si nunca llegó a iniciarse;
            # así una petición posterior no queda bloqueada por estado inválido.
            self._codificador = None
            self._salida = None
            raise ErrorCamara(self._mensaje_error("No se pudo iniciar el video", excepcion)) from excepcion

    def detener_video(self) -> None:
        """Finaliza el MP4 y libera el codificador, manteniendo la cámara disponible.

        ``stop_recording`` cierra correctamente la secuencia enviada a ffmpeg,
        algo importante para que el contenedor MP4 quede completo y legible. El
        bloque ``finally`` siempre limpia los atributos de la grabación, incluso
        si falla el dispositivo, para que el estado Python no afirme que hay un
        video activo que ya no puede controlarse.
        """
        if not self._grabando:
            return

        try:
            # Picamera2 detiene el flujo antes de liberar referencias; esto da a
            # ffmpeg la oportunidad de cerrar el contenedor MP4 correctamente.
            self._camara.stop_recording()
        except Exception as excepcion:
            raise ErrorCamara(self._mensaje_error("No se pudo detener el video", excepcion)) from excepcion
        finally:
            # ``finally`` se ejecuta tanto si todo salió bien como si falló. Es
            # una garantía importante al manejar recursos físicos y procesos de
            # multimedia, ya que permite recuperar el controlador para otra orden.
            self._grabando = False
            self._codificador = None
            self._salida = None

    def cerrar(self) -> None:
        """Detiene operaciones activas y libera ordenadamente la cámara física.

        Cerrar cámara, grabación y referencias es esencial: la cámara CSI es un
        recurso exclusivo del sistema operativo. Si se abandona abierta, otra
        ejecución puede no poder usarla o dejar un archivo de video incompleto.
        En el cierre de una ventana no conviene propagar otro error que impida
        liberar los demás recursos; por eso el estado interno se limpia en
        ``finally`` aunque una llamada de Picamera2 falle.
        """
        if self._camara is None:
            return

        try:
            if self._grabando:
                # Una grabación debe finalizar antes de cerrar el dispositivo;
                # de lo contrario el archivo podría quedar incompleto.
                self.detener_video()
            # ``stop`` detiene la entrega de cuadros y ``close`` libera el
            # recurso CSI ante el sistema operativo para que otra aplicación o
            # una ejecución posterior pueda volver a utilizarlo.
            self._camara.stop()
            self._camara.close()
        except Exception:
            # El cierre suele ocurrir cuando Qt ya está destruyendo la ventana;
            # propagar una excepción aquí no permite recuperarse y puede impedir
            # liberar el estado Python que representa el recurso físico.
            pass
        finally:
            # Incluso después de un error se eliminan las referencias Python.
            # Esto evita reutilizar objetos que representan una cámara ya cerrada.
            self._camara = None
            self._codificador = None
            self._salida = None
            self._grabando = False

    @staticmethod
    def _mensaje_error(contexto: str, excepcion: Exception) -> str:
        """Combina una explicación de ANICAM con el detalle técnico original.

        Centralizar este formato evita mensajes distintos para foto, video e
        inicialización y conserva la causa de Picamera2 para diagnosticarla.
        """
        return f"{contexto}. {excepcion}"
