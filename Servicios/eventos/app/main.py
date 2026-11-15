import os
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db

RESERVAS_URL = os.environ.get('RESERVAS_URL', 'http://reservas:8000')


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.conectar()
    app.state.cliente_http = httpx.AsyncClient(timeout=5.0)
    yield
    await app.state.cliente_http.aclose()
    await db.cerrar()


app = FastAPI(title='Eventos', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


class EventoCrear(BaseModel):
    nombre: str = Field(min_length=1)
    lugar: str = Field(min_length=1)
    fecha: datetime
    precio: Decimal = Field(gt=0)
    capacidad: int = Field(gt=0)


class Evento(BaseModel):
    id: UUID
    nombre: str
    lugar: str
    fecha: datetime
    precio: Decimal
    capacidad: int
    cupo_restante: int | None = None


@app.get('/salud')
async def salud():
    return {'estado': 'ok'}


async def _cupo_restante(cliente: httpx.AsyncClient, evento_id: UUID, capacidad: int) -> int | None:
    try:
        respuesta = await cliente.get(f'{RESERVAS_URL}/reservas/disponibilidad/{evento_id}')
        if respuesta.status_code == 200:
            return respuesta.json()['disponibles']
        if respuesta.status_code == 404:
            nueva = await cliente.post(
                f'{RESERVAS_URL}/reservas/disponibilidad',
                json={'evento_id': str(evento_id), 'capacidad': capacidad},
            )
            if nueva.status_code in (200, 201):
                return nueva.json()['disponibles']
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    return None


@app.post('/eventos', response_model=Evento, status_code=201)
async def crear_evento(cuerpo: EventoCrear):
    async with db.pool().acquire() as con:
        fila = await con.fetchrow(
            'INSERT INTO eventos (nombre, lugar, fecha, precio, capacidad) '
            'VALUES ($1, $2, $3, $4, $5) '
            'RETURNING id, nombre, lugar, fecha, precio, capacidad',
            cuerpo.nombre, cuerpo.lugar, cuerpo.fecha, cuerpo.precio, cuerpo.capacidad,
        )
    evento = dict(fila)
    evento['cupo_restante'] = await _cupo_restante(
        app.state.cliente_http, evento['id'], evento['capacidad'],
    )
    return evento


@app.get('/eventos', response_model=list[Evento])
async def listar_eventos():
    async with db.pool().acquire() as con:
        filas = await con.fetch(
            'SELECT id, nombre, lugar, fecha, precio, capacidad FROM eventos ORDER BY fecha'
        )
    eventos = [dict(fila) for fila in filas]
    for evento in eventos:
        evento['cupo_restante'] = await _cupo_restante(
            app.state.cliente_http, evento['id'], evento['capacidad'],
        )
    return eventos


@app.get('/eventos/{evento_id}', response_model=Evento)
async def obtener_evento(evento_id: UUID):
    async with db.pool().acquire() as con:
        fila = await con.fetchrow(
            'SELECT id, nombre, lugar, fecha, precio, capacidad FROM eventos WHERE id = $1',
            evento_id,
        )
    if fila is None:
        raise HTTPException(status_code=404, detail='Evento no encontrado')
    evento = dict(fila)
    evento['cupo_restante'] = await _cupo_restante(
        app.state.cliente_http, evento_id, evento['capacidad'],
    )
    return evento
