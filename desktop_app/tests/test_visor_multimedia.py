"""Pruebas del visor integrado sin FastAPI, B2 ni hardware multimedia real."""

import os
import unittest
from unittest.mock import Mock, patch

# Qt debe usar un backend sin ventana para que la decodificación de pixmaps se
# pueda comprobar en integración continua y en equipos sin monitor disponible.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtGui import QCloseEvent, QImage
from PySide6.QtWidgets import QApplication, QHeaderView, QSplitter

from widgets.ventana_principal import (
    VentanaPrincipal,
    clasificar_archivo_multimedia,
    decodificar_imagen,
    origen_archivo,
)


class VisorMultimediaTests(unittest.TestCase):
    """Comprueba el contrato real de metadatos y fallos de contenido de imagen."""

    @classmethod
    def setUpClass(cls) -> None:
        """Crea una única aplicación Qt, requisito previo para QPixmap."""
        cls.aplicacion = QApplication.instance() or QApplication([])

    def test_reconoce_imagen_confirmada_por_el_backend(self) -> None:
        """``imagen`` e ``image/jpeg`` deben abrirse como fotografía, no fallar."""
        archivo = {
            "tipo": "imagen",
            "tipo_contenido": "image/jpeg",
            "nombre_archivo": "captura.jpg",
        }
        self.assertEqual(clasificar_archivo_multimedia(archivo, {"tipo": "foto"}), "imagen")

    def test_decodifica_imagen_y_rechaza_contenido_invalido(self) -> None:
        """La descarga válida crea un pixmap y bytes corruptos devuelven ``None``."""
        imagen_origen = QImage(1, 1, QImage.Format.Format_RGB32)
        imagen_origen.fill(0xFF2E6F40)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.assertTrue(imagen_origen.save(buffer, "PNG"))
        imagen = decodificar_imagen(bytes(buffer.data()))
        self.assertIsNotNone(imagen)
        self.assertEqual(imagen.size().width(), 1)
        self.assertIsNone(decodificar_imagen(b"contenido que no es una imagen"))

    def test_mensaje_de_error_no_necesita_red_ni_hardware(self) -> None:
        """El visor vuelve a un estado legible ante una descarga o URL fallida."""
        ventana = VentanaPrincipal()
        ventana.pestana_pruebas = ventana._crear_tab_peticiones()
        ventana._mostrar_mensaje_visor("No se pudo cargar la fotografía seleccionada.")
        self.assertEqual(ventana.visor_peticiones.text(), "No se pudo cargar la fotografía seleccionada.")
        ventana.deleteLater()

    def test_cierre_detiene_el_dashboard_y_libera_el_cliente(self) -> None:
        """Cerrar no deja una sesión HTTP ni polling activos en segundo plano."""
        ventana = VentanaPrincipal()
        api = Mock()
        ventana.api = api
        ventana._dashboard_activo = True

        ventana.closeEvent(QCloseEvent())

        self.assertFalse(ventana._dashboard_activo)
        api.cerrar.assert_called_once()

    def test_cierre_tolera_un_visor_qt_ya_destruido(self) -> None:
        """Cerrar sesión no debe impedir el cierre posterior de la aplicación."""
        class ReproductorDestruido:
            def stop(self) -> None:
                raise RuntimeError("Internal C++ object already deleted")

        class VisorDestruido:
            reproductor = ReproductorDestruido()

        ventana = VentanaPrincipal()
        ventana.api = Mock()
        ventana.visor_multimedia_peticiones = VisorDestruido()

        ventana.closeEvent(QCloseEvent())

        ventana.api.cerrar.assert_called_once()

    def _ventana_con_camara(self, archivos: list[dict]) -> VentanaPrincipal:
        """Crea el mínimo Dashboard necesario para probar el panel Cámaras."""
        class ApiFalsa:
            def listar_camaras(self) -> list[dict]:
                return [{"_id": "camara001", "nombre": "Norte", "ubicacion": "Sendero", "estado": "activa", "fecha_instalacion": "2026-10-01"}]

            def listar_archivos_camara(self, _identificador: str) -> list[dict]:
                return archivos

        ventana = VentanaPrincipal()
        ventana.pestana_pruebas = ventana._crear_tab_camaras()
        ventana._crear_tab_peticiones()
        ventana.api = ApiFalsa()
        ventana.refrescar_camaras()
        ventana.tabla_camaras.selectRow(0)
        self.aplicacion.processEvents()
        return ventana

    def test_tabla_camaras_muestra_metadatos_y_origen_real(self) -> None:
        """El origen usa relaciones explícitas, nunca el nombre del archivo."""
        archivos = [
            {"_id": "uno", "nombre_archivo": "captura-01.jpg", "tipo": "imagen", "fecha_hora": "2026-10-14 10:00", "peticion_id": "pet-1", "estado_subida": "confirmada"},
            {"_id": "dos", "nombre_archivo": "evento.mp4", "tipo_contenido": "video/mp4", "fecha_captura": "2026-10-14 11:00", "id_evento": "evt-1", "estado": "procesado"},
            {"_id": "tres", "nombre_archivo": "peticion-en-el-nombre.jpg", "tipo": "imagen"},
        ]
        ventana = self._ventana_con_camara(archivos)

        self.assertEqual(ventana.tabla_archivos_camara.rowCount(), 3)
        self.assertEqual(ventana.tabla_archivos_camara.item(0, 3).text(), "Petición")
        self.assertEqual(ventana.tabla_archivos_camara.item(1, 3).text(), "Evento")
        self.assertEqual(ventana.tabla_archivos_camara.item(2, 3).text(), "Desconocido")
        self.assertEqual(ventana.tabla_archivos_camara.item(1, 2).text(), "2026-10-14 11:00")
        self.assertEqual(origen_archivo(archivos[2]), "Desconocido")
        ventana.deleteLater()

    def test_seleccionar_archivo_camara_no_visualiza(self) -> None:
        """La selección de fila no pide URL ni inicia una descarga."""
        ventana = self._ventana_con_camara(
            [{"_id": "uno", "nombre_archivo": "captura.jpg", "tipo": "imagen"}]
        )
        abiertos: list[str] = []
        ventana._visualizar_archivo_camara = lambda archivo: abiertos.append(archivo["_id"])

        ventana.tabla_archivos_camara.selectRow(0)
        self.aplicacion.processEvents()
        self.assertEqual(abiertos, [])

        ventana.tabla_archivos_camara.cellWidget(0, 5).click()
        self.assertEqual(abiertos, ["uno"])
        ventana.deleteLater()

    def test_visualizar_camara_usa_su_visor_independiente(self) -> None:
        """Una visualización de Cámara no modifica el contenido de Peticiones."""
        ventana = self._ventana_con_camara(
            [{"_id": "uno", "nombre_archivo": "captura.jpg", "tipo": "imagen"}]
        )

        class ApiConEnlace:
            def enlace_visualizacion(self, archivo_id: str) -> dict:
                self.archivo_id = archivo_id
                return {"url": "https://ejemplo.invalid/captura-firmada"}

        api = ApiConEnlace()
        ventana.api = api
        presentados: list[str] = []
        ventana.visor_peticiones.setText("Peticiones sin cambios")
        ventana.visor_multimedia_camaras.presentar = lambda archivo, _peticion, _respuesta: presentados.append(archivo["_id"])
        ventana._visualizar_archivo_camara({"_id": "uno", "tipo": "imagen"})

        self.assertEqual(api.archivo_id, "uno")
        self.assertEqual(presentados, ["uno"])
        self.assertEqual(ventana.visor_peticiones.text(), "Peticiones sin cambios")
        ventana.deleteLater()

    def test_camara_sin_archivos_y_error_de_enlace_se_informan_en_seccion(self) -> None:
        """No hay diálogos para una cámara vacía ni para un enlace fallido."""
        ventana = self._ventana_con_camara([])
        self.assertEqual(ventana.tabla_archivos_camara.rowCount(), 0)
        self.assertIn("no tiene archivos", ventana.estado_archivos_camara_label.text().lower())

        class ApiConError:
            def enlace_visualizacion(self, _archivo_id: str) -> dict:
                from services.cliente_api import ErrorApi
                raise ErrorApi("vencida")

        ventana.api = ApiConError()
        ventana._visualizar_archivo_camara({"_id": "no-disponible", "tipo": "imagen"})
        self.assertIn("No se pudo obtener", ventana.visor_camaras.text())
        ventana.deleteLater()

    def test_seleccionar_peticion_no_abre_y_boton_visualizar_si(self) -> None:
        """La selección es pasiva; sólo el botón de la fila inicia el visor."""
        class ApiFalsa:
            def listar_archivos_camara(self, _identificador: str) -> list[dict]:
                return []

            def listar_archivos_evento(self, _identificador: str) -> list[dict]:
                return []

            def listar_archivos_peticion(self, _identificador: str) -> list[dict]:
                return [{"_id": "archivo-1", "estado_subida": "confirmada", "tipo": "imagen"}]

        ventana = VentanaPrincipal()
        ventana.pestana_pruebas = ventana._crear_tab_peticiones()
        ventana._dashboard_activo = True
        ventana.api = ApiFalsa()
        abiertos: list[str] = []
        ventana._visualizar_archivo = lambda archivo, peticion=None: abiertos.append(archivo["_id"])
        ventana._recibir_peticiones(
            [{
                "_id": "peticion-1",
                "camara_id": "camara001",
                "tipo": "foto",
                "estado": "ejecutado",
                "fecha_hora": "2026-10-13 10:00:00",
                "archivo_id": "archivo-1",
                "nombre_archivo": "foto.jpg",
            }]
        )

        ventana.tabla_peticiones.selectRow(0)
        self.aplicacion.processEvents()
        self.assertEqual(abiertos, [])

        ventana.tabla_peticiones.cellWidget(0, 6).click()
        self.assertEqual(abiertos, ["archivo-1"])
        ventana.deleteLater()

    def test_el_respaldo_abre_solo_la_url_temporal_actual(self) -> None:
        """El botón alternativo conserva la apertura externa sin diálogos propios."""
        ventana = VentanaPrincipal()
        ventana.pestana_pruebas = ventana._crear_tab_peticiones()
        ventana.visor_multimedia_peticiones._url_visualizacion_actual = QUrl("https://ejemplo.invalid/archivo-firmado")
        with patch("widgets.ventana_principal.QDesktopServices.openUrl", return_value=True) as abrir:
            ventana._abrir_visualizacion_en_navegador()
        abrir.assert_called_once_with(ventana.visor_multimedia_peticiones._url_visualizacion_actual)
        ventana.deleteLater()

    def test_evento_usa_un_visor_distinto_al_de_peticion(self) -> None:
        """Visualizar un evento no cambia la URL ni el contenido de Peticiones."""
        class ApiFalsa:
            def listar_archivos_evento(self, identificador: str) -> list[dict]:
                self.identificador = identificador
                return [{"_id": "archivo-evento", "tipo": "imagen", "estado_subida": "confirmada"}]

            def enlace_visualizacion(self, archivo_id: str) -> dict:
                self.archivo_id = archivo_id
                return {"url": "https://ejemplo.invalid/evento-firmado"}

        ventana = VentanaPrincipal()
        ventana.pestana_pruebas = ventana._crear_tab_peticiones()
        ventana._crear_tab_eventos()
        api = ApiFalsa()
        ventana.api = api
        presentados: list[str] = []
        ventana.visor_peticiones.setText("Peticiones sin cambios")
        ventana.visor_multimedia_eventos.presentar = (
            lambda archivo, _peticion, _respuesta: presentados.append(archivo["_id"])
        )

        ventana._mostrar_archivos("evento", "evento-1")

        self.assertEqual(api.identificador, "evento-1")
        self.assertEqual(api.archivo_id, "archivo-evento")
        self.assertEqual(presentados, ["archivo-evento"])
        self.assertEqual(ventana.visor_peticiones.text(), "Peticiones sin cambios")
        self.assertIn("evento", ventana.visor_eventos.text().lower())
        ventana.deleteLater()

    def test_tablas_conservan_ancho_manual_y_splitters_difieren_redimensionamiento(self) -> None:
        """Una recarga de filas no debe recalcular columnas ni trabajo por píxel."""
        ventana = VentanaPrincipal()
        ventana.pestana_pruebas = ventana._crear_tab_peticiones()
        pestana_eventos = ventana._crear_tab_eventos()
        tabla = ventana.tabla_eventos
        encabezado = tabla.horizontalHeader()

        self.assertEqual(
            encabezado.sectionResizeMode(0), QHeaderView.ResizeMode.Interactive
        )
        tabla.setColumnWidth(0, 237)
        tabla.setRowCount(1)
        ventana._llenar_fila(
            tabla,
            0,
            ["evento-1", "Norte", "2026-10-17", "12:00", "PIR", "Movimiento", "ejecutado"],
            {"_id": "evento-1"},
        )
        self.assertEqual(tabla.columnWidth(0), 237)

        splitters = pestana_eventos.findChildren(QSplitter)
        self.assertEqual(len(splitters), 1)
        self.assertFalse(splitters[0].opaqueResize())
        ventana.deleteLater()


if __name__ == "__main__":
    unittest.main()
