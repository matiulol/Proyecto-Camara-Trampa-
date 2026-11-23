"""Organiza las capturas locales de una cámara en la tarjeta SD.

MongoDB conserva metadatos y la relación con una petición; los bytes de las
fotos y videos permanecen en la Raspberry. Este módulo concentra esa decisión
de almacenamiento para no mezclar rutas del sistema de archivos con la interfaz.
"""

from __future__ import annotations

# dataclass evita escribir a mano el constructor de este objeto de datos;
# datetime genera metadatos legibles y Path gestiona rutas sin concatenarlas.
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from stat import S_ISREG


@dataclass(frozen=True)
class ArchivoCaptura:
    """Valor inmutable con los datos que la interfaz necesita mostrar.

    ``dataclass(frozen=True)`` evita que una fila de la interfaz modifique por
    accidente la ruta real de una captura ya almacenada. Es un objeto de datos:
    reúne ruta, tipo, fecha y hora en una sola unidad, en lugar de devolver
    listas paralelas que podrían desordenarse.
    """

    ruta: Path
    tipo: str
    fecha: str
    hora: str

    @property
    def nombre(self) -> str:
        """Expone solo el nombre visible, sin revelar la ruta completa en la tabla."""
        return self.ruta.name


class GestorArchivos:
    """Crea rutas y lista los archivos de una única cámara local.

    Cada instancia representa una cámara identificada por ``CAMARA_ID``. La
    separación por cámara evita que una petición de otro dispositivo reutilice o
    mezcle archivos de la tarjeta SD.
    """

    def __init__(self, camara_id: str, directorio_base: Path | None = None) -> None:
        """Prepara la estructura ``archivos/<camara_id>/{fotos,videos}``.

        Recibe el identificador de cámara y, opcionalmente, una carpeta base
        útil para pruebas. Si no se recibe, usa ``raspberry_pi/archivos``.
        Con ``Path /`` se construyen rutas de forma portable, sin concatenar
        texto ni depender del separador de Windows o Linux. La validación
        restringe el identificador a un segmento de ruta seguro; así un valor de
        configuración no puede escapar hacia otras carpetas mediante ``..``.
        """
        # Antes de construir rutas se descarta un identificador vacío o con
        # separadores. Es una validación defensiva: CAMARA_ID forma parte de la
        # ruta y no debe permitir salir del directorio de almacenamiento.
        if not camara_id or not camara_id.replace("_", "").isalnum():
            raise ValueError("El identificador de cámara solo puede contener letras, números y guiones bajos.")

        if directorio_base is None:
            # ``__file__`` ubica este módulo instalado y ``parents[1]`` vuelve a
            # la raíz de raspberry_pi. Así la ruta no depende del directorio
            # desde el que el usuario haya ejecutado ``python inicio.py``.
            directorio_base = Path(__file__).resolve().parents[1] / "archivos"

        self.camara_id = camara_id
        # Se separan fotos y videos porque tienen extensiones, tamaños y formas
        # de visualización diferentes. La carpeta de cámara evita mezclar los
        # resultados de dos dispositivos que comparten la misma tarjeta o PC.
        self.directorio_camara = Path(directorio_base) / camara_id
        self.directorio_fotos = self.directorio_camara / "fotos"
        self.directorio_videos = self.directorio_camara / "videos"
        self.crear_estructura()

    def crear_estructura(self) -> None:
        """Garantiza que las carpetas de fotos y videos existen antes de capturar.

        ``parents=True`` crea también directorios superiores faltantes y
        ``exist_ok=True`` hace la operación idempotente: puede repetirse antes
        de cada captura sin fallar si las carpetas ya fueron creadas.
        """
        self.directorio_fotos.mkdir(parents=True, exist_ok=True)
        self.directorio_videos.mkdir(parents=True, exist_ok=True)

    def siguiente_ruta_foto(self) -> Path:
        """Reserva la próxima ruta disponible para una foto JPEG."""
        return self._siguiente_ruta(self.directorio_fotos, "foto", ".jpg")

    def siguiente_ruta_video(self) -> Path:
        """Reserva la próxima ruta disponible para un video MP4."""
        return self._siguiente_ruta(self.directorio_videos, "video", ".mp4")

    def _siguiente_ruta(self, directorio: Path, prefijo: str, extension: str) -> Path:
        """Calcula un nombre secuencial sin sobrescribir capturas existentes.

        Recibe el directorio y el formato de cada tipo: JPEG para fotos y MP4
        para videos. Examina el mayor índice ya guardado y además verifica la
        existencia final en un bucle. Así conserva el historial aunque se borre
        una captura intermedia o se copie un archivo manualmente a la carpeta;
        por ejemplo, después de ``foto_004.jpg`` propone ``foto_005.jpg``.
        """
        self.crear_estructura()
        mayor_indice = 0

        # Sólo se consideran nombres generados por esta aplicación. ``glob``
        # filtra por prefijo y extensión antes de extraer el índice numérico.
        for archivo in directorio.glob(f"{prefijo}_*{extension}"):
            texto_indice = archivo.stem.removeprefix(f"{prefijo}_")
            if texto_indice.isdigit():
                mayor_indice = max(mayor_indice, int(texto_indice))

        indice = mayor_indice + 1
        while True:
            ruta = directorio / f"{prefijo}_{indice:03d}{extension}"
            # La segunda comprobación protege contra un archivo creado entre el
            # recorrido anterior y este punto. Si existe, se prueba el siguiente
            # número sin eliminar ni reemplazar una captura anterior.
            if not ruta.exists():
                return ruta
            indice += 1

    def listar_archivos(self) -> list[ArchivoCaptura]:
        """Devuelve fotos y videos ordenados desde el más reciente.

        La fecha se deriva de la modificación local porque este listado describe
        los archivos físicos de la Raspberry, no la fecha de un documento de
        MongoDB. Recorre ambos directorios, ignora subcarpetas y convierte cada
        archivo en ``ArchivoCaptura``; de ese modo la interfaz trata JPEG y MP4
        con la misma estructura. Finalmente ordena por modificación descendente
        para mostrar primero la captura más reciente.
        """
        self.crear_estructura()
        # Se conserva la marca de tiempo usada para mostrar cada archivo. Así
        # no se vuelve a ejecutar ``stat`` durante el ordenamiento, algo que se
        # nota al acumular capturas en una tarjeta SD de rendimiento limitado.
        archivos_con_marca: list[tuple[float, ArchivoCaptura]] = []

        # El mismo recorrido sirve para ambos formatos porque cada elemento se
        # normaliza como ArchivoCaptura antes de llegar a la interfaz.
        for directorio, tipo in ((self.directorio_fotos, "Foto"), (self.directorio_videos, "Video")):
            for ruta in directorio.iterdir():
                try:
                    estado = ruta.stat()
                except OSError:
                    # La cámara u otro proceso puede eliminar una captura entre
                    # el listado del directorio y esta consulta. Omitir sólo
                    # esa entrada evita que la interfaz deje de actualizarse.
                    continue
                if not S_ISREG(estado.st_mode):
                    continue
                # ``st_mtime`` es la fecha de última modificación del archivo
                # físico. Se convierte a fecha/hora legible sólo para mostrarla,
                # sin modificar el archivo ni MongoDB.
                fecha_hora = datetime.fromtimestamp(estado.st_mtime)
                archivos_con_marca.append(
                    (
                        estado.st_mtime,
                        ArchivoCaptura(
                            ruta=ruta,
                            tipo=tipo,
                            fecha=fecha_hora.strftime("%d/%m/%Y"),
                            hora=fecha_hora.strftime("%H:%M:%S"),
                        ),
                    )
                )

        # ``reverse=True`` coloca primero las capturas más recientes, que son
        # normalmente las que el usuario necesita revisar al abrir la pantalla.
        return [
            archivo
            for _marca, archivo in sorted(archivos_con_marca, key=lambda elemento: elemento[0], reverse=True)
        ]
