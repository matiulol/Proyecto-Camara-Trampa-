"""Adaptador no bloqueante del PIR para Raspberry Pi 3 Model B+."""
from __future__ import annotations

from collections.abc import Callable
from threading import Lock


class ErrorPIR(RuntimeError):
    """Error recuperable: una falla PIR no debe detener cámara ni polling."""


class SensorPIR:
    """Encapsula GPIO Zero; su callback breve delega la captura a Qt."""
    def __init__(self, pin_bcm: str, al_detectar: Callable[[], None]) -> None:
        self.pin_bcm, self._sensor = pin_bcm, None
        self.al_detectar: Callable[[], None] | None = al_detectar
        # GPIO Zero puede invocar ``when_motion`` en un hilo propio. El candado
        # coordina ese callback con ``cerrar`` para no usar la ventana mientras
        # Qt está destruyéndola.
        self._activo = False
        # El evento que llega a Qt representa un flanco de detección, no el
        # nivel sostenido del PIR. Así un backend GPIO que repita callbacks
        # mientras el sensor está alto no genera nuevas capturas.
        self._en_movimiento = False
        self._candado = Lock()

    def iniciar(self) -> None:
        if not self.pin_bcm:
            raise ErrorPIR("PIR_PIN_BCM no está configurado.")
        sensor = None
        try:
            # MotionSensor usa numeración BCM y registra detecciones sin un bucle
            # ocupado; GPIO Zero funciona en Raspberry Pi 3 B+ con Raspberry Pi OS.
            from gpiozero import MotionSensor
            sensor = MotionSensor(int(self.pin_bcm))
            with self._candado:
                self._sensor = sensor
                self._activo = True
                self._en_movimiento = False
            # Se registra un método propio en lugar del callback de Qt de forma
            # directa: así se distingue el comienzo y el final del movimiento,
            # y ``cerrar`` puede desactivar ambos de manera atómica.
            sensor.when_motion = self._notificar_movimiento
            sensor.when_no_motion = self._notificar_fin_movimiento
        except Exception as exc:
            # Si GPIO Zero creó el recurso pero falló al registrar el callback,
            # se libera antes de informar el error a la interfaz.
            if sensor:
                self.cerrar()
            raise ErrorPIR("No se pudo inicializar el sensor PIR.") from exc

    def _notificar_movimiento(self) -> None:
        """Emite hacia Qt solamente al comenzar un nuevo movimiento."""
        # Mantener el candado mientras se emite garantiza que ``cerrar`` no
        # invalida el callback a mitad de una notificación. La emisión de una
        # señal Qt es breve y encola el slot en el hilo de la interfaz.
        with self._candado:
            if self._activo and not self._en_movimiento and self.al_detectar:
                self._en_movimiento = True
                self.al_detectar()

    def _notificar_fin_movimiento(self) -> None:
        """Marca que el próximo movimiento será una detección nueva."""
        with self._candado:
            if self._activo:
                self._en_movimiento = False

    def cerrar(self) -> None:
        # Se desactiva primero y se elimina el callback de GPIO antes de cerrar
        # el dispositivo. De este modo un evento tardío no conserva acceso a la
        # señal de una ventana que ya comenzó a destruirse.
        with self._candado:
            self._activo = False
            self._en_movimiento = False
            sensor = self._sensor
            self._sensor = None
            self.al_detectar = None
            if sensor:
                try:
                    sensor.when_motion = None
                    sensor.when_no_motion = None
                except Exception:
                    # Aun si GPIO Zero falla al quitar el callback, ``close``
                    # sigue siendo necesario para liberar el pin físico.
                    pass
        if sensor:
            try:
                sensor.close()
            except Exception:
                # El cierre se ejecuta mientras Qt termina la aplicación; no
                # debe impedir liberar el resto de cámara, red e interfaz.
                pass
