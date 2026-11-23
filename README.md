# ANICAM — Cámara Trampa Inteligente para Reserva Natural

ANICAM permite que el Panel de control solicite una foto o un video a una Raspberry Pi con cámara CSI. FastAPI coordina la comunicación y es el único componente que accede a MongoDB. La base de datos existente y obligatoria es **`Ani_cam`**.

> Esta guía describe la versión actual de ANICAM; no crea una base nueva ni prepara una arquitectura futura. También existe una versión esencial en texto plano: [`README.txt`](README.txt). Para las instrucciones específicas de la Raspberry Pi, consulte [`raspberry_pi/README.md`](raspberry_pi/README.md).

## Arquitectura y flujo

```text
Panel de control PySide6 ──HTTP──> FastAPI ──> MongoDB Ani_cam
                              ^
                              │ HTTP (consulta periódica y resultado)
Raspberry Pi + Picamera2 ────┘
             │
             └── JPEG / MP4 en su tarjeta SD
```

1. El Panel de control crea una petición `foto` o `video`.
2. La Raspberry consulta periódicamente si hay una petición pendiente para su cámara, realiza la captura y conserva el archivo local.
3. La Raspberry envía el JPEG o MP4 cerrado a FastAPI. El servidor registra el metadato pendiente, confirma B2 y luego actualiza `peticiones`, `archivos` y, cuando corresponde, el evento PIR relacionado.

El PIR es un flujo automático separado de las peticiones manuales. El Panel de control guarda por cámara si se habilita, el tipo de captura y el período de espera. La Raspberry lee esa configuración al detectar movimiento; `CapturadorPIR` coordina el sensor y la cámara en un hilo propio. Una detección aceptada guarda la captura en SD y usa `/api/v1/peticiones/pir/archivo` para que FastAPI cree el evento y el metadato del archivo, confirme B2 y marque el evento como `ejecutado`. Si una captura aceptada falla antes de iniciar la persistencia, la Raspberry informa el error por `/api/v1/peticiones/pir/error`. Ninguna de esas rutas crea una petición PIR pendiente. Los movimientos durante una captura o el período de espera se descartan.

## Responsabilidades de los componentes

- **Panel de control (PySide6):** administra cámaras, guarda sus parámetros PIR, crea peticiones manuales y consulta los historiales y archivos.
- **Servidor (FastAPI):** centraliza las rutas HTTP, valida los datos, accede a MongoDB `Ani_cam`, sube capturas a B2 y devuelve enlaces privados temporales.
- **Raspberry Pi (PySide6 y Picamera2):** consulta peticiones manuales por consulta periódica, atiende el sensor PIR opcional y conserva las capturas en su tarjeta SD antes de enviarlas a FastAPI.
- **MongoDB y Backblaze B2:** MongoDB conserva datos y metadatos; B2 conserva la copia privada de los archivos. Sólo el servidor se conecta directamente a ambos.

## Instalación y orden de inicio

El orden importa porque cada componente depende del anterior:

1. **Inicie MongoDB local.** La base existente y obligatoria es `Ani_cam`; no cree ni migre otra. Copie `backend/.env.example` como `backend/.env`. Mantenga `MONGODB_URI=mongodb://localhost:27017`, `MONGODB_DATABASE=Ani_cam` y `MONGODB_TIMEOUT_MS=5000`. `backend/.env` está ignorado por Git.

   ```powershell
   cd backend
   Copy-Item .env.example .env
   ```

   En Windows, compruebe el servicio con `Get-Service MongoDB`; si está detenido, ejecútelo como administrador con `Start-Service MongoDB`. También puede verificar la conexión con `mongosh --host localhost --port 27017`.

2. **Instale las dependencias e inicie el servidor** desde `backend`:

   ```powershell
   cd backend
   pip install -r requirements.txt
   uvicorn inicio:app --host 0.0.0.0 --port 8000 --reload
   ```

   `uvicorn` sirve FastAPI; `inicio:app` busca el objeto `app` de `inicio.py`; `--host 0.0.0.0` escucha en todas las interfaces de la PC, `--port 8000` fija el puerto y `--reload` reinicia durante desarrollo. Pruebe `http://localhost:8000/health`: debe responder `{"status":"ok"}`. Si falla, revise que el servicio local esté iniciado, que la URI sea `mongodb://localhost:27017` y que `MONGODB_DATABASE` siga siendo `Ani_cam`. El servidor hace `ping` a MongoDB tanto al iniciar como en `/health`; los mensajes de error no imprimen la URI.

   `uvicorn inicio:app --reload` usa la configuración predeterminada y puede dejar el servicio accesible solo desde la propia PC. Para una Raspberry remota use siempre el comando completo anterior.

