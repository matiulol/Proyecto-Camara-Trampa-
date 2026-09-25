# Camara Trampa: prueba local para Raspberry Pi

Esta carpeta contiene una primera prueba independiente para usar una camara CSI de Raspberry Pi con una interfaz local de PySide6. Permite capturar fotos JPEG, iniciar y detener videos MP4, listar las capturas guardadas en la tarjeta SD, ver fotos y reproducir videos desde la misma ventana.

La Raspberry se conecta únicamente a FastAPI mediante HTTP. No se conecta a MongoDB,
ni al dashboard. Los JPEG y MP4 se conservan en la tarjeta SD y FastAPI registra sus
metadatos en la colección `archivos` al recibir el resultado.

## Tecnologia elegida

La aplicacion usa **Picamera2**, la biblioteca recomendada actualmente por Raspberry Pi para sus modulos de camara CSI. Picamera2 usa la pila `libcamera`; la antigua biblioteca `PiCamera` esta obsoleta. Para crear MP4, Picamera2 entrega H.264 a `ffmpeg`.

Se recomienda Raspberry Pi OS Bookworm de 64 bits con Python 3.11, una camara Raspberry Pi conectada por su cable CSI y un entorno grafico de escritorio activo.

## Estructura

```text
raspberry_prueba/
├── main.py                         # Arranque de la aplicacion
├── config.py                       # ID local y parametros de captura
├── camara/
│   └── controlador_camara.py       # Picamera2: iniciar, foto, video y cierre
├── almacenamiento/
│   └── gestor_archivos.py           # Carpetas, nombres y lista de capturas
├── interfaz/
│   └── ventana_principal.py         # Ventana PySide6, visor y reproductor
├── archivos/
│   └── camara001/
│       ├── fotos/                   # foto_001.jpg, foto_002.jpg, ...
│       └── videos/                  # video_001.mp4, video_002.mp4, ...
├── tests/
│   └── test_gestor_archivos.py
├── requirements.txt
└── README.md
```

Las carpetas de `archivos/camara001` tambien se crean automaticamente al iniciar el programa. Los nombres se calculan a partir del ultimo indice existente y nunca se reutiliza una ruta que ya exista.

## Instalacion en la Raspberry Pi

Instala la pila de la camara y los componentes multimedia desde los repositorios de Raspberry Pi OS:

```bash
sudo apt update
sudo apt install -y python3-picamera2 ffmpeg python3-pyside6.qtwidgets python3-pyside6.qtmultimedia
```

No instales `picamera2` con `pip`: Raspberry Pi recomienda instalarlo mediante `apt` para mantener compatibles sus enlaces de `libcamera`. `requirements.txt` declara PySide6 para entornos donde prefieras administrarlo con Python, pero para esta prueba se recomienda la instalacion con `apt` anterior y ejecutar con el Python del sistema.

## Comprobar la camara antes de abrir la aplicacion

Con la camara conectada y la Raspberry apagada al colocar el cable CSI, arranca el sistema y ejecuta:

```bash
rpicam-hello -t 3s
```

En Raspberry Pi OS Bookworm los comandos comienzan con `rpicam-`. Si ves una vista previa o un mensaje de camara detectada, la pila esta lista. Tambien puedes comprobar los dispositivos con:

```bash
rpicam-hello --list-cameras
```

## Ejecucion

Desde esta carpeta:

```bash
python3 main.py
```

Antes de ejecutar en la Raspberry, configura la dirección accesible de la PC que
ejecuta FastAPI. Reemplaza `192.168.1.50` por la IP real de esa PC:

```bash
export URL_BACKEND="http://192.168.1.50:8000/api/v1"
export CAMARA_ID="camara001"
python3 main.py
```

La interfaz consulta cada cinco segundos `GET /peticiones/pendientes/camara001`.
Cuando recibe una solicitud, usa Picamera2, guarda el archivo local y llama a
`PUT /peticiones/{id}/resultado`. Para cambiar el intervalo o los segundos del
video se pueden definir `INTERVALO_CONSULTA_MS` y `DURACION_VIDEO_SEGUNDOS`.

La ventana muestra el estado de camara. Cuando diga `DISPONIBLE`, las acciones de captura quedan habilitadas.

## Guia de prueba

1. Enciende la Raspberry con la camara CSI conectada.
2. Ejecuta `rpicam-hello -t 3s` para comprobar que la camara responde.
3. Abre la aplicacion con `python3 main.py`.
4. Comprueba el estado `DISPONIBLE` y pulsa **Tomar foto**.
5. Confirma que aparece `foto_001.jpg` en `archivos/camara001/fotos/` y en la tabla.
6. Selecciona la foto en la tabla para verla en la ventana.
7. Pulsa **Iniciar video**, espera unos segundos y pulsa **Detener video**.
8. Confirma que aparece `video_001.mp4` en `archivos/camara001/videos/`.
9. Selecciona el video y pulsa **Reproducir video seleccionado**.
10. Cierra la ventana. La aplicacion detiene cualquier grabacion y libera la camara.

## Problemas comunes

| Situacion | Accion recomendada |
| --- | --- |
| `Estado de camara: NO DISPONIBLE` | Apaga la Raspberry, revisa la orientacion y firmeza del cable CSI, vuelve a encenderla y ejecuta `rpicam-hello --list-cameras`. |
| `No module named 'picamera2'` | Instala `python3-picamera2` con `apt` y ejecuta con `python3` del sistema, no desde un entorno virtual aislado. |
| El video no inicia o no se genera MP4 | Instala `ffmpeg` y confirma que `ffmpeg -version` responde. |
| No se reproduce el video dentro de la app | Instala `python3-pyside6.qtmultimedia`; en instalaciones Lite puede faltar un backend multimedia o un escritorio grafico. |
| Error de permiso al guardar | Ejecuta la aplicacion desde una carpeta que pertenezca al usuario actual y confirma espacio libre con `df -h`. |

## Verificacion sin camara

La prueba unitaria del almacenamiento no requiere Raspberry ni PySide6:

```bash
python3 -m unittest discover -s tests -v
```

La captura real debe probarse en la Raspberry porque Picamera2 usa su hardware y su pila `libcamera`.
