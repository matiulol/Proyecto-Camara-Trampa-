"""Conversión de valores de MongoDB a datos seguros para respuestas JSON."""

# datetime permite reconocer fechas almacenadas como objetos Python. Any se usa
# porque la función recibe tanto documentos, listas y valores individuales.
from datetime import datetime
from typing import Any

# ObjectId es el identificador que MongoDB genera para documentos como peticiones.
# JSON no puede enviarlo directamente, por eso debe transformarse a texto.
from bson import ObjectId


def serializar_documento(valor: Any) -> Any:
    # Recorre de forma recursiva documentos y listas. Los routers llaman esta
    # función antes de responder para que FastAPI pueda convertir el resultado a
    # JSON sin perder la estructura original de cada colección.
    if isinstance(valor, list):
        return [serializar_documento(item) for item in valor]
    if isinstance(valor, dict):
        return {clave: serializar_documento(contenido) for clave, contenido in valor.items()}
    if isinstance(valor, ObjectId):
        # Conserva el identificador de MongoDB, pero como cadena utilizable por
        # Dashboard y Raspberry en rutas HTTP, por ejemplo /peticiones/{id}.
        return str(valor)
    if isinstance(valor, datetime):
        # Las fechas se convierten al formato ISO estándar para que no dependan de
        # la configuración regional de la computadora cliente.
        return valor.isoformat()
    return valor
