"""Conversión de valores de MongoDB a datos seguros para respuestas JSON."""

# datetime permite reconocer fechas almacenadas como objetos Python. Any se usa
# porque la función recibe tanto documentos, listas y valores individuales.
from datetime import datetime
from typing import Any

# ObjectId es el identificador que MongoDB genera para documentos como peticiones.
# JSON no puede enviarlo directamente, por eso debe transformarse a texto.
from bson import ObjectId


def serializar_documento(valor: Any) -> Any:
    """Convierte recursivamente tipos BSON y fechas a valores aptos para JSON.

    Acepta documentos, listas o valores individuales; los ``ObjectId`` pasan a
    texto y las fechas a ISO 8601. Los demás valores se devuelven sin cambios.
    """
    # Recorre de forma recursiva documentos y listas. Los enrutadores llaman esta
    # función antes de responder para que FastAPI pueda convertir el resultado a
    # JSON sin perder la estructura original de cada colección.
    if isinstance(valor, list):
        return [serializar_documento(elemento_lista) for elemento_lista in valor]
    if isinstance(valor, dict):
        return {clave: serializar_documento(contenido) for clave, contenido in valor.items()}
    if isinstance(valor, ObjectId):
        # Conserva el identificador de MongoDB, pero como cadena utilizable por
        # Panel de control y Raspberry en rutas HTTP, por ejemplo /peticiones/{id}.
        return str(valor)
    if isinstance(valor, datetime):
        # Las fechas se convierten al formato ISO estándar para que no dependan de
        # la configuración regional de la computadora cliente.
        return valor.isoformat()
    return valor
