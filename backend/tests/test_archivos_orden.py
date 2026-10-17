"""Pruebas del orden cronológico de metadatos de captura."""
from datetime import datetime
import unittest

from routers.archivos import _fecha_ordenable


class OrdenArchivosTests(unittest.TestCase):
    def test_interpreta_formato_heredado_y_formato_actual(self):
        heredado = {"fecha_hora": "26-08-2026 15:30:05"}
        actual = {"fecha_hora": "2026-10-14 18:52:16"}

        ordenados = sorted((actual, heredado), key=_fecha_ordenable, reverse=True)

        self.assertEqual(ordenados, [actual, heredado])

    def test_fecha_no_reconocida_no_impide_listar(self):
        self.assertEqual(_fecha_ordenable({"fecha_hora": "sin formato"}), datetime.min)


if __name__ == "__main__":
    unittest.main()
