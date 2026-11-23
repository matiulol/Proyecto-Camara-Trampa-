# Aplicación de ANICAM para Raspberry Pi

Esta carpeta contiene la aplicación de Raspberry Pi que atiende las peticiones
manuales creadas desde el Panel de control y las capturas automáticas del sensor PIR.
Usa una cámara CSI para generar fotos JPEG o videos MP4, conserva las capturas
en la tarjeta SD y permite ver localmente los resultados de peticiones manuales.

La Raspberry se conecta únicamente a FastAPI mediante HTTP. No se conecta a MongoDB
ni al Panel de control. Los JPEG y MP4 se conservan en la tarjeta SD; tras cerrar cada
captura, la Raspberry la envía a FastAPI, que persiste y confirma sus metadatos en
la colección `archivos` antes de informar éxito.

## Tecnología elegida

La aplicación usa **Picamera2**, la biblioteca recomendada por Raspberry Pi para sus módulos de cámara CSI. Picamera2 usa la pila `libcamera`; la antigua biblioteca `PiCamera` está obsoleta. Para crear MP4, Picamera2 entrega H.264 a `ffmpeg`.

Se recomienda Raspberry Pi OS Bookworm de 64 bits con Python 3.11, una cámara Raspberry Pi conectada por su cable CSI y un entorno gráfico de escritorio activo.

## Estructura

```text
raspberry_pi/
├── inicio.py                         # Arranque de la aplicación
├── configuracion.py                  # URL de API, ID local y parámetros de captura
├── camara/
│   └── controlador_camara.py       # Picamera2: iniciar, foto, video y cierre
├── sensor/
│   ├── sensor_pir.py                # Flancos físicos de GPIO Zero
│   └── capturador_pir.py            # Máquina de estados autónoma del PIR
├── almacenamiento/
│   └── gestor_archivos.py           # Carpetas, nombres y lista de capturas
├── interfaz/
│   └── ventana_principal.py         # Ventana PySide6, visor y reproductor
├── archivos/
│   └── camara001/
│       ├── fotos/                   # foto_001.jpg, foto_002.jpg, ...
│       └── videos/                  # video_001.mp4, video_002.mp4, ...
├── requirements.txt
└── README.md
```

Las carpetas de `archivos/camara001` también se crean automáticamente al iniciar el programa. Los nombres se calculan a partir del último índice existente y nunca se reutiliza una ruta que ya exista.

## Instalación en la Raspberry Pi

Instala la pila de la cámara y los componentes multimedia desde los repositorios de Raspberry Pi OS:

```bash
sudo apt update
sudo apt install -y python3-picamera2 ffmpeg python3-pyside6.qtwidgets python3-pyside6.qtmultimedia
```

No instales `picamera2` con `pip`: Raspberry Pi recomienda instalarlo mediante `apt` para mantener compatibles sus enlaces de `libcamera`. `requirements.txt` declara PySide6 para entornos donde prefieras administrarlo con Python, pero para esta versión se recomienda la instalación con `apt` anterior y ejecutar con el Python del sistema.

## Comprobar la cámara antes de abrir la aplicación

Con la cámara conectada y la Raspberry apagada mientras colocas el cable CSI, arranca el sistema y ejecuta:

```bash
rpicam-hello -t 3s
```

En Raspberry Pi OS Bookworm los comandos comienzan con `rpicam-`. Si ves una vista previa o un mensaje de cámara detectada, la pila está lista. También puedes comprobar los dispositivos con:

```bash
rpicam-hello --list-cameras
```

## Ejecución

Desde esta carpeta:

```bash
python3 inicio.py
```

Antes de ejecutar en la Raspberry, configure la dirección accesible de la PC
que ejecuta FastAPI. `URL_BACKEND` es la URL base de la API, por eso conserva
el sufijo `/api/v1`. Reemplace `192.168.1.100` por la IPv4 real de esa PC:

```bash
export URL_BACKEND="http://192.168.1.100:8000/api/v1"
export CAMARA_ID="camara001"
python3 inicio.py
```

No use `localhost` ni `127.0.0.1` para una PC remota: desde la Raspberry ambas
direcciones significan la propia Raspberry. Antes de abrir la aplicación,
compruebe la red con `ping IP_DE_LA_PC`. Si no responde, revise conectividad,
IP, firewall y que el servidor esté iniciado con:

```bash
uvicorn inicio:app --host 0.0.0.0 --port 8000 --reload
```

La interfaz consulta cada cinco segundos `GET /peticiones/pendientes/camara001`.
Cuando recibe una solicitud, usa Picamera2, guarda el archivo local y lo envía
a `POST /peticiones/{id}/archivo`; FastAPI confirma B2 y MongoDB. Si la carga o
la cámara fallan, comunica el error con `PUT /peticiones/{id}/resultado`; una
captura correcta no se marca ejecutada por esa ruta sin su archivo confirmado.
Para cambiar el intervalo o los segundos del video se pueden definir
`INTERVALO_CONSULTA_MS` y `DURACION_VIDEO_SEGUNDOS`.

La ventana muestra si puede comunicarse con FastAPI y el resultado de cada
petición. La captura no se inicia con botones locales: se ejecuta al recibir una
orden pendiente del Panel de control.

## Recorrido de una petición manual

1. Enciende la Raspberry con la cámara CSI conectada.
2. Ejecuta `rpicam-hello -t 3s` para comprobar que la cámara responde.
3. Abre la aplicación con `python3 inicio.py`.
4. Crea desde el Panel de control una petición de foto o video para `camara001`.
5. Confirma que la petición aparece en la tabla de la Raspberry y cambia a
   `ejecutado`, o a `error` con un mensaje comprensible.
