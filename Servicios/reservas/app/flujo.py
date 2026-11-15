from uuid import UUID

import httpx

from . import db, orquestacion


async def finalizar_pago(reserva_id: UUID, pago: orquestacion.ResultadoPago) -> None:
    if not pago.ok:
        return
    async with db.pool().acquire() as con:
        async with con.transaction():
            reserva = await con.fetchrow(
                'SELECT estado, evento_id FROM reservas WHERE id = $1 FOR UPDATE',
                reserva_id,
            )
            if not reserva or reserva['estado'] != 'PAGO_EN_PROCESO':
                return
            if pago.aprobado:
                await con.execute(
                    "UPDATE reservas SET estado = 'CONFIRMADA', pago_estado = 'APROBADO', "
                    "pago_id = $2, boleto_estado = 'PENDIENTE' WHERE id = $1",
                    reserva_id, UUID(pago.pago_id),
                )
            else:
                await con.execute(
                    "UPDATE reservas SET estado = 'FALLIDA', pago_estado = 'RECHAZADO', pago_id = $2 "
                    'WHERE id = $1',
                    reserva_id, UUID(pago.pago_id),
                )
                await con.execute(
                    'UPDATE disponibilidad SET disponibles = disponibles + 1 WHERE evento_id = $1',
                    reserva['evento_id'],
                )


async def asegurar_resultado(cliente: httpx.AsyncClient, reserva_id: UUID) -> None:
    async with db.pool().acquire() as con:
        reserva = await con.fetchrow(
            'SELECT id, evento_id, usuario_id, estado, boleto_estado, boleto_id, notificado '
            'FROM reservas WHERE id = $1',
            reserva_id,
        )
    if not reserva:
        return
    usuario_id = reserva['usuario_id']
    evento_id = reserva['evento_id']
    datos = {'reserva_id': str(reserva_id), 'evento_id': str(evento_id)}

    if reserva['estado'] == 'FALLIDA':
        if not reserva['notificado']:
            ok = await orquestacion.notificar(
                cliente, usuario_id, 'COMPRA_RECHAZADA',
                'Tu pago fue rechazado y tu reserva se libero.', datos,
            )
            if ok:
                async with db.pool().acquire() as con:
                    await con.execute(
                        "UPDATE reservas SET notificado = true WHERE id = $1 AND estado = 'FALLIDA'",
                        reserva_id,
                    )
        return

    if reserva['estado'] != 'CONFIRMADA':
        return

    boleto_id = reserva['boleto_id']
    if reserva['boleto_estado'] != 'GENERADO':
        boleto = await orquestacion.generar_boleto(cliente, reserva_id, evento_id, usuario_id)
        if boleto:
            boleto_id = UUID(boleto['id'])
            async with db.pool().acquire() as con:
                await con.execute(
                    "UPDATE reservas SET boleto_id = $2, boleto_estado = 'GENERADO' "
                    "WHERE id = $1 AND estado = 'CONFIRMADA'",
                    reserva_id, boleto_id,
                )
        else:
            await orquestacion.notificar(
                cliente, usuario_id, 'COMPRA_CONFIRMADA_BOLETO_PENDIENTE',
                'Tu compra esta confirmada y tu boleto se generara cuando el servicio este disponible.',
                datos,
            )
            return

    if not reserva['notificado']:
        datos['boleto_id'] = str(boleto_id)
        ok = await orquestacion.notificar(
            cliente, usuario_id, 'COMPRA_EXITOSA',
            'Tu compra fue confirmada y tu boleto ya esta disponible.', datos,
        )
        if ok:
            async with db.pool().acquire() as con:
                await con.execute(
                    "UPDATE reservas SET notificado = true WHERE id = $1 AND estado = 'CONFIRMADA' "
                    "AND boleto_estado = 'GENERADO'",
                    reserva_id,
                )
