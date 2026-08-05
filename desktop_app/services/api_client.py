import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from config.settings import API_BASE_URL


def check_backend_connection():
    """Comprueba que el backend inicial responda correctamente."""
    try:
        with urlopen(f"{API_BASE_URL}/", timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return False, f"Error del servidor: {error.code}"
    except URLError:
        return False, "No se pudo conectar con el backend"
    except TimeoutError:
        return False, "Tiempo de espera agotado"

    if data.get("message") == "Backend iniciado correctamente":
        return True, "Backend conectado correctamente"

    return False, "El backend respondio con un formato inesperado"
