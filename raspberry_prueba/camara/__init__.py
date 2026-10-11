"""Paquete que aísla el acceso a la cámara CSI de Raspberry Pi.

La interfaz usa su controlador en vez de llamar a Picamera2 directamente para
mantener la dependencia de hardware separada de la presentación y de la red.
"""
