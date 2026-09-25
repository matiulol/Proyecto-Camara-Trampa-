from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from almacenamiento.gestor_archivos import GestorArchivos


class GestorArchivosTests(unittest.TestCase):
    def test_crea_carpetas_y_genera_nombres_sin_sobrescribir(self) -> None:
        with tempfile.TemporaryDirectory() as temporal:
            gestor = GestorArchivos("camara001", Path(temporal))
            primera_foto = gestor.siguiente_ruta_foto()
            primera_foto.touch()
            segunda_foto = gestor.siguiente_ruta_foto()
            primer_video = gestor.siguiente_ruta_video()

            self.assertTrue(gestor.directorio_fotos.is_dir())
            self.assertTrue(gestor.directorio_videos.is_dir())
            self.assertEqual(primera_foto.name, "foto_001.jpg")
            self.assertEqual(segunda_foto.name, "foto_002.jpg")
            self.assertEqual(primer_video.name, "video_001.mp4")

    def test_lista_fotos_y_videos_con_metadatos(self) -> None:
        with tempfile.TemporaryDirectory() as temporal:
            gestor = GestorArchivos("camara001", Path(temporal))
            foto = gestor.directorio_fotos / "foto_001.jpg"
            video = gestor.directorio_videos / "video_001.mp4"
            foto.touch()
            video.touch()

            archivos = gestor.listar_archivos()

            self.assertEqual({archivo.nombre for archivo in archivos}, {foto.name, video.name})
            self.assertEqual({archivo.tipo for archivo in archivos}, {"Foto", "Video"})
            self.assertTrue(all(archivo.fecha and archivo.hora for archivo in archivos))


if __name__ == "__main__":
    unittest.main()
