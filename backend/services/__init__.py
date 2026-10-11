"""Servicios reutilizables que separan datos generales de los routers.

Los servicios contienen operaciones que no son endpoints ni consultas directas a
MongoDB. Esta separación permite que los routers se concentren en HTTP y usen
funciones pequeñas para preparar la información que devolverán al Dashboard.
"""
