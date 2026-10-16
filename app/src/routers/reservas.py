from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from .pagos import procesar_pago
from .boletos import generar_boleto
from .notificaciones import notificar

router = APIRouter(prefix="/reservas", tags=["reservas"])


def _vencida(reserva: models.Reserva) -> bool:
    expira = reserva.expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    return reserva.estado == models.EstadoReserva.PENDIENTE and expira < datetime.now(timezone.utc)


def _expirar_si_corresponde(db: Session, reserva: models.Reserva) -> models.Reserva:

    if _vencida(reserva):
        evento = db.query(models.Evento).filter_by(id=reserva.evento_id).with_for_update().first()
        reserva.estado = models.EstadoReserva.EXPIRADA
        evento.cupo_disponible += 1
        db.commit()
        db.refresh(reserva)
    return reserva


@router.post("", response_model=schemas.ReservaOut, status_code=201)
def crear_reserva(datos: schemas.ReservaCrear, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).get(datos.usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # --- Bloqueo pesimista ---
    # FOR UPDATE bloquea la fila hasta el commit/rollback de esta
    # transacción: ninguna otra solicitud puede leer ni modificar el
    # cupo de este evento mientras tanto, sin importar cuántas copias
    # del servicio de Reservas estén corriendo.

    evento = (
        db.query(models.Evento)
        .filter_by(id=datos.evento_id)
        .with_for_update()
        .first()
    )
    if not evento:
        db.rollback()
        raise HTTPException(status_code=404, detail="Evento no encontrado")

    if evento.cupo_disponible <= 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="No hay disponibilidad para este evento")

    evento.cupo_disponible -= 1
    reserva = models.Reserva(
        usuario_id=datos.usuario_id,
        evento_id=datos.evento_id,
        estado=models.EstadoReserva.PENDIENTE,
        expira_en=models.Reserva.nueva_expiracion(),
    )
    db.add(reserva)
    db.commit()  # libera el lock FOR UPDATE
    db.refresh(reserva)
    return reserva


@router.get("/{reserva_id}", response_model=schemas.ReservaOut)
def obtener_reserva(reserva_id: int, db: Session = Depends(get_db)):
    reserva = db.query(models.Reserva).get(reserva_id)
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    reserva = _expirar_si_corresponde(db, reserva)
    return reserva


@router.post("/{reserva_id}/pago", response_model=schemas.PagoOut)
def pagar_reserva(
    reserva_id: int,
    datos: schemas.PagoCrear,
    resultado_forzado: str | None = None,
    fallar_boleto: bool = False,
    db: Session = Depends(get_db),
):

    reserva = db.query(models.Reserva).get(reserva_id)
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    reserva = _expirar_si_corresponde(db, reserva)
    if reserva.estado == models.EstadoReserva.EXPIRADA:
        raise HTTPException(status_code=409, detail="La reservación expiró, el lugar ya se liberó")
    if reserva.estado != models.EstadoReserva.PENDIENTE:
        raise HTTPException(status_code=409, detail=f"La reserva ya está en estado '{reserva.estado.value}'")

    # 1) Pagos
    pago = procesar_pago(db, reserva, datos.idempotency_key, resultado_forzado)

    if pago.estado == models.EstadoPago.RECHAZADO:
        # Compra no se confirma, se libera el lugar.
        evento = db.query(models.Evento).filter_by(id=reserva.evento_id).with_for_update().first()
        evento.cupo_disponible += 1
        reserva.estado = models.EstadoReserva.RECHAZADA
        notificar(
            db, reserva.usuario_id, reserva.id,
            tipo="pago_rechazado",
            mensaje=f"Tu pago para '{reserva.evento.nombre}' fue rechazado. El lugar fue liberado.",
        )
        db.commit()
        db.refresh(pago)
        return pago

    # El pago se aprobó, la compra se confirma pase lo que pase con el boleto después.
    reserva.estado = models.EstadoReserva.CONFIRMADA

    # 3) Boletos digitales
    boleto = generar_boleto(db, reserva.id, fallar=fallar_boleto)

    # 4) Notificaciones
    if boleto.estado == models.EstadoBoleto.GENERADO:
        notificar(
            db, reserva.usuario_id, reserva.id,
            tipo="compra_exitosa",
            mensaje=(
                f"Compra confirmada para '{reserva.evento.nombre}'. "
                f"Tu boleto es {boleto.codigo_unico}."
            ),
        )
    else:
        # Boleto pendiente, se reintenta automáticamente.
        notificar(
            db, reserva.usuario_id, reserva.id,
            tipo="boleto_pendiente",
            mensaje=(
                f"Tu compra para '{reserva.evento.nombre}' está confirmada. "
                "Tu boleto se está generando, te avisamos en cuanto esté listo."
            ),
        )

    db.commit()
    db.refresh(pago)
    return pago