3. **Compruebe la red.** Obtenga la IPv4 de la PC con `ipconfig`. Desde la Raspberry ejecute `ping IP_DE_LA_PC`; las respuestas indican conectividad. En una red local normalmente ambos dispositivos comparten red, por Wi-Fi o Ethernet, pero lo indispensable es que puedan comunicarse entre sí.

4. **Prepare la Raspberry.** Siga [`raspberry_pi/README.md`](raspberry_pi/README.md). Antes de iniciar, configure `URL_BACKEND` con la IP de la PC y el prefijo de la API:

   ```bash
   export URL_BACKEND="http://192.168.1.100:8000/api/v1"
   export CAMARA_ID="camara001"
   python3 inicio.py
   ```

   La IP es un ejemplo. `localhost` y `127.0.0.1` siempre significan *el mismo dispositivo*: en la Raspberry no representan la PC. El puerto `8000` debe coincidir con Uvicorn.

5. **Inicie el Panel de control** en otra terminal de la PC:

   ```powershell
   cd aplicacion_escritorio
   pip install -r requirements.txt
   python inicio.py
   ```

   Si el Panel de control se ejecuta desde otra PC de la red, defina antes `ANICAM_API_BASE_URL` con la IPv4 de la PC que ejecuta FastAPI; por defecto conserva `http://127.0.0.1:8000/api/v1`:

   ```powershell
   $env:ANICAM_API_BASE_URL = "http://192.168.1.100:8000/api/v1"
   python inicio.py
   ```

   Inicie sesión, seleccione una cámara y cree una petición de prueba. La Raspberry mostrará la conexión y ejecutará el trabajo pendiente. El Panel de control consulta el historial de peticiones automáticamente cada cinco segundos en un hilo de trabajo, por lo que el estado cambia sin pulsar **Actualizar** ni bloquear la interfaz. Al seleccionar una petición ejecutada, su visor lateral usa la URL prefirmada temporal de B2 para mostrar la fotografía o reproducir el video; no es una transmisión en vivo. FastAPI clasifica el archivo de una foto como `imagen` y con MIME `image/jpeg`, mientras que la petición conserva el valor técnico `foto`; el Panel de control reconoce ambos contratos. Las fotos se descargan en segundo plano con Qt Network y se ajustan sin deformarse. El visor conserva **Abrir en navegador** como respaldo para enlaces vencidos o videos cuyo códec no pueda decodificar Qt Multimedia.

   En **Cámaras**, primero seleccione la cámara: el Panel de control consulta `archivos` por su `id_camara` y muestra a la izquierda una tabla de nombre, tipo, fecha, origen y estado. La tabla usa los campos reales `nombre_archivo`, `tipo`/`tipo_contenido`, `fecha_hora` (o la fecha de captura/creación que exista) y `estado_subida`. El origen sólo se muestra como **Petición** si el documento contiene `peticion_id`, o como **Evento** si contiene `id_evento`; si faltan ambas relaciones o están las dos, muestra **Desconocido**. Para clasificar esos archivos sin relación hace falta que el productor guarde uno de esos identificadores en `archivos`; el Panel de control no lo deduce del nombre del archivo.

   Seleccionar una fila de archivo es pasivo. Sólo **Visualizar** solicita la URL temporal y la carga en el visor lateral propio de Cámaras, sin ventanas emergentes ni cambios en los visores de Peticiones o Eventos. El visor de Cámaras mantiene su propia URL, descarga, reproductor y controles; el botón **Abrir en navegador** es la alternativa explícita. Las cámaras sin archivos y los errores de URL, descarga o formato se informan dentro de la sección o del visor, sin alertas redundantes.

   La reproducción integrada de MP4 requiere que la instalación de Qt incluya el componente de Qt Multimedia y soporte para el códec del archivo (las capturas de ANICAM se generan como H.264/MP4). La interfaz muestra reproducción, pausa y volumen cuando ese servidor está disponible; la compatibilidad real debe comprobarse con un MP4 en el sistema de destino.

## Dependencias reales de Raspberry Pi

En Raspberry Pi OS se instalan con el gestor del sistema porque Picamera2 se integra con `libcamera`:

```bash
sudo apt update
sudo apt install -y python3-picamera2 ffmpeg python3-pyside6.qtwidgets python3-pyside6.qtmultimedia
```

