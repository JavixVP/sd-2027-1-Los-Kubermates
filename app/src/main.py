import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, SessionLocal
from .routers import usuarios, eventos, reservas, pagos, boletos, notificaciones
from .routers.boletos import generar_boleto
from .routers.notificaciones import notificar

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kubermates.background")

INTERVALO_BACKGROUND_SEGUNDOS = 15

# libera reservas expiradas y devuelve el cupo al evento
def _liberar_reservas_vencidas(db: Session) -> int:
    ahora = datetime.now(timezone.utc)
    vencidas = (
        db.query(models.Reserva)
        .filter(models.Reserva.estado == models.EstadoReserva.PENDIENTE)
        .filter(models.Reserva.expira_en < ahora)
        .all()
    )
    for reserva in vencidas:
        # Bloqueo pesimista para actualizar cupo de forma segura
        evento = db.query(models.Evento).filter_by(id=reserva.evento_id).with_for_update().first()
        reserva.estado = models.EstadoReserva.EXPIRADA
        evento.cupo_disponible += 1
    if vencidas:
        db.commit()
    return len(vencidas)


# reintenta generar boletos pendientes de compras confirmadas
def _reintentar_boletos_pendientes(db: Session) -> int:
    pendientes = (
        db.query(models.Boleto)
        .filter(models.Boleto.estado == models.EstadoBoleto.PENDIENTE)
        .all()
    )
    for boleto in pendientes:
        reserva = db.query(models.Reserva).get(boleto.reserva_id)
        if not reserva or reserva.estado != models.EstadoReserva.CONFIRMADA:
            continue
        generar_boleto(db, reserva.id, fallar=False)
        if boleto.estado == models.EstadoBoleto.GENERADO:
            notificar(
                db, reserva.usuario_id, reserva.id,
                tipo="boleto_generado",
                mensaje=f"Tu boleto para '{reserva.evento.nombre}' ya está listo: {boleto.codigo_unico}.",
            )
    if pendientes:
        db.commit()
    return len(pendientes)

# Reintenta el envío de notificaciones fallidas
def _reintentar_notificaciones_fallidas(db: Session) -> int:
    fallidas = (
        db.query(models.Notificacion)
        .filter(models.Notificacion.estado == models.EstadoNotificacion.FALLIDA)
        .all()
    )
    for n in fallidas:
        n.estado = models.EstadoNotificacion.ENVIADA
    if fallidas:
        db.commit()
    return len(fallidas)


# verificaciones para expiraciones y reintentos
async def _job_background():
    while True:
        await asyncio.sleep(INTERVALO_BACKGROUND_SEGUNDOS)
        db = SessionLocal()
        try:
            n1 = _liberar_reservas_vencidas(db)
            n2 = _reintentar_boletos_pendientes(db)
            n3 = _reintentar_notificaciones_fallidas(db)
            if n1 or n2 or n3:
                logger.info(
                    "ciclo de background: %s reservas expiradas, %s boletos reintentados, %s notificaciones reintentadas",
                    n1, n2, n3,
                )
        except Exception:
            logger.exception("fallo en el ciclo de background")
        finally:
            db.close()


# crea tablas y arranca la tarea de background
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    tarea = asyncio.create_task(_job_background())
    yield
    tarea.cancel()


# inicialización de FastAPI y registro de los 6 routers 
app = FastAPI(
    title="Los Kubermates · Boletos y reservaciones",
    description="Monolito inicial (rama 01-monolito) del sistema descrito en docs/PRD.md",
    lifespan=lifespan,
)

app.include_router(usuarios.router)
app.include_router(eventos.router)
app.include_router(reservas.router)
app.include_router(pagos.router)
app.include_router(boletos.router)
app.include_router(notificaciones.router)


@app.get("/salud")
def salud():
    return {"status": "ok"}