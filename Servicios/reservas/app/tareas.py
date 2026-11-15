import asyncio
import logging
import os
from uuid import UUID

import httpx

from . import db, flujo, orquestacion

logger = logging.getLogger('reservas.tareas')
BARRIDO_SEGUNDOS = int(os.environ.get('BARRIDO_SEGUNDOS', '5'))


async def _expirar_reservas_vencidas(con) -> None:
    async with con.transaction():
        vencidas = await con.fetch(
            "SELECT id, evento_id FROM reservas WHERE estado = 'PENDIENTE' "
            'AND expira_en < now() FOR UPDATE SKIP LOCKED'
        )
        for fila in vencidas:
            await con.execute("UPDATE reservas SET estado = 'EXPIRADA' WHERE id = $1", fila['id'])
            await con.execute(
                'UPDATE disponibilidad SET disponibles = disponibles + 1 WHERE evento_id = $1',
                fila['evento_id'],
            )


async def _reconciliar_pago(cliente: httpx.AsyncClient, fila) -> None:
    reserva_id = fila['id']
    resultado = await orquestacion.consultar_pago(cliente, reserva_id)
    if resultado is None:
        monto = await orquestacion.precio_evento(cliente, fila['evento_id'])
        if monto is None:
            return
        resultado = await orquestacion.procesar_pago(
            cliente, reserva_id, fila['evento_id'], fila['usuario_id'], monto,
        )
    if resultado.ok:
        await flujo.finalizar_pago(reserva_id, resultado)
        await flujo.asegurar_resultado(cliente, reserva_id)


async def _ciclo(cliente: httpx.AsyncClient) -> None:
    while True:
        try:
            async with db.pool().acquire() as con:
                await _expirar_reservas_vencidas(con)
                en_proceso = await con.fetch(
                    "SELECT id, evento_id, usuario_id FROM reservas WHERE estado = 'PAGO_EN_PROCESO' "
                    "AND pago_iniciado_en < now() - interval '12 seconds' LIMIT 20"
                )
                pendientes = await con.fetch(
                    "SELECT id FROM reservas WHERE (estado = 'CONFIRMADA' AND "
                    "(boleto_estado = 'PENDIENTE' OR notificado = false)) "
                    "OR (estado = 'FALLIDA' AND notificado = false) LIMIT 20"
                )
            for fila in en_proceso:
                await _reconciliar_pago(cliente, fila)
            for fila in pendientes:
                await flujo.asegurar_resultado(cliente, fila['id'])
        except Exception:
            logger.exception('Error en el barrido de Reservas')
        await asyncio.sleep(BARRIDO_SEGUNDOS)


def iniciar_barrido(cliente: httpx.AsyncClient) -> asyncio.Task:
    return asyncio.create_task(_ciclo(cliente))
