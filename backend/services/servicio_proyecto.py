"""Información descriptiva del proyecto utilizada por las rutas generales."""

# La configuración centralizada evita duplicar nombre, versión y descripción
# dentro del endpoint GET /info.
from config.settings import settings


def obtener_informacion_proyecto() -> dict[str, str]:
    """Construye los datos descriptivos de solo lectura del backend.

    La ruta general consume esta función para distinguir su responsabilidad HTTP
    de la preparación de datos. No consulta MongoDB ni modifica ``Ani_cam``.
    """
    return {
        "nombre": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "descripcion": settings.DESCRIPTION,
    }