6. Comprueba que aparece el archivo en `archivos/camara001/fotos/` o `videos/`.
7. Pulsa **Visualizar** en la fila de una petición ejecutada para abrir su
   fotografía o reproducir su video local. La tabla muestra Tipo, Fecha, Estado
   y esa acción; el identificador interno continúa asociado a la petición, pero
   no se expone como columna.

La Raspberry abre sus copias locales de SD según el tipo de la petición
(`foto` o `video`); no consume URLs temporales de B2 en su visor. Por ello la
normalización de `imagen`/`image/jpeg` usada por el visor del Panel de control no
modifica este recorrido. La reproducción local de MP4 sigue requiriendo
`python3-pyside6.qtmultimedia`, `ffmpeg` y un componente de Qt Multimedia compatible
con el códec generado por la cámara.
8. Cierra la ventana. La aplicación detiene cualquier grabación y libera la cámara.

## Problemas comunes

| Situación | Acción recomendada |
| --- | --- |
| `Estado de cámara: NO DISPONIBLE` | Apaga la Raspberry, revisa la orientación y firmeza del cable CSI, vuelve a encenderla y ejecuta `rpicam-hello --list-cameras`. |
| `No module named 'picamera2'` | Instala `python3-picamera2` con `apt` y ejecuta con `python3` del sistema, no desde un entorno virtual aislado. |
| El video no inicia o no se genera MP4 | Instala `ffmpeg` y confirma que `ffmpeg -version` responde. |
| No se reproduce el video dentro de la aplicación | La aplicación muestra el detalle y permanece abierta. Instala `python3-pyside6.qtmultimedia`, verifica `ffmpeg -version` y prueba el MP4 con un reproductor externo. En Raspberry Pi OS el componente que usa Qt Multimedia depende de los paquetes multimedia del sistema. |
| Error de permiso al guardar | Ejecuta la aplicación desde una carpeta que pertenezca al usuario actual y confirma el espacio libre con `df -h`. |

La versión de cierre no incluye pruebas automatizadas. La comprobación de
capturas requiere una Raspberry con cámara CSI y la pila `libcamera` instalada.

## Reproducción de video: diagnóstico y comportamiento seguro

La interfaz usa `QMediaPlayer` y `QVideoWidget` de **Qt Multimedia** (PySide6),
no un reproductor MP4 propio. Picamera2 genera H.264 y `FfmpegOutput` lo
encapsula como MP4. Que un archivo se reproduzca al copiarlo a otra PC confirma
que probablemente se creó correctamente, pero no garantiza que el servidor
multimedia de Qt instalado en la Raspberry tenga el códec o los complementos
necesarios para decodificarlo.

ANICAM ahora escucha los errores asíncronos de `QMediaPlayer`: si Qt informa un
fallo, detiene esa reproducción, muestra el detalle técnico y mantiene abierta
la aplicación y su consulta periódica. Una caída nativa del componente multimedia
no puede confirmarse ni corregirse sin reproducirla en el hardware; si ocurre, guarde la
salida de consola y verifique en este orden: `ffmpeg -version`, los paquetes
`python3-pyside6.qtmultimedia`, la reproducción externa del mismo MP4 y el
formato/códec informado por `ffprobe archivo.mp4`.
## Capturas automáticas con sensor PIR

ANICAM usa `gpiozero.MotionSensor`, instalado desde Raspberry Pi OS para mantener
compatibilidad con el GPIO de la Pi 3 B+: `sudo apt update && sudo apt install -y
python3-gpiozero`. No instale esta biblioteca desde Windows para la Raspberry.

Conecte GND del PIR a GND de la Pi, aliméntelo según su módulo y conecte OUT a
un GPIO libre compatible con **3,3 V**. Los GPIO no toleran una salida de 5 V;
use un conversor de nivel si el PIR no entrega 3,3 V. El valor configurado por
defecto es `PIR_PIN_BCM=17` y `PIR_HABILITADO_LOCAL=true`; cámbielos sólo si el
cableado físico usa otro GPIO BCM.

El Panel de control guarda por cámara si el PIR está habilitado, el tipo (`foto` o
`video`) y un período de espera de 3 a 3600 segundos. `PIR_HABILITADO_LOCAL` controla si
el proceso intenta inicializar el sensor; `PIR_PIN_BCM` define el pin físico y
usa BCM 17 por defecto. Cada flanco consulta la configuración de esa cámara y
`CapturadorPIR` realiza la captura en un hilo propio, independiente del ciclo de
eventos de Qt.

Una captura aceptada se guarda primero en SD. Tras cerrarse el JPEG o el MP4,
la Raspberry envía el archivo a `POST /api/v1/peticiones/pir/archivo`; FastAPI
registra el evento y el metadato de `archivos`, confirma B2 y marca el evento
como `ejecutado`. El flujo no crea una petición pendiente. Si el hardware falla
después de reservar la cámara y antes de iniciar la persistencia, la Raspberry
informa un evento de error mediante `POST /api/v1/peticiones/pir/error`. Si B2
rechaza el archivo, FastAPI registra el error en el evento y el metadato; la
copia local se conserva.

El período de espera empieza cuando termina la captura o falla una captura aceptada.
Los movimientos durante la captura o el período de espera se descartan sin quedar en cola ni
crear eventos. Al vencer el intervalo, si el PIR seguía activo, se necesita un
aviso de ausencia de movimiento antes de aceptar otro flanco. Las peticiones
manuales continúan por consulta periódica y comparten una reserva exclusiva de cámara con
el coordinador PIR. Desactivar el PIR en el Panel de control detiene las capturas
automáticas; las peticiones manuales siguen disponibles.
