# Cámara Trampa Inteligente

Proyecto escolar 2026 para una cámara trampa inteligente de reserva natural.

La etapa actual implementa:

- Backend FastAPI.
- Conexión con MongoDB usando exclusivamente `Ani_cam`.
- Login básico con `usuarios`.
- CRUD básico de `camaras`.
- Gestión de `peticiones` para solicitar foto o video a una cámara.
- Consulta visual de `eventos` existentes.
- App de escritorio PySide6 con login y dashboard.

Flujo actual:

```text
Dashboard -> FastAPI -> MongoDB
```

Flujo futuro:

```text
Dashboard -> FastAPI -> Raspberry -> Cámara -> respuesta
```

Importante: la Raspberry todavía no está conectada al backend. Los eventos no se crean desde peticiones ni desde el dashboard.

Documentación detallada: `docs/DOCUMENTACION_ETAPA_1.txt`.
