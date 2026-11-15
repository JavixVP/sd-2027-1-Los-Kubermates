"""Servicio Boletos digitales.

Genera el boleto con un identificador único cuando Reservas confirma una compra.
Es idempotente por `reserva_id`: si Reservas reintenta la solicitud (porque la
primera vez este servicio no respondió a tiempo), aquí no se genera un boleto
duplicado — se devuelve el que ya existe (PRD sección 3 y 7).
"""
import logging
import secrets
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("boletos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.conectar()
    yield
    await db.cerrar()


app = FastAPI(title="Boletos digitales", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class BoletoSolicitud(BaseModel):
    reserva_id: UUID
    evento_id: UUID
    usuario_id: UUID


class Boleto(BaseModel):
    id: UUID
    reserva_id: UUID
    evento_id: UUID
    usuario_id: UUID
    codigo: str


@app.get("/salud")
async def salud():
    return {"estado": "ok"}


def _generar_codigo() -> str:
    return f"BOL-{secrets.token_hex(6).upper()}"


@app.post("/boletos", response_model=Boleto, status_code=201)
async def generar_boleto(cuerpo: BoletoSolicitud, idempotency_key: str | None = Header(default=None)):
    async with db.pool().acquire() as con:
        existente = await con.fetchrow(
            "SELECT id, reserva_id, evento_id, usuario_id, codigo FROM boletos WHERE reserva_id = $1",
            cuerpo.reserva_id,
        )
        if existente is not None:
            logger.info("Boleto ya existente para la reservación %s; no se genera otro", cuerpo.reserva_id)
            return dict(existente)

        fila = await con.fetchrow(
            "INSERT INTO boletos (reserva_id, evento_id, usuario_id, codigo) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (reserva_id) DO NOTHING "
            "RETURNING id, reserva_id, evento_id, usuario_id, codigo",
            cuerpo.reserva_id,
            cuerpo.evento_id,
            cuerpo.usuario_id,
            _generar_codigo(),
        )
        if fila is None:
            fila = await con.fetchrow(
                "SELECT id, reserva_id, evento_id, usuario_id, codigo FROM boletos WHERE reserva_id = $1",
                cuerpo.reserva_id,
            )
    return dict(fila)


@app.get("/boletos/{reserva_id}", response_model=Boleto)
async def obtener_boleto(reserva_id: UUID):
    async with db.pool().acquire() as con:
        fila = await con.fetchrow(
            "SELECT id, reserva_id, evento_id, usuario_id, codigo FROM boletos WHERE reserva_id = $1",
            reserva_id,
        )
    if fila is None:
        raise HTTPException(status_code=404, detail="Esta reservación todavía no tiene boleto")
    return dict(fila)
