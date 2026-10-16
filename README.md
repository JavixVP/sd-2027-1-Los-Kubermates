# Los Kubermates · Sistema de boletos y reservaciones de eventos

Sistema para consultar eventos, reservar lugares con cupo limitado,
pagar y recibir un boleto digital, inspirado en los problemas de
plataformas como Ticketmaster bajo demanda alta. El detalle completo
del problema, las decisiones y los criterios de aceptación está en
[`docs/PRD.md`](docs/PRD.md).

## Integrantes

- [@Oswaldo-F](https://github.com/Oswaldo-F) — Flores Herrera Oswaldo
- [@FerrRv](https://github.com/FerrRv) — Reyes Vázquez Fernando
- [@menavaledo](https://github.com/menavaledo) — Valencia Lerdo Dalia Jimena
- [@JavixVP](https://github.com/JavixVP) — Velasco Pacheco Javier

## Plan de ramas

Una rama por etapa de partición, como se vio en clase:

- `main` — este README y el PRD.
- `01-monolito` (rama actual) — los 6 módulos del PRD en un solo
  servicio FastAPI con una sola base PostgreSQL.
- `02-separacion`, `03-...` — separación progresiva en servicios
  independientes, Traefik como API gateway y réplicas de Reservas,
  según el diseño de PRD §7.

## Cómo se levanta

Requiere Docker y Docker Compose.

```bash
docker compose up --build
```

La API queda en `http://localhost:8000` (página interactiva de FastAPI) y PostgreSQL en el puerto `5432`.

### Flujo de prueba rápido (FastAPI)

```bash
# 1. Crear un usuario
curl -X POST localhost:8000/usuarios \
  -H "Content-Type: application/json" \
  -d '{"nombre": "Ada", "email": "ada@example.com"}'

# 2. Crear un evento con 2 lugares
curl -X POST localhost:8000/eventos \
  -H "Content-Type: application/json" \
  -d '{"nombre": "Concierto X", "fecha": "2026-12-01T20:00:00", "precio": 450, "cupo_total": 2}'

# 3. Reservar un lugar (usuario_id y evento_id de los pasos anteriores)
curl -X POST localhost:8000/reservas \
  -H "Content-Type: application/json" \
  -d '{"usuario_id": 1, "evento_id": 1}'

# 4. Pagar la reserva (resultado_forzado=aprobado para una demo
#    determinista; sin ese parámetro el resultado se simula al azar)
curl -X POST "localhost:8000/reservas/1/pago?resultado_forzado=aprobado" \
  -H "Content-Type: application/json" -d '{}'

# 5. Consultar el boleto generado
curl localhost:8000/reservas/1/boleto
```


## Estructura del repo

```
docs/PRD.md              PRD completo
docker-compose.yml        app + base de datos (rama 01-monolito)
app/
  Dockerfile
  requirements.txt
  src/
    main.py               arranque, routers, job de background
    database.py            conexión a PostgreSQL
    models.py               tablas: Usuario, Evento, Reserva, Pago, Boleto, Notificacion
    schemas.py               esquemas Pydantic de entrada/salida
    routers/
      usuarios.py
      eventos.py
      reservas.py            bloqueo pesimista + orquestación del flujo de compra
      pagos.py                 pago simulado
      boletos.py                 generación de boleto + reintento
      notificaciones.py         notificación + reintento
```
Cada archivo dentro de `routers/` representa una de las áreas principales definidas en el PRD, lo que facilita que más adelante puedan separarse en servicios independientes.


## Faltante

- Traefik como gateway y réplicas del servicio de Reservas.
