from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.conectar()
    yield
    await db.cerrar()


app = FastAPI(title='Pagos', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


class PagoSolicitud(BaseModel):
    reserva_id: UUID
    evento_id: UUID
    usuario_id: UUID
    monto: Decimal
    resultado_forzado: Literal['aprobado', 'rechazado'] | None = None


class Pago(BaseModel):
    id: UUID
    reserva_id: UUID
    estado: str
    motivo: str
    monto: Decimal


@app.get('/salud')
async def salud():
    return {'estado': 'ok'}


@app.post('/pagos', response_model=Pago, status_code=201)
async def procesar_pago(cuerpo: PagoSolicitud):
    async with db.pool().acquire() as con:
        existente = await con.fetchrow(
            'SELECT id, reserva_id, estado, motivo, monto FROM pagos WHERE reserva_id = $1',
            cuerpo.reserva_id,
        )
        if existente:
            return dict(existente)

        if cuerpo.monto <= 0:
            estado, motivo = 'RECHAZADO', 'Monto invalido'
        elif cuerpo.resultado_forzado == 'rechazado':
            estado, motivo = 'RECHAZADO', 'Pago rechazado en la simulacion'
        else:
            estado, motivo = 'APROBADO', ''

        fila = await con.fetchrow(
            'INSERT INTO pagos (reserva_id, evento_id, usuario_id, monto, estado, motivo) '
            'VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (reserva_id) DO NOTHING '
            'RETURNING id, reserva_id, estado, motivo, monto',
            cuerpo.reserva_id, cuerpo.evento_id, cuerpo.usuario_id,
            cuerpo.monto, estado, motivo,
        )
        if fila is None:
            fila = await con.fetchrow(
                'SELECT id, reserva_id, estado, motivo, monto FROM pagos WHERE reserva_id = $1',
                cuerpo.reserva_id,
            )
    return dict(fila)


@app.get('/pagos/{reserva_id}', response_model=Pago)
async def obtener_pago(reserva_id: UUID):
    from fastapi import HTTPException
    async with db.pool().acquire() as con:
        fila = await con.fetchrow(
            'SELECT id, reserva_id, estado, motivo, monto FROM pagos WHERE reserva_id = $1',
            reserva_id,
        )
    if fila is None:
        raise HTTPException(status_code=404, detail='No hay pago registrado para esta reservacion')
    return dict(fila)
