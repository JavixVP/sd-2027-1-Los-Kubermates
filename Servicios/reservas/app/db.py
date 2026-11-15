import os
import asyncpg

_pool: asyncpg.Pool | None = None

DDL = """
CREATE TABLE IF NOT EXISTS disponibilidad (
    evento_id UUID PRIMARY KEY,
    capacidad INTEGER NOT NULL CHECK (capacidad > 0),
    disponibles INTEGER NOT NULL CHECK (disponibles >= 0 AND disponibles <= capacidad)
);

CREATE TABLE IF NOT EXISTS reservas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evento_id UUID NOT NULL REFERENCES disponibilidad (evento_id),
    usuario_id UUID NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',
    creada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_en TIMESTAMPTZ NOT NULL,
    pago_id UUID,
    pago_estado TEXT,
    pago_iniciado_en TIMESTAMPTZ,
    boleto_id UUID,
    boleto_estado TEXT NOT NULL DEFAULT 'NO_APLICA'
        CHECK (boleto_estado IN ('NO_APLICA', 'PENDIENTE', 'GENERADO')),
    notificado BOOLEAN NOT NULL DEFAULT false
);

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS pago_iniciado_en TIMESTAMPTZ;
ALTER TABLE reservas DROP CONSTRAINT IF EXISTS reservas_estado_check;
ALTER TABLE reservas ADD CONSTRAINT reservas_estado_check
    CHECK (estado IN ('PENDIENTE', 'PAGO_EN_PROCESO', 'CONFIRMADA', 'FALLIDA', 'EXPIRADA'));

CREATE INDEX IF NOT EXISTS ix_reservas_expiracion
    ON reservas (estado, expira_en) WHERE estado = 'PENDIENTE';
CREATE INDEX IF NOT EXISTS ix_reservas_boleto_pendiente
    ON reservas (boleto_estado) WHERE boleto_estado = 'PENDIENTE';
"""


async def conectar() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.environ['DB_HOST'],
            port=int(os.environ['DB_PORT']),
            user=os.environ['DB_USER'],
            password=os.environ['DB_PASSWORD'],
            database=os.environ['DB_NAME'],
            min_size=1,
            max_size=10,
        )
        async with _pool.acquire() as con:
            await con.execute('SELECT pg_advisory_lock(7654321)')
            try:
                await con.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto;')
                await con.execute(DDL)
            finally:
                await con.execute('SELECT pg_advisory_unlock(7654321)')
    return _pool


async def cerrar() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    assert _pool is not None
    return _pool
