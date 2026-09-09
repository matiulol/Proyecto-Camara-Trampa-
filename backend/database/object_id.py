from datetime import datetime
from typing import Any

from bson import ObjectId


def serializar_documento(valor: Any) -> Any:
    if isinstance(valor, list):
        return [serializar_documento(item) for item in valor]
    if isinstance(valor, dict):
        return {clave: serializar_documento(contenido) for clave, contenido in valor.items()}
    if isinstance(valor, ObjectId):
        return str(valor)
    if isinstance(valor, datetime):
        return valor.isoformat()
    return valor
