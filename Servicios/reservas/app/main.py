import asyncio
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, flujo, orquestacion, tareas

RESERVA_TTL_SEGUNDOS = int(os.environ.get('RESERVA_TTL_SEGUNDOS', '600'))
USUARIOS_URL = os.environ.get('USUARIOS_URL', 'http://usuarios:8000')


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.conectar()
    app.state.cliente_http = httpx.AsyncClient()
    app.state.tarea_barrido = tareas.iniciar_barrido(app.state.cliente_http)
    yield
    app.state.tarea_barrido.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.tarea_barrido
    await app.state.cliente_http.aclose()
    await db.cerrar()


app = FastAPI(title='Reservas', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


class DisponibilidadCrear(BaseModel):
    evento_id: UUID
    capacidad: int = Field(gt=0)


class Disponibilidad(BaseModel):
    evento_id: UUID
    capacidad: int
    disponibles: int


class ReservaCrear(BaseModel):
    evento_id: UUID
    usuario_id: UUID


class Reserva(BaseModel):
    id: UUID
    evento_id: UUID
    usuario_id: UUID
    estado: str
    creada_en: datetime | None = None
    expira_en: datetime
    pago_estado: str | None = None
    boleto_id: UUID | None = None
    boleto_estado: str


CAMPOS_RESERVA = (
    'id, evento_id, usuario_id, estado, creada_en, expira_en, '
    'pago_estado, boleto_id, boleto_estado'
)


@app.get('/salud')
async def salud():
    return {'estado': 'ok'}


@app.post('/reservas/disponibilidad', response_model=Disponibilidad, status_code=201)
async def inicializar_disponibilidad(cuerpo: DisponibilidadCrear):
    async with db.pool().acquire() as con:
        fila = await con.fetchrow(
            'INSERT INTO disponibilidad (evento_id, capacidad, disponibles) '
            'VALUES ($1, $2, $2) ON CONFLICT (evento_id) DO NOTHING '
            'RETURNING evento_id, capacidad, disponibles',
            cuerpo.evento_id, cuerpo.capacidad,
        )
        if fila is None:
            fila = await con.fetchrow(
                'SELECT evento_id, capacidad, disponibles FROM disponibilidad WHERE evento_id = $1',
                cuerpo.evento_id,
            )
    return dict(fila)


@app.get('/reservas/disponibilidad/{evento_id}', response_model=Disponibilidad)
async def consultar_disponibilidad(evento_id: UUID):
    async with db.pool().acquire() as con:
        fila = await con.fetchrow(
            'SELECT evento_id, capacidad, disponibles FROM disponibilidad WHERE evento_id = $1',
            evento_id,
        )
    if fila is None:
        raise HTTPException(status_code=404, detail='Disponibilidad no configurada para este evento')
    return dict(fila)


async def _verificar_usuario(usuario_id: UUID):
    try:
        respuesta = await app.state.cliente_http.get(
            f'{USUARIOS_URL}/usuarios/{usuario_id}', timeout=5.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail='Usuarios no esta disponible') from exc
    if respuesta.status_code == 404:
        raise HTTPException(status_code=404, detail='Usuario no encontrado')
    if respuesta.status_code != 200:
        raise HTTPException(status_code=503, detail='No se pudo comprobar el usuario')


@app.post('/reservas', response_model=Reserva, status_code=201)
async def crear_reserva(cuerpo: ReservaCrear):
    await _verificar_usuario(cuerpo.usuario_id)
    async with db.pool().acquire() as con:
        async with con.transaction():
            disp = await con.fetchrow(
                'SELECT disponibles FROM disponibilidad WHERE evento_id = $1 FOR UPDATE',
                cuerpo.evento_id,
            )
            if disp is None:
                raise HTTPException(status_code=404, detail='Evento inexistente o sin disponibilidad configurada')
            if disp['disponibles'] < 1:
                raise HTTPException(status_code=409, detail='No hay lugares disponibles para este evento')
            await con.execute(
                'UPDATE disponibilidad SET disponibles = disponibles - 1 WHERE evento_id = $1',
                cuerpo.evento_id,
            )
            fila = await con.fetchrow(
                'INSERT INTO reservas (evento_id, usuario_id, expira_en) '
                "VALUES ($1, $2, now() + ($3::int * interval '1 second')) "
                f'RETURNING {CAMPOS_RESERVA}',
                cuerpo.evento_id, cuerpo.usuario_id, RESERVA_TTL_SEGUNDOS,
            )
    return dict(fila)


@app.get('/reservas/{reserva_id}', response_model=Reserva)
async def obtener_reserva(reserva_id: UUID):
    async with db.pool().acquire() as con:
        fila = await con.fetchrow(
            f'SELECT {CAMPOS_RESERVA} FROM reservas WHERE id = $1',
            reserva_id,
        )
    if fila is None:
        raise HTTPException(status_code=404, detail='Reservacion no encontrada')
    return dict(fila)


@app.get('/reservas', response_model=list[Reserva])
async def listar_reservas(usuario_id: UUID):
    async with db.pool().acquire() as con:
        filas = await con.fetch(
            f'SELECT {CAMPOS_RESERVA} FROM reservas '
            'WHERE usuario_id = $1 ORDER BY creada_en DESC',
            usuario_id,
        )
    return [dict(f) for f in filas]


@app.post('/reservas/{reserva_id}/pago', response_model=Reserva)
async def pagar_reserva(reserva_id: UUID,
                        resultado_forzado: Literal['aprobado', 'rechazado'] | None = None):
    cliente = app.state.cliente_http
    async with db.pool().acquire() as con:
        reserva = await con.fetchrow(
            'SELECT evento_id, usuario_id, estado FROM reservas WHERE id = $1', reserva_id,
        )
    if not reserva:
        raise HTTPException(status_code=404, detail='Reservacion no encontrada')
    if reserva['estado'] in ('CONFIRMADA', 'PAGO_EN_PROCESO'):
        return await obtener_reserva(reserva_id)
    if reserva['estado'] != 'PENDIENTE':
        raise HTTPException(status_code=409, detail='Esta reservacion ya no puede pagarse')

    monto = await orquestacion.precio_evento(cliente, reserva['evento_id'])
    if monto is None:
        raise HTTPException(status_code=503, detail='No se pudo obtener el precio del evento')

    expirada = False
    estado_actual = None
    async with db.pool().acquire() as con:
        async with con.transaction():
            actual = await con.fetchrow(
                'SELECT evento_id, estado, expira_en FROM reservas WHERE id = $1 FOR UPDATE',
                reserva_id,
            )
            estado_actual = actual['estado']
            if estado_actual == 'PENDIENTE':
                vencida = await con.fetchval('SELECT now() >= $1', actual['expira_en'])
                if vencida:
                    await con.execute(
                        "UPDATE reservas SET estado = 'EXPIRADA' WHERE id = $1", reserva_id,
                    )
                    await con.execute(
                        'UPDATE disponibilidad SET disponibles = disponibles + 1 WHERE evento_id = $1',
                        actual['evento_id'],
                    )
                    expirada = True
                else:
                    await con.execute(
                        "UPDATE reservas SET estado = 'PAGO_EN_PROCESO', "
                        "pago_estado = 'PENDIENTE', pago_iniciado_en = now() WHERE id = $1",
                        reserva_id,
                    )
    if expirada:
        raise HTTPException(status_code=409, detail='La reservacion expiro y se libero el cupo')
    if estado_actual != 'PENDIENTE':
        return await obtener_reserva(reserva_id)

    resultado = await orquestacion.procesar_pago(
        cliente, reserva_id, reserva['evento_id'],
        reserva['usuario_id'], monto, resultado_forzado,
    )
    await flujo.finalizar_pago(reserva_id, resultado)
    if resultado.ok:
        await flujo.asegurar_resultado(cliente, reserva_id)
    return await obtener_reserva(reserva_id)
