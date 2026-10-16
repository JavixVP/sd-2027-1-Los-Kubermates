"""Esquemas Pydantic de entrada/salida para cada módulo."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict


# Usuarios 
class UsuarioCrear(BaseModel):
    nombre: str
    email: EmailStr

class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    email: str
    creado_en: datetime


# Eventos
class EventoCrear(BaseModel):
    nombre: str
    fecha: datetime
    precio: float
    cupo_total: int

class EventoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    fecha: datetime
    precio: float
    cupo_total: int
    cupo_disponible: int
    disponible: bool  # cupo_disponible > 0 — criterio de aceptación #4


# Reservas 
class ReservaCrear(BaseModel):
    usuario_id: int
    evento_id: int


class ReservaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    usuario_id: int
    evento_id: int
    estado: str
    creada_en: datetime
    expira_en: datetime


# Pagos
class PagoCrear(BaseModel):
    # Clave de idempotencia enviada por el cliente (PRD §7 "Manejo de
    # fallas"): si la misma solicitud de pago se reintenta por timeout,
    # el servicio reconoce que ya se procesó y no cobra dos veces.
    idempotency_key: Optional[str] = None


class PagoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reserva_id: int
    monto: float
    estado: str
    creado_en: datetime


# Boletos digitales 
class BoletoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reserva_id: int
    codigo_unico: Optional[str]
    estado: str
    creado_en: datetime


# Notificaciones 
class NotificacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    usuario_id: int
    reserva_id: int
    tipo: str
    mensaje: str
    estado: str
    creada_en: datetime
