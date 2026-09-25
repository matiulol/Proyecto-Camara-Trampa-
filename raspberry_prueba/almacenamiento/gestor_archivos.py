"""Organiza las capturas locales de una camara en la tarjeta SD."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ArchivoCaptura:
    """Informacion lista para mostrar sobre una captura almacenada."""

    ruta: Path
    tipo: str
    fecha: str
    hora: str

    @property
    def nombre(self) -> str:
        return self.ruta.name


class GestorArchivos:
    """Crea rutas y lista los archivos de una unica camara local."""

    def __init__(self, camara_id: str, directorio_base: Path | None = None) -> None:
        if not camara_id or not camara_id.replace("_", "").isalnum():
            raise ValueError("El identificador de camara solo puede contener letras, numeros y guiones bajos.")

        if directorio_base is None:
            directorio_base = Path(__file__).resolve().parents[1] / "archivos"

        self.camara_id = camara_id
        self.directorio_camara = Path(directorio_base) / camara_id
        self.directorio_fotos = self.directorio_camara / "fotos"
        self.directorio_videos = self.directorio_camara / "videos"
        self.crear_estructura()

    def crear_estructura(self) -> None:
        """Garantiza que las carpetas de destino existen antes de capturar."""
        self.directorio_fotos.mkdir(parents=True, exist_ok=True)
        self.directorio_videos.mkdir(parents=True, exist_ok=True)

    def siguiente_ruta_foto(self) -> Path:
        return self._siguiente_ruta(self.directorio_fotos, "foto", ".jpg")

    def siguiente_ruta_video(self) -> Path:
        return self._siguiente_ruta(self.directorio_videos, "video", ".mp4")

    def _siguiente_ruta(self, directorio: Path, prefijo: str, extension: str) -> Path:
        self.crear_estructura()
        mayor_indice = 0

        for archivo in directorio.glob(f"{prefijo}_*{extension}"):
            texto_indice = archivo.stem.removeprefix(f"{prefijo}_")
            if texto_indice.isdigit():
                mayor_indice = max(mayor_indice, int(texto_indice))

        indice = mayor_indice + 1
        while True:
            ruta = directorio / f"{prefijo}_{indice:03d}{extension}"
            if not ruta.exists():
                return ruta
            indice += 1

    def listar_archivos(self) -> list[ArchivoCaptura]:
        """Devuelve fotos y videos ordenados desde el mas reciente."""
        self.crear_estructura()
        archivos: list[ArchivoCaptura] = []

        for directorio, tipo in ((self.directorio_fotos, "Foto"), (self.directorio_videos, "Video")):
            for ruta in directorio.iterdir():
                if ruta.is_file():
                    fecha_hora = datetime.fromtimestamp(ruta.stat().st_mtime)
                    archivos.append(
                        ArchivoCaptura(
                            ruta=ruta,
                            tipo=tipo,
                            fecha=fecha_hora.strftime("%d/%m/%Y"),
                            hora=fecha_hora.strftime("%H:%M:%S"),
                        )
                    )

        return sorted(archivos, key=lambda archivo: archivo.ruta.stat().st_mtime, reverse=True)
