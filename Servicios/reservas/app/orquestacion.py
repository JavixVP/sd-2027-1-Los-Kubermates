import logging
import os
from datetime import datetime, timezone
from uuid import UUID

import httpx

logger = logging.getLogger('reservas.orquestacion')

PAGOS_URL = os.environ.get('PAGOS_URL', 'http://pagos:8000')
BOLETOS_URL = os.environ.get('BOLETOS_URL', 'http://boletos:8000')
NOTIFICACIONES_URL = os.environ.get('NOTIFICACIONES_URL', 'http://notificaciones:8000')

TIMEOUT_PAGOS = float(os.environ.get('TIMEOUT_PAGOS_SEGUNDOS', '5'))
TIMEOUT_BOLETOS = float(os.environ.get('TIMEOUT_BOLETOS_SEGUNDOS', '5'))
TIMEOUT_NOTIFICACIONES = float(os.environ.get('TIMEOUT_NOTIFICACIONES_SEGUNDOS', '5'))


class ResultadoPago:
    def __init__(self, ok: bool, aprobado: bool | None = None,
                 pago_id: str | None = None, motivo: str = ''):
        self.ok = ok
        self.aprobado = aprobado
        self.pago_id = pago_id
        self.motivo = motivo


def _interpretar_pago(cuerpo: dict) -> ResultadoPago:
    return ResultadoPago(
        ok=True,
        aprobado=cuerpo['estado'] == 'APROBADO',
        pago_id=cuerpo['id'],
        motivo=cuerpo.get('motivo', ''),
    )


async def procesar_pago(cliente: httpx.AsyncClient, reserva_id: UUID, evento_id: UUID,
                        usuario_id: UUID, monto, resultado_forzado=None) -> ResultadoPago:
    try:
        resp = await cliente.post(
            f'{PAGOS_URL}/pagos',
            json={
                'reserva_id': str(reserva_id),
                'evento_id': str(evento_id),
                'usuario_id': str(usuario_id),
                'monto': str(monto),
                'resultado_forzado': resultado_forzado,
            },
            headers={'Idempotency-Key': str(reserva_id)},
            timeout=TIMEOUT_PAGOS,
        )
        if resp.status_code in (200, 201):
            return _interpretar_pago(resp.json())
        logger.warning('Pagos devolvio %s para %s', resp.status_code, reserva_id)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning('Resultado de pago incierto para %s: %s', reserva_id, exc)
    return ResultadoPago(ok=False, motivo='Resultado de pago pendiente de confirmar')


async def consultar_pago(cliente: httpx.AsyncClient, reserva_id: UUID) -> ResultadoPago | None:
    try:
        resp = await cliente.get(f'{PAGOS_URL}/pagos/{reserva_id}', timeout=TIMEOUT_PAGOS)
        if resp.status_code == 404:
            return None
        if resp.status_code == 200:
            return _interpretar_pago(resp.json())
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    return ResultadoPago(ok=False, motivo='No se pudo consultar el pago')


async def generar_boleto(cliente: httpx.AsyncClient, reserva_id: UUID, evento_id: UUID,
                          usuario_id: UUID) -> dict | None:
    try:
        resp = await cliente.post(
            f'{BOLETOS_URL}/boletos',
            json={'reserva_id': str(reserva_id), 'evento_id': str(evento_id), 'usuario_id': str(usuario_id)},
            headers={'Idempotency-Key': str(reserva_id)},
            timeout=TIMEOUT_BOLETOS,
        )
        if resp.status_code in (200, 201):
            return resp.json()
        logger.warning('Boletos devolvio %s para %s', resp.status_code, reserva_id)
    except httpx.HTTPError as exc:
        logger.warning('No se pudo generar boleto para %s: %s', reserva_id, exc)
    return None


async def notificar(cliente: httpx.AsyncClient, usuario_id: UUID, tipo: str,
                    mensaje: str, datos: dict) -> bool:
    reserva_id = datos.get('reserva_id', '')
    try:
        resp = await cliente.post(
            f'{NOTIFICACIONES_URL}/notificaciones',
            json={
                'usuario_id': str(usuario_id),
                'tipo': tipo,
                'mensaje': mensaje,
                'datos': datos,
                'fecha': datetime.now(timezone.utc).isoformat(),
                'clave': f'{reserva_id}:{tipo}' if reserva_id else None,
            },
            timeout=TIMEOUT_NOTIFICACIONES,
        )
        return resp.status_code in (200, 201)
    except httpx.HTTPError as exc:
        logger.warning('Notificaciones no respondio para %s: %s', usuario_id, exc)
        return False


async def precio_evento(cliente: httpx.AsyncClient, evento_id: UUID):
    from decimal import Decimal
    url = os.environ.get('EVENTOS_URL', 'http://eventos:8000')
    try:
        resp = await cliente.get(f'{url}/eventos/{evento_id}', timeout=5.0)
        if resp.status_code == 200:
            monto = Decimal(str(resp.json()['precio']))
            return monto if monto > 0 else None
    except (httpx.HTTPError, ValueError, KeyError, ArithmeticError):
        pass
    return None
