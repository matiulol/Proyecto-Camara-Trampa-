"""Coordinación autónoma de capturas automáticas iniciadas por el PIR."""
from __future__ import annotations

from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic

from almacenamiento.gestor_archivos import GestorArchivos
from camara.controlador_camara import ControladorCamara, ErrorCamara
from comunicacion.cliente_api import ClienteAPI, ErrorAPI


class CapturadorPIR:
    """Coordina los estados de espera, captura y rearme del PIR.

    Un fallo de cámara o de persistencia también inicia el período de espera: la
    detección fue aceptada y repetirla de inmediato podría generar bucles de
    fallos con el sensor todavía activo. Nunca se programa una captura diferida.
    """

    ESPERANDO = "esperando"
    CAPTURANDO = "capturando"
    # La propiedad estado conserva el valor previo para no cambiar su contrato.
    ESPERA = "cooldown"
    REARME = "rearme"

    def __init__(
        self,
        controlador: ControladorCamara,
        gestor: GestorArchivos,
        cliente: ClienteAPI,
        duracion_video_segundos: int,
    ) -> None:
        """Guarda los colaboradores y crea el estado sincronizado del PIR.

        ``controlador``, ``gestor`` y ``cliente`` son las mismas dependencias de
        hardware, archivos y HTTP que usa la Raspberry. El hilo de captura sólo
        se crea al aceptar un flanco, y ``duracion_video_segundos`` limita su
        espera al finalizar un video.
        """
        self.controlador = controlador
        self.gestor = gestor
        self.cliente = cliente
        self.duracion_video_segundos = duracion_video_segundos
        self._candado = Lock()
        self._estado = self.ESPERANDO
        self._espera_hasta = 0.0
        self._reposo_observado = True
        self._detener = Event()
        self._hilo: Thread | None = None

    @property
    def estado(self) -> str:
        """Devuelve de forma sincronizada el estado actual del coordinador."""
        with self._candado:
            return self._estado

    def detectar_movimiento(self) -> None:
        """Acepta un flanco válido o lo descarta sin crear trabajo en cola."""
        with self._candado:
            ahora = monotonic()
            if self._estado == self.ESPERA and ahora >= self._espera_hasta:
                self._estado = self.ESPERANDO if self._reposo_observado else self.REARME
            if self._estado != self.ESPERANDO or self._detener.is_set():
                return
            self._estado = self.CAPTURANDO
            self._reposo_observado = False
            self._hilo = Thread(target=self._capturar, name="captura-pir", daemon=True)
            self._hilo.start()

    def finalizar_movimiento(self) -> None:
        """Registra el reposo necesario para rearmar después de la espera."""
        with self._candado:
            self._reposo_observado = True
            if self._estado == self.REARME:
                self._estado = self.ESPERANDO

    def cerrar(self) -> None:
        """Impide nuevos flancos y espera brevemente la captura en curso."""
        self._detener.set()
        hilo = self._hilo
        if hilo and hilo.is_alive():
            hilo.join(timeout=self.duracion_video_segundos + 5)
        self.cliente.cerrar()

    def _capturar(self) -> None:
        """Consulta configuración, captura y registra el resultado de un flanco.

        La operación corre en un hilo propio para no bloquear GPIO ni Qt. Reserva
        la cámara frente a la consulta periódica manual, guarda primero en SD y deja que
        FastAPI registre evento y metadato antes de confirmar B2. Los flancos
        ignorados no se encolan; los fallos de una captura aceptada inician el período de espera y se informan como evento cuando aún no empezó la persistencia.
        """
        configuracion: dict = {}
        tipo = "foto"
        duracion_espera = 10
        ruta: Path | None = None
        reserva = False
        persistencia_iniciada = False
        captura_aceptada = False
        espera_iniciada = False
        try:
            configuracion = self.cliente.obtener_camara(self.gestor.camara_id)
            if not configuracion.get("pir_habilitado", False):
                return
            tipo = configuracion.get("pir_tipo_captura", "foto")
            duracion_espera = int(configuracion.get("pir_cooldown_segundos", 10))
            if tipo not in {"foto", "video"}:
                raise ErrorCamara("La configuración PIR tiene un tipo de captura no permitido.")
            # Si una petición manual ya posee la reserva, este flanco se ignora.
            reserva = self.controlador.reservar_captura()
            if not reserva:
                return
            captura_aceptada = True
            ruta = self.gestor.siguiente_ruta_foto() if tipo == "foto" else self.gestor.siguiente_ruta_video()
            if tipo == "foto":
                self.controlador.tomar_foto(ruta)
            else:
                self.controlador.iniciar_video(ruta)
                self._detener.wait(self.duracion_video_segundos)
                self.controlador.detener_video()
            self._validar_archivo(ruta)
            # La foto ya está escrita o el MP4 fue cerrado: desde aquí corre el
            # período de espera, aunque la transferencia a B2 continúe en este hilo.
            self.controlador.liberar_captura()
            reserva = False
            self._iniciar_espera(duracion_espera)
            espera_iniciada = True
            # Desde este punto FastAPI crea y actualiza el único evento PIR.
            # Si B2 falla, esa misma ruta ya deja el evento y el archivo en
            # error; no debe crearse un segundo evento desde la Raspberry.
            persistencia_iniciada = True
            self.cliente.subir_captura_pir(self.gestor.camara_id, tipo, ruta)
        except (ErrorCamara, ErrorAPI, OSError, ValueError) as excepcion:
            # Sólo se registra un error cuando la detección llegó a intentar una
            # captura. Un PIR deshabilitado u ocupado no produce un evento.
            if reserva and not persistencia_iniciada:
                try:
                    self.cliente.informar_error_captura_pir(self.gestor.camara_id, tipo, str(excepcion))
                except ErrorAPI:
                    pass
        finally:
            if reserva:
                self.controlador.liberar_captura()
            with self._candado:
                # Si no hubo captura (PIR deshabilitado, red al consultar o cámara
                # ocupada), se espera el siguiente flanco sin iniciar el intervalo.
                if captura_aceptada and not espera_iniciada:
                    self._estado = self.ESPERA
                    self._espera_hasta = monotonic() + max(duracion_espera, 0)
                elif not captura_aceptada:
                    self._estado = self.ESPERANDO

    def _iniciar_espera(self, duracion_segundos: int) -> None:
        """Fija el vencimiento del intervalo con un reloj monotónico."""
        with self._candado:
            self._estado = self.ESPERA
            self._espera_hasta = monotonic() + max(duracion_segundos, 0)

    @staticmethod
    def _validar_archivo(ruta: Path) -> None:
        """Rechaza rutas inexistentes o vacías antes de enviarlas al servidor."""
        if not ruta.is_file() or ruta.stat().st_size <= 0:
            raise ErrorCamara("La captura local no existe o está vacía.")