`requests` y el rango de PySide6 están declarados en `raspberry_pi/requirements.txt`. No instale Picamera2 con `pip`. Antes de abrir ANICAM compruebe la cámara con `rpicam-hello -t 3s`.

## Backblaze B2 privado

El servidor usa B2 mediante `boto3`; la Raspberry guarda primero cada JPEG o MP4 en su tarjeta SD y luego lo envía por HTTP a FastAPI. Solo FastAPI posee las variables `B2_DIRECCION_SERVICIO`, `B2_NOMBRE_DEPOSITO`, `B2_REGION`, `B2_IDENTIFICADOR_CLAVE` y `B2_CLAVE_SECRETA` de `backend/.env`. Complete esos valores directamente en ese archivo, sin subirlo a Git. B2 confirma la subida antes de que la petición pase a `ejecutado`; un fallo conserva el archivo local y registra la petición como error. Para visualizar, el Panel de control solicita al servidor una URL prefirmada de cinco minutos: la URL no se guarda en MongoDB ni vuelve público el depósito.

## Persistencia de metadatos de capturas

La causa corregida era el orden de confirmación: el flujo anterior subía primero a B2 y recién después insertaba o actualizaba MongoDB, sin comprobar el resultado de esas escrituras. Una caída de MongoDB después de la subida podía dejar un objeto en B2 sin documento en `Ani_cam.archivos`.

Ahora la ruta HTTP de carga registra primero un metadato con `estado_subida: pendiente` y los campos existentes `id_camara`, `peticion_id`, `tipo`, `nombre_archivo`, `fecha_hora`, `clave_b2` y `tipo_contenido`. Sólo tras esa escritura se envía el archivo a B2. Luego el servidor verifica que `archivos` quede `confirmada` y que `peticiones` quede `ejecutado`; ante un fallo de MongoDB devuelve error y no informa éxito falso. Si B2 rechaza la carga, el metadato, la petición y, cuando corresponda, el evento PIR quedan en estado `error`. En una captura PIR aceptada, el servidor registra un evento `pendiente` y un metadato con `id_evento`; al confirmar B2 marca ambos como `ejecutado`. Si B2 rechaza el archivo, marca el evento y el metadato como `error`. Las detecciones que no llegan a reservar la cámara (por ejemplo, mientras una captura manual la usa) se descartan y no crean eventos.

Para inspeccionar la misma instancia que usa FastAPI, en la PC del servidor abra `mongosh`, ejecute `use Ani_cam` y consulte `db.archivos.find({id_camara:"camara001"})`. Los registros históricos pueden usar formatos de fecha distintos, por lo que la ruta HTTP los ordena cronológicamente antes de responder al Panel de control. Si aparece un registro `pendiente`, el metadato previo a B2 quedó persistido y debe revisarse el log de Uvicorn para distinguir fallo de B2 de una confirmación de MongoDB.

Al iniciar, FastAPI crea de forma idempotente índices **no únicos** para la consulta periódica de peticiones, los historiales y las relaciones de archivos. No cambia documentos ni borra información histórica. Si el usuario de MongoDB no puede crearlos, el servidor sigue disponible y deja una advertencia segura en el log.

## Problemas frecuentes

| Situación | Qué comprobar |
| --- | --- |
| La Raspberry no llega al servidor | IP y `URL_BACKEND`, ping, FastAPI iniciado con `--host 0.0.0.0`, puerto 8000 y firewall de la PC. |
| La PC funciona pero la Raspberry no | No use `localhost`: desde la Raspberry apunta a ella misma. Use la IPv4 de la PC. |
| MongoDB no funciona | Confirme `Get-Service MongoDB`, `MONGODB_URI=mongodb://localhost:27017`, `MONGODB_DATABASE=Ani_cam` y la respuesta de `/health`. |
| No se instala una dependencia de cámara | Use `apt` para Picamera2, libcamera/`rpicam-*`, ffmpeg y los paquetes PySide6 de Raspberry Pi OS. |
| Un MP4 no se reproduce | La aplicación informa el error sin cerrarse. Revise la sección «Reproducción de video» en [`raspberry_pi/README.md`](raspberry_pi/README.md). |

## Alcance actual

 La Raspberry conserva las capturas en SD; B2 guarda la copia privada y MongoDB sus metadatos y relaciones. Los eventos automáticos se crean para detecciones PIR aceptadas; las peticiones manuales no crean eventos.