from config.settings import settings


def get_project_info():
    return {
        "nombre": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "descripcion": settings.DESCRIPTION,
    }
