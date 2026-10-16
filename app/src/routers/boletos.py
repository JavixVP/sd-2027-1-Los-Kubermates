from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/reservas/{reserva_id}/boleto", tags=["boletos"])


def generar_boleto(db: Session, reserva_id: int, fallar: bool = False) -> models.Boleto:
    boleto = db.query(models.Boleto).filter_by(reserva_id=reserva_id).first()
    if boleto and boleto.estado == models.EstadoBoleto.GENERADO:
        # Ya existe y ya se generó: Al reinternar no crea uno nuevo.
        return boleto

    if not boleto:
        boleto = models.Boleto(reserva_id=reserva_id, estado=models.EstadoBoleto.PENDIENTE)
        db.add(boleto)

    if fallar:
        boleto.estado = models.EstadoBoleto.PENDIENTE
        boleto.codigo_unico = None
    else:
        boleto.codigo_unico = models.Boleto.generar_codigo()
        boleto.estado = models.EstadoBoleto.GENERADO

    db.flush()
    return boleto


@router.get("", response_model=schemas.BoletoOut)
def consultar_boleto(reserva_id: int, db: Session = Depends(get_db)):
    boleto = db.query(models.Boleto).filter_by(reserva_id=reserva_id).first()
    if not boleto:
        raise HTTPException(status_code=404, detail="Esta reserva no tiene boleto")
    return boleto


@router.post("/reintentar", response_model=schemas.BoletoOut)
def reintentar_boleto(reserva_id: int, db: Session = Depends(get_db)):

    reserva = db.query(models.Reserva).get(reserva_id)
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    if reserva.estado != models.EstadoReserva.CONFIRMADA:
        raise HTTPException(
            status_code=409,
            detail="Solo se genera boleto para una reserva confirmada (pago aprobado)",
        )
    boleto = generar_boleto(db, reserva_id, fallar=False)
    db.commit()
    db.refresh(boleto)
    return boleto
