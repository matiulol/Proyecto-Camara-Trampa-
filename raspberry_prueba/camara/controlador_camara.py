"""Controlador de Picamera2 para fotos y videos locales."""

from __future__ import annotations

from pathlib import Path


class ErrorCamara(RuntimeError):
    """Error recuperable al inicializar o usar la camara."""


class ControladorCamara:
    """Encapsula el ciclo de vida de una camara Raspberry Pi con Picamera2."""

    def __init__(self, tamano_foto: tuple[int, int], bitrate_video: int) -> None:
        self.tamano_foto = tamano_foto
        self.bitrate_video = bitrate_video
        self._camara = None
        self._encoder = None
        self._salida = None
        self._grabando = False

    @property
    def grabando(self) -> bool:
        return self._grabando

    @property
    def disponible(self) -> bool:
        return self._camara is not None

    def inicializar(self) -> None:
        """Abre y prepara la camara CSI con una configuracion apta para video."""
        if self._camara is not None:
            return

        try:
            from picamera2 import Picamera2

            camara = Picamera2()
            self._camara = camara
            configuracion = camara.create_video_configuration(main={"size": self.tamano_foto})
            camara.configure(configuracion)
            camara.start()
        except Exception as exc:
            self.cerrar()
            raise ErrorCamara(self._mensaje_error("No se pudo inicializar la camara", exc)) from exc

    def tomar_foto(self, destino: Path) -> None:
        """Captura una foto JPEG en la ruta local indicada."""
        self.inicializar()
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            self._camara.capture_file(str(destino))
        except Exception as exc:
            raise ErrorCamara(self._mensaje_error("No se pudo tomar la foto", exc)) from exc

    def iniciar_video(self, destino: Path) -> None:
        """Inicia una grabacion H.264 encapsulada como MP4 mediante ffmpeg."""
        if self._grabando:
            raise ErrorCamara("Ya hay una grabacion en curso.")

        self.inicializar()
        try:
            from picamera2.encoders import H264Encoder
            from picamera2.outputs import FfmpegOutput

            destino.parent.mkdir(parents=True, exist_ok=True)
            encoder = H264Encoder(bitrate=self.bitrate_video)
            salida = FfmpegOutput(str(destino))
            self._camara.start_recording(encoder, salida)
            self._encoder = encoder
            self._salida = salida
            self._grabando = True
        except Exception as exc:
            self._encoder = None
            self._salida = None
            raise ErrorCamara(self._mensaje_error("No se pudo iniciar el video", exc)) from exc

    def detener_video(self) -> None:
        """Finaliza la grabacion actual y libera el encoder sin cerrar la camara."""
        if not self._grabando:
            return

        try:
            self._camara.stop_recording()
        except Exception as exc:
            raise ErrorCamara(self._mensaje_error("No se pudo detener el video", exc)) from exc
        finally:
            self._grabando = False
            self._encoder = None
            self._salida = None

    def cerrar(self) -> None:
        """Detiene las operaciones activas y libera el recurso de camara."""
        if self._camara is None:
            return

        try:
            if self._grabando:
                self.detener_video()
            self._camara.stop()
            self._camara.close()
        except Exception:
            # Durante el cierre no hay una accion util para el usuario; se libera el estado local.
            pass
        finally:
            self._camara = None
            self._encoder = None
            self._salida = None
            self._grabando = False

    @staticmethod
    def _mensaje_error(contexto: str, error: Exception) -> str:
        return f"{contexto}. {error}"
