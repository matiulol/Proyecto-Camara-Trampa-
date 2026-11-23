"""Información descriptiva del proyecto utilizada por las rutas generales."""

# La configuración centralizada evita duplicar nombre, versión y descripción
# dentro de la ruta HTTP GET /info.
from configuracion.ajustes import configuracion


def obtener_informacion_proyecto() -> dict[str, str]:
    """Construye los datos descriptivos de solo lectura del servidor.

    La ruta general consume esta función para distinguir su responsabilidad HTTP
    de la preparación de datos. No consulta MongoDB ni modifica ``Ani_cam``.
    """
    return {
        "nombre": configuracion.NOMBRE_PROYECTO,
        "version": configuracion.VERSION_PROYECTO,
        "descripcion": configuracion.DESCRIPCION,
    }
