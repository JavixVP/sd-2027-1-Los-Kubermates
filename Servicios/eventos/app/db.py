"""Acceso a la base de datos del servicio Eventos (dueño de fechas, lugar, capacidad y precio)."""
import os
import asyncpg

_pool: asyncpg.Pool | None = None

DDL = """
CREATE TABLE IF NOT EXISTS eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre TEXT NOT NULL,
    lugar TEXT NOT NULL,
    fecha TIMESTAMPTZ NOT NULL,
    precio NUMERIC(10, 2) NOT NULL,
    capacidad INTEGER NOT NULL CHECK (capacidad >= 0),
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
