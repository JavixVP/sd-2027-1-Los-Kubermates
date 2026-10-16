from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/eventos", tags=["eventos"])


def _a_evento_out(evento: models.Evento) -> schemas.EventoOut:
    return schemas.EventoOut(
        id=evento.id,
        nombre=evento.nombre,
        fecha=evento.fecha,
        precio=evento.precio,
        cupo_total=evento.cupo_total,
        cupo_disponible=evento.cupo_disponible,
        disponible=evento.cupo_disponible > 0,
    )


@router.post("", response_model=schemas.EventoOut, status_code=201)
def crear_evento(datos: schemas.EventoCrear, db: Session = Depends(get_db)):
    evento = models.Evento(
        nombre=datos.nombre,
        fecha=datos.fecha,
        precio=datos.precio,
        cupo_total=datos.cupo_total,
        cupo_disponible=datos.cupo_total,
    )
    db.add(evento)
    db.commit()
    db.refresh(evento)
    return _a_evento_out(evento)


@router.get("", response_model=list[schemas.EventoOut])
def listar_eventos(db: Session = Depends(get_db)):
    # Criterio #3: si no hay eventos, el llamador recibe una lista vacía;
    # el mensaje ("no hay eventos para consultar") lo compone el cliente.
    eventos = db.query(models.Evento).order_by(models.Evento.fecha).all()
    return [_a_evento_out(e) for e in eventos]


@router.get("/{evento_id}", response_model=schemas.EventoOut)
def obtener_evento(evento_id: int, db: Session = Depends(get_db)):
    evento = db.query(models.Evento).get(evento_id)
    if not evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return _a_evento_out(evento)
