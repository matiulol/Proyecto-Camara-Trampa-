"""Pruebas aisladas de los índices usados por las consultas de ANICAM."""
import unittest
from unittest.mock import patch

from pymongo.errors import OperationFailure

from database.connection import INDICES_CONSULTA, preparar_indices


class ColeccionFalsa:
    """Registra creaciones de índice sin conectar una base MongoDB real."""

    def __init__(self, falla: bool = False) -> None:
        self.falla = falla
        self.llamadas: list[tuple[list[tuple[str, int]], str]] = []

    def create_index(self, campos: list[tuple[str, int]], name: str) -> None:
        if self.falla:
            raise OperationFailure("sin permiso")
        self.llamadas.append((campos, name))


class BaseFalsa:
    def __init__(self, falla: bool = False) -> None:
        self.colecciones: dict[str, ColeccionFalsa] = {}
        self.falla = falla

    def __getitem__(self, nombre: str) -> ColeccionFalsa:
        if nombre not in self.colecciones:
            self.colecciones[nombre] = ColeccionFalsa(self.falla)
        return self.colecciones[nombre]


class IndicesConsultaTests(unittest.TestCase):
    def test_crea_todos_los_indices_no_unicos_esperados(self) -> None:
        base = BaseFalsa()

        self.assertTrue(preparar_indices(base))

        creados = {
            nombre
            for coleccion in base.colecciones.values()
            for _campos, nombre in coleccion.llamadas
        }
        self.assertEqual(creados, {nombre for _coleccion, _campos, nombre in INDICES_CONSULTA})

    def test_informa_y_no_interrumpe_si_no_puede_crear_indices(self) -> None:
        with patch("database.connection.logger.warning") as advertencia:
            self.assertFalse(preparar_indices(BaseFalsa(falla=True)))

        advertencia.assert_called_once()


if __name__ == "__main__":
    unittest.main()
