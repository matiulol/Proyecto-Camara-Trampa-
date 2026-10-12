"""Configuración de la aplicación instalada en una Raspberry Pi.

Separar estas constantes de la lógica permite reutilizar la misma copia de
ANICAM en distintas cámaras o redes. Las variables de entorno prevalecen sobre
los valores de ejemplo, por lo que no es necesario editar el código para cambiar
de PC o de identificador de cámara. En otras palabras, este módulo reúne las
decisiones que cambian según la instalación, mientras que las clases de cámara,
almacenamiento e interfaz conservan el mismo comportamiento.
"""

# ``os`` permite recibir valores de entorno, mecanismo habitual para adaptar
# una instalación sin guardar direcciones o identificadores en el código.
import os

# Cada Raspberry necesita un identificador estable. FastAPI lo usa para devolver
# únicamente las peticiones destinadas a esa cámara y para separar sus archivos
# locales de los de otras cámaras.
# ``getenv`` usa primero la variable definida en el sistema y, si no existe,
# conserva el valor de ejemplo. Esto permite preparar cada Raspberry sin editar
# ni volver a distribuir el programa.
CAMARA_ID = os.getenv("CAMARA_ID", "camara001")

# Es la dirección de la API REST de FastAPI, no la de MongoDB. En una Raspberry,
# 127.0.0.1 (localhost) siempre señala a la Raspberry misma; para conectarse al
# equipo que ejecuta FastAPI debe configurarse la IP alcanzable de ese equipo,
# por ejemplo ``http://192.168.1.20:8000/api/v1``. Así el recorrido es
# Raspberry -> FastAPI -> MongoDB, sin exponer credenciales de la base de datos.
URL_BACKEND = os.getenv("URL_BACKEND", "http://127.0.0.1:8000/api/v1")
# El intervalo evita consultar MongoDB directamente: la Raspberry pregunta a
# FastAPI mediante HTTP y FastAPI conserva la responsabilidad de Ani_cam.
# Las variables de entorno son texto. ``int`` convierte ese texto a la unidad
# numérica que QTimer necesita, de modo que el intervalo sea configurable.
INTERVALO_CONSULTA_MS = int(os.getenv("INTERVALO_CONSULTA_MS", "5000"))
# La duración se expresa en segundos para una configuración legible; la
# interfaz la convierte a milisegundos porque esa es la unidad de QTimer. No es
# una pausa bloqueante: el temporizador de Qt permite que la interfaz responda
# mientras la cámara sigue grabando.
DURACION_VIDEO_SEGUNDOS = int(os.getenv("DURACION_VIDEO_SEGUNDOS", "10"))
# Picamera2 recibe el tamaño en píxeles y la tasa del codificador H.264 en bits
# por segundo. La resolución determina el detalle de cada cuadro y la tasa de
# bits influye en la calidad/tamaño del video. Son parámetros de captura, no
# datos que deban guardarse en MongoDB.
TAMANO_FOTO = (1920, 1080)
TASA_BITS_VIDEO = 10_000_000
# El pin BCM no se presupone: debe coincidir con el cable OUT del PIR. Al quedar
# vacío el sensor no se inicializa y las capturas manuales continúan disponibles.
PIR_PIN_BCM = os.getenv("PIR_PIN_BCM", "").strip()
PIR_HABILITADO_LOCAL = os.getenv("PIR_HABILITADO_LOCAL", "false").lower() == "true"
INTERVALO_CONFIGURACION_PIR_MS = int(os.getenv("INTERVALO_CONFIGURACION_PIR_MS", "30000"))
