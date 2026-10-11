# ANICAM — Cámara Trampa Inteligente para Reserva Natural

ANICAM permite que el Dashboard solicite una foto o un video a una Raspberry Pi
con cámara CSI. FastAPI coordina la comunicación y es el único componente que
accede a MongoDB. La base de datos existente y obligatoria es **`Ani_cam`**.

> Esta guía conserva la arquitectura probada; no crea una base nueva ni cambia
> los endpoints existentes. Para la guía técnica completa consulte
> [`docs/DOCUMENTACION_ETAPA_1.txt`](docs/DOCUMENTACION_ETAPA_1.txt). También
> existe una versión esencial en texto plano: [`README.txt`](README.txt). La
> referencia breve de rutas HTTP se mantiene en [`ENDPOINTS.docx`](ENDPOINTS.docx).

## Arquitectura y flujo

```text
Dashboard PySide6 ──HTTP──> FastAPI ──> MongoDB Ani_cam
                              ^
                              │ HTTP (polling y resultado)
Raspberry Pi + Picamera2 ────┘
             │
             └── JPEG / MP4 en su tarjeta SD
```

1. El Dashboard crea una petición `foto` o `video`.
2. La Raspberry consulta periódicamente si hay una petición pendiente para su
   cámara, realiza la captura y conserva el archivo local.
3. La Raspberry informa el resultado a FastAPI; este actualiza `peticiones` y
   registra metadatos en `archivos`.

## Instalación y orden de inicio

El orden importa porque cada componente depende del anterior:

1. **Inicie MongoDB** y compruebe que responde. En la PC puede ejecutar
   `mongosh` y después `use Ani_cam`; la base debe ser `Ani_cam`, no una nueva.
   Si el servicio no inicia, revise MongoDB antes de continuar.
2. **Prepare e inicie el backend** desde `backend`. El entorno virtual aísla
   las bibliotecas Python del sistema:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

   `uvicorn` sirve FastAPI; `main:app` busca el objeto `app` de `main.py`;
   `--host 0.0.0.0` escucha en todas las interfaces de la PC, `--port 8000`
   fija el puerto y `--reload` reinicia durante desarrollo. Pruebe
   `http://localhost:8000/health`: debe responder `{"status":"ok"}`. Si falla,
   revise que MongoDB esté activo y que la URI siga siendo `Ani_cam`.

   `uvicorn main:app --reload` usa la configuración predeterminada y puede dejar
   el servicio accesible solo desde la propia PC. Para una Raspberry remota use
   siempre el comando completo anterior.

3. **Compruebe la red.** Obtenga la IPv4 de la PC con `ipconfig`. Desde la
   Raspberry ejecute `ping IP_DE_LA_PC`; respuestas indican conectividad. En una
   red local normalmente ambos dispositivos comparten red, por Wi‑Fi o Ethernet,
   pero lo indispensable es que puedan comunicarse entre sí.
4. **Prepare la Raspberry.** Siga
   [`raspberry_prueba/README.md`](raspberry_prueba/README.md). Antes de iniciar,
   configure `URL_BACKEND` con la IP de la PC y el prefijo de la API:

   ```bash
   export URL_BACKEND="http://192.168.1.100:8000/api/v1"
   export CAMARA_ID="camara001"
   python3 main.py
   ```

   La IP es un ejemplo. `localhost` y `127.0.0.1` siempre significan *el mismo
   dispositivo*: en la Raspberry no representan la PC. El puerto `8000` debe
   coincidir con Uvicorn.
5. **Inicie el Dashboard** en otra terminal de la PC:

   ```powershell
   cd desktop_app
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python main.py
   ```

   Inicie sesión, seleccione una cámara y cree una petición de prueba. La
   Raspberry mostrará la conexión, ejecutará el trabajo pendiente y el Dashboard
   verá el estado actualizado al refrescarlo.

## Dependencias reales de Raspberry Pi

En Raspberry Pi OS se instalan con el gestor del sistema porque Picamera2 se
integra con `libcamera`:

```bash
sudo apt update
sudo apt install -y python3-picamera2 ffmpeg python3-pyside6.qtwidgets python3-pyside6.qtmultimedia
```

`requests` y el rango de PySide6 están declarados en
`raspberry_prueba/requirements.txt`. No instale Picamera2 con `pip`. Antes de
abrir ANICAM compruebe la cámara con `rpicam-hello -t 3s`.

## Problemas frecuentes

| Situación | Qué comprobar |
| --- | --- |
| La Raspberry no llega al backend | IP y `URL_BACKEND`, ping, FastAPI iniciado con `--host 0.0.0.0`, puerto 8000 y firewall de la PC. |
| La PC funciona pero la Raspberry no | No use `localhost`: desde la Raspberry apunta a ella misma. Use la IPv4 de la PC. |
| MongoDB no funciona | Servicio MongoDB activo, URI `mongodb://localhost:27017/Ani_cam` y respuesta correcta de `/health`. |
| No se instala una dependencia de cámara | Use `apt` para Picamera2, libcamera/`rpicam-*`, ffmpeg y los paquetes PySide6 de Raspberry Pi OS. |
| Un MP4 no se reproduce | La aplicación informa el error sin cerrarse. Revise la sección «Reproducción de video» en la documentación técnica. |

## Alcance actual

No hay JWT, nube, transferencia de archivos al Dashboard ni creación automática
de eventos. Los videos y fotografías permanecen en la Raspberry; MongoDB guarda
sus metadatos y la relación con la petición.
