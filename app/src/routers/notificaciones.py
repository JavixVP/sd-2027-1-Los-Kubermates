from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(tags=["notificaciones"])

# Probabilidad de que el "envío" simulado falle, para poder demostrar
# el camino de reintento (criterio 5) sin depender de una falla real.
PROBABILIDAD_FALLA_ENVIO = 0.1


def notificar(db: Session, usuario_id: int, reserva_id: int, tipo: str, mensaje: str) -> models.Notificacion:
    import random

    exito = random.random() > PROBABILIDAD_FALLA_ENVIO
    notificacion = models.Notificacion(
        usuario_id=usuario_id,
        reserva_id=reserva_id,
        tipo=tipo,
        mensaje=mensaje,
        estado=models.EstadoNotificacion.ENVIADA if exito else models.EstadoNotificacion.FALLIDA,
    )
    db.add(notificacion)
    db.flush()
    return notificacion


@router.get("/usuarios/{usuario_id}/notificaciones", response_model=list[schemas.NotificacionOut])
def listar_notificaciones(usuario_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Notificacion)
        .filter_by(usuario_id=usuario_id)
        .order_by(models.Notificacion.creada_en.desc())
        .all()
    )


@router.post("/notificaciones/{notificacion_id}/reintentar", response_model=schemas.NotificacionOut)
def reintentar_notificacion(notificacion_id: int, db: Session = Depends(get_db)):
    notificacion = db.query(models.Notificacion).get(notificacion_id)
    if not notificacion:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    if notificacion.estado == models.EstadoNotificacion.ENVIADA:
        return notificacion  # ya se había enviado: no se duplica

    notificacion.estado = models.EstadoNotificacion.ENVIADA
    db.commit()
    db.refresh(notificacion)
    return notificacion
