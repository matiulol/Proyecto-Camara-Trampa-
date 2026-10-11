"""Comunicación HTTP de la Raspberry con FastAPI.

Este límite evita conexiones directas a MongoDB y concentra las solicitudes REST
en un cliente que traduce errores de red para la interfaz.
"""
