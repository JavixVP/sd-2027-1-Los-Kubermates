"""Acceso a la base de datos del servicio Boletos digitales (dueño exclusivo de la
generación de boletos y la asignación de identificadores únicos)."""
import os
import asyncpg

_pool: asyncpg.Pool | None = None

DDL = """
CREATE TABLE IF NOT EXISTS boletos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Una reservación tiene a lo más un boleto: la llave única es lo que evita
    -- boletos duplicados cuando Reservas reintenta la generación (PRD sección 3,
    -- historia "Compra, pago y generación de boletos", criterio 5).
    reserva_id UUID NOT NULL UNIQUE,
    evento_id UUID NOT NULL,
    usuario_id UUID NOT NULL,
    codigo TEXT NOT NULL UNIQUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def conectar() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.environ["DB_HOST"],
            port=int(os.environ["DB_PORT"]),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.environ["DB_NAME"],
            min_size=1,
            max_size=10,
        )
        async with _pool.acquire() as con:
            await con.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
            await con.execute(DDL)
    return _pool


async def cerrar() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    assert _pool is not None, "La conexión a la base de datos todavía no se inicializa"
    return _pool
