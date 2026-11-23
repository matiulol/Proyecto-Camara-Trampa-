"""Servicios reutilizables que separan los datos generales de las rutas.

Los servicios contienen operaciones que no son rutas HTTP ni consultas directas a
MongoDB. Esta separación permite que los enrutadores se concentren en HTTP y usen
funciones pequeñas para preparar la información que devolverán al Panel de control.
"""
