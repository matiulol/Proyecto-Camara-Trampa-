"""Pruebas de ciclo de vida del cliente HTTP del Dashboard."""
import unittest
from unittest.mock import Mock, patch

from services.cliente_api import ClienteApi, ErrorApi, comprobar_conexion_backend


class ClienteApiTests(unittest.TestCase):
    def test_cerrar_libera_la_sesion(self) -> None:
        cliente = ClienteApi()
        cliente.sesion = Mock()

        cliente.cerrar()

        cliente.sesion.close.assert_called_once()

    def test_comprobacion_cierra_sesion_tambien_si_falla(self) -> None:
        instancia = Mock()
        instancia.listar_camaras.side_effect = ErrorApi("sin backend")
        with patch("services.cliente_api.ClienteApi", return_value=instancia):
            conectado, mensaje = comprobar_conexion_backend()

        self.assertFalse(conectado)
        self.assertEqual(mensaje, "sin backend")
        instancia.cerrar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
