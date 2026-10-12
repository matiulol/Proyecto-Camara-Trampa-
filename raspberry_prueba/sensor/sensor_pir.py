"""Adaptador no bloqueante del PIR para Raspberry Pi 3 Model B+."""
from __future__ import annotations

from collections.abc import Callable


class ErrorPIR(RuntimeError):
    """Error recuperable: una falla PIR no debe detener cámara ni polling."""


class SensorPIR:
    """Encapsula GPIO Zero; su callback breve delega la captura a Qt."""
    def __init__(self, pin_bcm: str, al_detectar: Callable[[], None]) -> None:
        self.pin_bcm, self.al_detectar, self._sensor = pin_bcm, al_detectar, None

    def iniciar(self) -> None:
        if not self.pin_bcm:
            raise ErrorPIR("PIR_PIN_BCM no está configurado.")
        try:
            # MotionSensor usa numeración BCM y registra detecciones sin un bucle
            # ocupado; GPIO Zero funciona en Raspberry Pi 3 B+ con Raspberry Pi OS.
            from gpiozero import MotionSensor
            self._sensor = MotionSensor(int(self.pin_bcm))
            self._sensor.when_motion = self.al_detectar
        except Exception as exc:
            raise ErrorPIR("No se pudo inicializar el sensor PIR.") from exc

    def cerrar(self) -> None:
        if self._sensor:
            self._sensor.close()
            self._sensor = None
