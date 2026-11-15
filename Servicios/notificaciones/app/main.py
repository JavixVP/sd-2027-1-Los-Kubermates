import asyncio
import logging
import os
import random
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from . import db

logger = logging.getLogger('notificaciones')
BARRIDO_SEGUNDOS = int(os.environ.get('BARRIDO_SEGUNDOS', '5'))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.conectar()
    app.state.tarea_reintentos = asyncio.create_task(_ciclo_reintentos())
    yield
    app.state.tarea_reintentos.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.tarea_reintentos
    db.cerrar()


app = FastAPI(title='Notificaciones', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


class NotificacionCrear(BaseModel):
    usuario_id: UUID
    tipo: str
    mensaje: str
    datos: dict = Field(default_factory=dict)
    fecha: str | None = None
    clave: str | None = None


class Notificacion(BaseModel):
    id: str
    usuario_id: str
    tipo: str
    mensaje: str
    datos: dict
    estado: str
    intentos: int
    creado_en: str


def _a_salida(doc: dict) -> dict:
    return {
        'id': doc['_id'],
        'usuario_id': doc['usuario_id'],
        'tipo': doc['tipo'],
        'mensaje': doc['mensaje'],
        'datos': doc['datos'],
        'estado': doc['estado'],
        'intentos': doc['intentos'],
        'creado_en': doc['creado_en'],
    }


def _intentar_envio(doc: dict) -> bool:
    if doc.get('datos', {}).get('forzar_falla'):
        return doc.get('intentos', 0) > 0
    return random.random() < 0.97


@app.get('/salud')
async def salud():
    return {'estado': 'ok'}


@app.post('/notificaciones', response_model=Notificacion, status_code=201)
async def crear_notificacion(cuerpo: NotificacionCrear):
    clave = cuerpo.clave or str(uuid4())
    actual = await db.coleccion().find_one({'_id': clave})
    if actual:
        return _a_salida(actual)
    doc = {
        '_id': clave,
        'usuario_id': str(cuerpo.usuario_id),
        'tipo': cuerpo.tipo,
        'mensaje': cuerpo.mensaje,
        'datos': cuerpo.datos,
        'estado': 'ENVIADA',
        'intentos': 0,
        'creado_en': cuerpo.fecha or datetime.now(timezone.utc).isoformat(),
    }
    if not _intentar_envio(doc):
        doc['estado'] = 'PENDIENTE'
    doc['intentos'] = 1
    try:
        await db.coleccion().insert_one(doc)
    except DuplicateKeyError:
        doc = await db.coleccion().find_one({'_id': clave})
    return _a_salida(doc)


@app.get('/notificaciones', response_model=list[Notificacion])
async def listar_notificaciones(usuario_id: UUID | None = None):
    filtro = {'usuario_id': str(usuario_id)} if usuario_id else {}
    cursor = db.coleccion().find(filtro).sort('creado_en', -1)
    return [_a_salida(doc) async for doc in cursor]


@app.get('/notificaciones/{notificacion_id}', response_model=Notificacion)
async def obtener_notificacion(notificacion_id: str):
    doc = await db.coleccion().find_one({'_id': notificacion_id})
    if doc is None:
        raise HTTPException(status_code=404, detail='Notificacion no encontrada')
    return _a_salida(doc)


async def _reintentar_pendientes() -> None:
    cursor = db.coleccion().find({'estado': 'PENDIENTE'}).limit(20)
    async for doc in cursor:
        exito = _intentar_envio(doc)
        await db.coleccion().update_one(
            {'_id': doc['_id'], 'estado': 'PENDIENTE'},
            {'$set': {'estado': 'ENVIADA' if exito else 'PENDIENTE'}, '$inc': {'intentos': 1}},
        )


async def _ciclo_reintentos() -> None:
    while True:
        try:
            await _reintentar_pendientes()
        except Exception:
            logger.exception('Error en el reintento de notificaciones')
        await asyncio.sleep(BARRIDO_SEGUNDOS)
