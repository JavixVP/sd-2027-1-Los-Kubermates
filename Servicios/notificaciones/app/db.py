"""Acceso a la base documental del servicio Notificaciones (MongoDB): guarda los
mensajes enviados y los registros de envío a los usuarios (PRD sección 6)."""
import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

_cliente: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def conectar() -> AsyncIOMotorDatabase:
    global _cliente, _db
    if _db is None:
        _cliente = AsyncIOMotorClient(os.environ["MONGO_URI"])
        _db = _cliente[os.environ.get("MONGO_DB", "notificaciones")]
        await _db.notificaciones.create_index("usuario_id")
        await _db.notificaciones.create_index("estado")
    return _db


def cerrar() -> None:
    global _cliente, _db
    if _cliente is not None:
        _cliente.close()
        _cliente = None
        _db = None


def coleccion():
    assert _db is not None, "La conexión a Mongo todavía no se inicializa"
    return _db.notificaciones
