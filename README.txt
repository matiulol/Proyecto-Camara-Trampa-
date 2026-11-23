ANICAM — Cámara trampa inteligente para una reserva natural
===========================================================

ANICAM conecta el Panel de control de escritorio, un servidor FastAPI, la base
de datos MongoDB `Ani_cam` y una Raspberry Pi con cámara CSI. El Panel de
control crea peticiones; la Raspberry las consulta por HTTP, captura fotos o
videos en su tarjeta SD y envía los archivos al servidor. FastAPI es el único
componente que accede directamente a MongoDB y a Backblaze B2.

La base de datos existente y obligatoria es `Ani_cam`. En la PC, configure la
conexión local en `backend/.env` mediante `MONGODB_URI=mongodb://localhost:27017`.
No cree ni migre otra base de datos.

ORDEN DE INICIO
1. Inicie MongoDB local. Desde la carpeta `backend`, copie `.env.example` como
   `.env` y mantenga `MONGODB_URI=mongodb://localhost:27017`,
   `MONGODB_DATABASE=Ani_cam` y `MONGODB_TIMEOUT_MS=5000`. El archivo `.env` está
   excluido de Git. En Windows, compruebe el servicio con `Get-Service MongoDB`
   y, si está detenido, inícielo como administrador con `Start-Service MongoDB`.

2. Instale las dependencias e inicie el servidor desde `backend`:

   ```powershell
   pip install -r requirements.txt
   uvicorn inicio:app --host 0.0.0.0 --port 8000 --reload
   ```

   Uvicorn sirve FastAPI. `inicio:app` selecciona el objeto `app` de `inicio.py`;
   `0.0.0.0` permite conexiones desde la red, `8000` es el puerto y `--reload`
   reinicia el proceso durante el desarrollo. Compruebe
   `http://localhost:8000/health`; debe responder `{"status":"ok"}`.

3. Obtenga la IPv4 de la PC con `ipconfig` y, desde la Raspberry, compruebe la
   conexión con `ping IP_DE_LA_PC`. Si no hay respuesta, revise la red, la IP,
   el firewall y que FastAPI escuche en todas las interfaces.

4. Instale las dependencias de Raspberry Pi OS y configure la dirección del
   servidor en la Raspberry:

   ```bash
   sudo apt update
   sudo apt install -y python3-picamera2 ffmpeg python3-pyside6.qtwidgets python3-pyside6.qtmultimedia
   export URL_BACKEND="http://192.168.1.100:8000/api/v1"
   export CAMARA_ID="camara001"
   python3 inicio.py
   ```

   Ejecute `python3 inicio.py` desde `raspberry_pi`. La IP es un ejemplo:
   reemplácela por la IPv4 real de la PC. En la Raspberry, `localhost` y
   `127.0.0.1` representan la propia Raspberry, no la PC. Picamera2 se instala
   con `apt` y no con `pip`.

5. Inicie el Panel de control desde `aplicacion_escritorio` en otra terminal de
   la PC:

   ```powershell
   pip install -r requirements.txt
   python inicio.py
   ```

   Inicie sesión, seleccione una cámara y cree una petición de foto o video.
   Si el Panel de control se ejecuta en otra PC, defina antes la variable de
   entorno `ANICAM_API_BASE_URL` con la dirección del servidor:

   ```powershell
   $env:ANICAM_API_BASE_URL = "http://IP_DE_LA_PC:8000/api/v1"
   ```

BACKBLAZE B2 PRIVADO

Configure únicamente en `backend/.env` las variables
`B2_DIRECCION_SERVICIO`, `B2_NOMBRE_DEPOSITO`, `B2_REGION`,
`B2_IDENTIFICADOR_CLAVE` y `B2_CLAVE_SECRETA`. No suba ese archivo a Git. La
Raspberry conserva primero la captura en SD y la envía por HTTP a FastAPI; el
servidor la sube a B2 y genera enlaces temporales para visualizarla. Si la carga
a B2 falla, se conserva el archivo local y la petición no se marca como ejecutada.

CAPTURAS PIR

El sensor PIR puede generar capturas automáticas cuando está habilitado en el
Panel de control y configurado en la Raspberry. Cada captura se guarda primero
en SD y se envía a FastAPI como evento; no crea una petición manual pendiente.
Los movimientos durante una captura o el período de espera se descartan. Si la
captura o su persistencia fallan, ANICAM informa el estado del evento.

AYUDA

- Si la Raspberry no llega al servidor, revise `URL_BACKEND`, la IP, `ping`,
  el puerto 8000, el firewall y el comando de Uvicorn.
- Si MongoDB no responde, compruebe que el servicio local esté iniciado,
  `MONGODB_URI=mongodb://localhost:27017` y la base `Ani_cam`.
- La reproducción de MP4 depende de Qt Multimedia y del códec disponible en el
  equipo; compruébela con un archivo en el sistema de destino.

La guía principal está en `README.md`. Para las instrucciones específicas de la
Raspberry Pi, consulte `raspberry_pi/README.md`.