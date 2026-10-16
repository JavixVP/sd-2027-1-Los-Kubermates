from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=schemas.UsuarioOut, status_code=201)
def crear_usuario(datos: schemas.UsuarioCrear, db: Session = Depends(get_db)):
    existente = db.query(models.Usuario).filter_by(email=datos.email).first()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")

    usuario = models.Usuario(nombre=datos.nombre, email=datos.email)
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.get("/{usuario_id}", response_model=schemas.UsuarioOut)
def obtener_usuario(usuario_id: int, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).get(usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@router.get("", response_model=list[schemas.UsuarioOut])
def listar_usuarios(db: Session = Depends(get_db)):
    return db.query(models.Usuario).all()
