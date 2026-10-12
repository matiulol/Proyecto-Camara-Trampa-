ANICAM — Cámara Trampa Inteligente para Reserva Natural
========================================================

ANICAM conecta un Dashboard PySide6, FastAPI, MongoDB Ani_cam y una Raspberry
Pi con Picamera2. El Dashboard solicita una foto o video; la Raspberry consulta
la petición por HTTP, captura el archivo en su tarjeta SD e informa el resultado
al backend. FastAPI es el único componente que usa MongoDB.

Base de datos obligatoria: Ani_cam
Conexión local: MONGODB_URI=mongodb://localhost:27017 en backend/.env.

ORDEN DE INICIO
1. Iniciar MongoDB local. En backend, copiar .env.example como .env y mantener
   MONGODB_URI=mongodb://localhost:27017,
   MONGODB_DATABASE=Ani_cam y MONGODB_TIMEOUT_MS=5000. .env está ignorado por
   Git. En Windows, comprobar el servicio con Get-Service MongoDB e iniciarlo
   como administrador con Start-Service MongoDB si está detenido.
2. En backend instalar dependencias y ejecutar:

   uvicorn main:app --host 0.0.0.0 --port 8000 --reload

   Uvicorn ejecuta FastAPI; main:app busca app en main.py; 0.0.0.0 permite
   conexiones desde la red, 8000 es el puerto y --reload reinicia en desarrollo.
   Comprobar http://localhost:8000/health. Debe responder status ok.
3. Obtener la IPv4 de la PC (ipconfig) y, desde la Raspberry, ejecutar:

   ping IP_DE_LA_PC

   Si responde, hay conectividad. Si no, revisar red, IP, firewall, backend y
   que FastAPI no esté limitado a localhost.
4. En la Raspberry configurar e iniciar:

   export URL_BACKEND="http://192.168.1.100:8000/api/v1"
   export CAMARA_ID="camara001"
   python3 main.py

   La IP es solo ejemplo. localhost y 127.0.0.1 en la Raspberry representan la
   propia Raspberry, no la PC. El puerto debe coincidir con Uvicorn.
5. Iniciar desktop_app con python main.py, iniciar sesión y crear una petición.

DEPENDENCIAS DE RASPBERRY
sudo apt update
sudo apt install -y python3-picamera2 ffmpeg python3-pyside6.qtwidgets python3-pyside6.qtmultimedia

Picamera2 no debe instalarse con pip; se integra con libcamera mediante apt.
Compruebe la cámara con: rpicam-hello -t 3s

BACKBLAZE B2 PRIVADO
Instalar dependencias del backend con: pip install -r requirements.txt.
Completar únicamente en backend/.env: B2_DIRECCION_SERVICIO,
B2_NOMBRE_DEPOSITO, B2_REGION, B2_IDENTIFICADOR_CLAVE y B2_CLAVE_SECRETA.
La Raspberry guarda primero en SD y transmite el archivo a FastAPI; el backend
sube a B2 y genera enlaces temporales al visualizar. Si B2 falla, el archivo
local se conserva y la petición no queda ejecutada.

PROBLEMAS FRECUENTES
- Raspberry sin backend: revisar URL_BACKEND, IP, ping, puerto 8000, firewall y
  el comando completo de Uvicorn.
- MongoDB: confirmar que el servicio local está iniciado, que
  MONGODB_URI=mongodb://localhost:27017 y que la base sea Ani_cam.
- Video: si Qt Multimedia no puede decodificar un MP4, ANICAM muestra el error
  y sigue abierta. Revisar las dependencias multimedia de Raspberry Pi OS.

Documentación detallada: README.md y docs/DOCUMENTACION_ETAPA_1.txt.
