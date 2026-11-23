"""Acceso aislado a Backblaze B2 mediante su API compatible con S3."""
from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from configuracion.ajustes import configuracion


class ErrorB2(RuntimeError):
    """Falla segura de B2: el detalle del proveedor no llega a clientes ni logs."""


def _cliente_b2():
    """Crea el cliente solo en el servidor, donde viven las credenciales."""
    if not configuracion.b2_configurado():
        raise ErrorB2("Backblaze B2 no está configurado en backend/.env.")
    return boto3.client(
        "s3", endpoint_url=configuracion.DIRECCION_SERVICIO_B2,
        region_name=configuracion.REGION_B2,
        aws_access_key_id=configuracion.IDENTIFICADOR_CLAVE_B2,
        aws_secret_access_key=configuracion.CLAVE_SECRETA_B2,
    )


def clave_objeto(camara_id: str, peticion_id: str, nombre: str, tipo: str) -> str:
    """Devuelve una clave determinista para que reintentos no creen duplicados."""
    extension = Path(nombre).suffix.lower()
    return f"camaras/{camara_id}/{tipo}/{peticion_id}{extension}"


def subir_archivo(origen: BinaryIO, clave: str, tipo_contenido: str) -> None:
    """Transmite el archivo recibido a B2 sin guardarlo en el disco del servidor."""
    try:
        _cliente_b2().upload_fileobj(
            origen, configuracion.NOMBRE_DEPOSITO_B2, clave,
            ExtraArgs={"ContentType": tipo_contenido},
        )
    except (BotoCoreError, ClientError, OSError) as excepcion:
        raise ErrorB2("No se pudo subir el archivo a Backblaze B2.") from excepcion


def enlace_temporal(clave: str, expiracion: int = 300) -> str:
    """Genera una URL privada, breve y renovable para un objeto ya registrado."""
    try:
        cliente = _cliente_b2()
        cliente.head_object(Bucket=configuracion.NOMBRE_DEPOSITO_B2, Key=clave)
        return cliente.generate_presigned_url(
            "get_object", Params={"Bucket": configuracion.NOMBRE_DEPOSITO_B2, "Key": clave},
            ExpiresIn=expiracion,
        )
    except (BotoCoreError, ClientError) as excepcion:
        raise ErrorB2("El archivo no está disponible en Backblaze B2.") from excepcion
