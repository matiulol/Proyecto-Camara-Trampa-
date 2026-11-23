"""Punto de entrada de la aplicación Raspberry y composición de sus módulos.

Inicializa Qt, configura almacenamiento, cámara y clientes HTTP, y conecta el
sensor PIR opcional con su coordinador independiente de la interfaz.
"""

from __future__ import annotations

# ``sys.argv`` conserva los argumentos que QApplication puede reconocer y
# SystemExit devuelve al sistema operativo el resultado del ciclo de eventos.
import sys

# QApplication es el objeto raíz de una aplicación PySide6: debe existir antes
# de crear controles y se encarga de despachar señales, clics y temporizadores.
from PySide6.QtWidgets import QApplication

# Cada import corresponde a una responsabilidad. El punto de entrada los une
# por composición: crea objetos especializados y los entrega a la ventana, sin
# mezclar captura, almacenamiento ni HTTP en una única clase.
from almacenamiento.gestor_archivos import GestorArchivos
from camara.controlador_camara import ControladorCamara
from comunicacion.cliente_api import ClienteAPI
from configuracion import (
    CAMARA_ID,
    DURACION_VIDEO_SEGUNDOS,
    INTERVALO_CONSULTA_MS,
    TAMANO_FOTO,
    TASA_BITS_VIDEO,
    URL_BACKEND,
    PIR_PIN_BCM, PIR_HABILITADO_LOCAL, INTERVALO_CONFIGURACION_PIR_MS,
)
from interfaz.ventana_principal import VentanaPrincipal
from sensor.capturador_pir import CapturadorPIR
from sensor.sensor_pir import ErrorPIR, SensorPIR


def iniciar_aplicacion() -> int:
    """Inicia la aplicación de escritorio de la Raspberry y devuelve su salida.

    El flujo es: crear ``QApplication``; construir los objetos de archivos,
    cámara y HTTP; inyectarlos en ``VentanaPrincipal``; mostrarla; y por último
    entregar el control a ``exec``. ``QApplication`` es el objeto central de
    PySide6: mantiene la cola de eventos, distribuye clics y señales, y gestiona
    la vida de las ventanas. El punto de entrada no captura ni hace HTTP
    directamente; esa separación es composición y evita una clase gigante.
    """
    # QApplication debe construirse antes que cualquier QWidget. A partir de
    # aquí Qt conoce qué aplicación maneja la ventana y sus recursos visuales.
    aplicacion = QApplication(sys.argv)
    aplicacion.setApplicationName("Cámara Trampa")

    # Estas instancias representan colaboradores con una sola responsabilidad:
    # rutas locales, cámara física y comunicación REST, respectivamente.
    gestor = GestorArchivos(CAMARA_ID)
    controlador = ControladorCamara(TAMANO_FOTO, TASA_BITS_VIDEO)
    # La URL y el identificador se leen desde configuración para que el mismo
    # programa pueda instalarse en otras Raspberry sin editar esta función.
    cliente = ClienteAPI(URL_BACKEND)
    # La ventana recibe los objetos ya preparados en vez de crearlos por dentro.
    # Así coordina el caso de uso (consultar y capturar), mientras cada objeto
    # conserva su especialidad y puede probarse de forma independiente.
    ventana = VentanaPrincipal(
        controlador,
        gestor,
        cliente,
        INTERVALO_CONSULTA_MS,
        DURACION_VIDEO_SEGUNDOS,
        INTERVALO_CONFIGURACION_PIR_MS,
    )
    capturador_pir = None
    sensor = None
    if PIR_HABILITADO_LOCAL:
        # El sensor y el coordinador pertenecen al proceso de la Raspberry, no
        # a la ventana: la notificación GPIO no emite señales Qt ni modifica la interfaz gráfica.
        cliente_pir = ClienteAPI(URL_BACKEND)
        capturador_pir = CapturadorPIR(controlador, gestor, cliente_pir, DURACION_VIDEO_SEGUNDOS)
        sensor = SensorPIR(PIR_PIN_BCM, capturador_pir.detectar_movimiento, capturador_pir.finalizar_movimiento)
        try:
            sensor.iniciar()
        except ErrorPIR as excepcion:
            # El sensor es opcional: un fallo GPIO no impide que el monitor siga
            # atendiendo las peticiones manuales, pero queda visible en consola.
            print(f"No se pudo iniciar el sensor PIR: {excepcion}")
            sensor = None
    # Mostrar la ventana no bloquea: Qt comienza a atender sus eventos al
    # entrar en ``exec`` y termina cuando el usuario cierra la aplicación.
    ventana.show()
    # ``exec`` inicia la cola de eventos de Qt. Mientras está activa, Qt entrega
    # las señales del temporizador, los clics de los botones y los avisos de los reproductores
    # sus señales; sin este ciclo la ventana se mostraría y cerraría enseguida.
    try:
        return aplicacion.exec()
    finally:
        if sensor:
            sensor.cerrar()
        if capturador_pir:
            capturador_pir.cerrar()
        controlador.cerrar()


if __name__ == "__main__":
    # Este guardia evita ejecutar la interfaz al importar el módulo desde una
    # prueba. SystemExit entrega a la consola el código que devuelve Qt.
    raise SystemExit(iniciar_aplicacion())
