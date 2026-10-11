from __future__ import annotations

# ``sys.argv`` conserva los argumentos que QApplication puede reconocer y
# SystemExit devuelve al sistema operativo el resultado del ciclo de eventos.
import sys

# QApplication es el objeto raíz de una aplicación PySide6: debe existir antes
# de crear widgets y se encarga de despachar señales, clics y temporizadores.
from PySide6.QtWidgets import QApplication

# Cada import corresponde a una responsabilidad. El punto de entrada los une
# por composición: crea objetos especializados y los entrega a la ventana, sin
# mezclar captura, almacenamiento ni HTTP en una única clase.
from almacenamiento.gestor_archivos import GestorArchivos
from camara.controlador_camara import ControladorCamara
from comunicacion.cliente_backend import ClienteBackend
from config import (
    CAMARA_ID,
    DURACION_VIDEO_SEGUNDOS,
    INTERVALO_CONSULTA_MS,
    TAMANO_FOTO,
    TASA_BITS_VIDEO,
    URL_BACKEND,
)
from interfaz.ventana_principal import VentanaPrincipal


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
    cliente = ClienteBackend(URL_BACKEND)
    # La ventana recibe los objetos ya preparados en vez de crearlos por dentro.
    # Así coordina el caso de uso (consultar y capturar), mientras cada objeto
    # conserva su especialidad y puede probarse de forma independiente.
    ventana = VentanaPrincipal(
        controlador,
        gestor,
        cliente,
        INTERVALO_CONSULTA_MS,
        DURACION_VIDEO_SEGUNDOS,
    )
    # Mostrar la ventana no bloquea: Qt comienza a atender sus eventos al
    # entrar en ``exec`` y termina cuando el usuario cierra la aplicación.
    ventana.show()
    # ``exec`` inicia la cola de eventos de Qt. Mientras está activa, Qt entrega
    # al temporizador sus ticks, a los botones sus clics y a los reproductores
    # sus señales; sin este ciclo la ventana se mostraría y cerraría enseguida.
    return aplicacion.exec()


if __name__ == "__main__":
    # Este guardia evita ejecutar la interfaz al importar el módulo desde una
    # prueba. SystemExit entrega a la consola el código que devuelve Qt.
    raise SystemExit(iniciar_aplicacion())
