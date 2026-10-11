"""Pruebas unitarias del almacenamiento local que no requieren una Raspberry.

Una prueba automatizada ejecuta un comportamiento pequeño y comprueba su
resultado de forma repetible. En este caso se prueba el gestor de archivos sin
cámara, interfaz ni tarjeta SD real; si una modificación rompe el algoritmo de
rutas, la prueba lo informa antes de usar el programa en el dispositivo.
"""

from __future__ import annotations

# sys ajusta la ruta de imports de la prueba; tempfile aporta una carpeta
# descartable y unittest ejecuta aserciones sin depender de una Raspberry.
import sys
import tempfile
import unittest
from pathlib import Path

# La prueba se ejecuta desde ``tests``; se agrega la raíz de la aplicación para
# importar el módulo real sin instalarlo como paquete global de Python.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from almacenamiento.gestor_archivos import GestorArchivos


class GestorArchivosTests(unittest.TestCase):
    """Agrupa pruebas de la regla de no sobrescritura y de los metadatos.

    Hereda de ``unittest.TestCase`` para obtener aserciones. Una aserción compara
    el resultado real con el esperado: si no coinciden, la prueba falla y señala
    qué contrato de ``GestorArchivos`` dejó de cumplirse.
    """

    def test_crea_carpetas_y_genera_nombres_sin_sobrescribir(self) -> None:
        """Verifica estructura y numeración sin tocar la tarjeta SD.

        ``TemporaryDirectory`` crea una carpeta aislada y la borra al salir del
        bloque. Se marca la primera ruta como ocupada con ``touch`` y luego se
        comprueba que el gestor propone ``foto_002.jpg`` en vez de sobrescribir
        ``foto_001.jpg``. Las aserciones también verifican que foto y video usan
        carpetas y extensiones diferentes.
        """
        with tempfile.TemporaryDirectory() as temporal:
            # El gestor usa una base temporal explícita para que la prueba nunca
            # cree ni borre archivos de la instalación real de la Raspberry.
            gestor = GestorArchivos("camara001", Path(temporal))
            primera_foto = gestor.siguiente_ruta_foto()
            # ``touch`` crea un archivo vacío: alcanza para simular que la ruta
            # ya está ocupada y comprobar la regla de no sobrescritura.
            primera_foto.touch()
            segunda_foto = gestor.siguiente_ruta_foto()
            primer_video = gestor.siguiente_ruta_video()

            # Cada aserción expresa un resultado esperado del contrato público
            # del gestor. Si una falla, unittest informa cuál se incumplió.
            self.assertTrue(gestor.directorio_fotos.is_dir())
            self.assertTrue(gestor.directorio_videos.is_dir())
            self.assertEqual(primera_foto.name, "foto_001.jpg")
            self.assertEqual(segunda_foto.name, "foto_002.jpg")
            self.assertEqual(primer_video.name, "video_001.mp4")

    def test_lista_fotos_y_videos_con_metadatos(self) -> None:
        """Comprueba que fotos y videos producen una representación uniforme.

        Se simula un JPEG y un MP4 vacíos porque para esta prueba interesa la
        estructura de rutas, no su contenido multimedia. Las aserciones finales
        verifican que ``listar_archivos`` los convierte en objetos con nombre,
        tipo y fecha/hora utilizables por la interfaz.
        """
        with tempfile.TemporaryDirectory() as temporal:
            gestor = GestorArchivos("camara001", Path(temporal))
            # Se crean archivos vacíos con extensiones reales para representar
            # los dos tipos que reconoce la aplicación, sin requerir JPEG/MP4.
            foto = gestor.directorio_fotos / "foto_001.jpg"
            video = gestor.directorio_videos / "video_001.mp4"
            foto.touch()
            video.touch()

            archivos = gestor.listar_archivos()

            # Los conjuntos no dependen del orden: aquí interesa comprobar que
            # los dos archivos aparecen y que cada uno conserva su metadato.
            self.assertEqual({archivo.nombre for archivo in archivos}, {foto.name, video.name})
            self.assertEqual({archivo.tipo for archivo in archivos}, {"Foto", "Video"})
            self.assertTrue(all(archivo.fecha and archivo.hora for archivo in archivos))


if __name__ == "__main__":
    # Permite ejecutar este archivo directamente; el descubridor de unittest
    # localiza los métodos que empiezan con ``test_`` y muestra sus resultados.
    unittest.main()
