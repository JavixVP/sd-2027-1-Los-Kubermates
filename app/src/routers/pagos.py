import random
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/reservas/{reserva_id}/pago", tags=["pagos"])

PROBABILIDAD_APROBACION = 0.85


def procesar_pago(
    db: Session,
    reserva: "models.Reserva",
    idempotency_key: Optional[str],
    resultado_forzado: Optional[str] = None,
) -> models.Pago:
    pago_existente = db.query(models.Pago).filter_by(reserva_id=reserva.id).first()
    if pago_existente:
        # Reintento idempotente: No se vuelve a cobrar
        return pago_existente

    if resultado_forzado in ("aprobado", "rechazado"):
        aprobado = resultado_forzado == "aprobado"
    else:
        aprobado = random.random() < PROBABILIDAD_APROBACION

    pago = models.Pago(
        reserva_id=reserva.id,
        monto=reserva.evento.precio,
        estado=models.EstadoPago.APROBADO if aprobado else models.EstadoPago.RECHAZADO,
        idempotency_key=idempotency_key or str(uuid.uuid4()),
    )
    db.add(pago)
    db.flush()  # consulta el id sin cerrar la transacción que abrió reservas.py
    return pago


@router.get("", response_model=schemas.PagoOut)
def obtener_pago(reserva_id: int, db: Session = Depends(get_db)):
    pago = db.query(models.Pago).filter_by(reserva_id=reserva_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Esta reserva no tiene un pago registrado")
    return pago
