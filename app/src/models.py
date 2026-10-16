import enum
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import relationship

from .database import Base

# cada reservación aparta el lugar durante 10 minutos.
RESERVA_TTL_MINUTOS = 10
def ahora():
    return datetime.now(timezone.utc)

# Usuarios
class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    creado_en = Column(DateTime(timezone=True), default=ahora)


# Eventos
class Evento(Base):
    __tablename__ = "eventos"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(200), nullable=False)
    fecha = Column(DateTime(timezone=True), nullable=False)
    precio = Column(Float, nullable=False)
    # PRD §3: disponibilidad general por cupo, no asiento numerado.
    cupo_total = Column(Integer, nullable=False)
    cupo_disponible = Column(Integer, nullable=False)

# Reservas
class EstadoReserva(str, enum.Enum):
    PENDIENTE = "pendiente"    # lugar apartado
    CONFIRMADA = "confirmada"  # pago aprobado 
    RECHAZADA = "rechazada"    # pago rechazado
    EXPIRADA = "expirada"      # pasaron los 10 min sin pago


class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    evento_id = Column(Integer, ForeignKey("eventos.id"), nullable=False)
    estado = Column(Enum(EstadoReserva), default=EstadoReserva.PENDIENTE, nullable=False)
    creada_en = Column(DateTime(timezone=True), default=ahora)
    expira_en = Column(DateTime(timezone=True), nullable=False)

    evento = relationship("Evento")
    usuario = relationship("Usuario")

    @staticmethod
    def nueva_expiracion():
        return ahora() + timedelta(minutes=RESERVA_TTL_MINUTOS)


# Pagos
class EstadoPago(str, enum.Enum):
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True)
    reserva_id = Column(Integer, ForeignKey("reservas.id"), unique=True, nullable=False)
    monto = Column(Float, nullable=False)
    estado = Column(Enum(EstadoPago), nullable=False)
    idempotency_key = Column(String(64), unique=True, nullable=False)
    creado_en = Column(DateTime(timezone=True), default=ahora)


# Boletos digitales
class EstadoBoleto(str, enum.Enum):
    PENDIENTE = "pendiente"  # pago aprobado, pero la generación falló: queda para reintentar
    GENERADO = "generado"


class Boleto(Base):
    __tablename__ = "boletos"

    id = Column(Integer, primary_key=True)
    reserva_id = Column(Integer, ForeignKey("reservas.id"), unique=True, nullable=False)
    codigo_unico = Column(String(40), unique=True, nullable=True)
    estado = Column(Enum(EstadoBoleto), default=EstadoBoleto.PENDIENTE, nullable=False)
    creado_en = Column(DateTime(timezone=True), default=ahora)

    @staticmethod
    def generar_codigo():
        return f"BOL-{secrets.token_hex(6).upper()}"


# Notificaciones
class EstadoNotificacion(str, enum.Enum):
    ENVIADA = "enviada"
    FALLIDA = "fallida"


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    reserva_id = Column(Integer, ForeignKey("reservas.id"), nullable=False)
    tipo = Column(String(40), nullable=False)  # compra_exitosa | pago_rechazado | boleto_pendiente | boleto_generado
    mensaje = Column(Text, nullable=False)
    estado = Column(Enum(EstadoNotificacion), default=EstadoNotificacion.ENVIADA, nullable=False)
    creada_en = Column(DateTime(timezone=True), default=ahora)
