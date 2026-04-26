"""
Helpers para emitir eventos de tiempo real desde codigo sincrono (vistas DRF).

Uso tipico desde una vista (function-based, sincrona):

    from users.realtime import notify_view_sync

    notify_view_sync(
        view_id='tramites_list',
        event_type='tramite_removed_event',
        payload={'tramite_id': tramite.id, 'reason': 'sent_to_pasarela'},
    )

El consumer `PresenceConsumer` debe tener un metodo del mismo nombre que
`event_type` para reenviar el mensaje al cliente WebSocket.
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def _view_group(view_id):
    """Mismo nombre de grupo que usa PresenceConsumer._view_group."""
    safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(view_id))
    return f'view_{safe}'


def notify_view_sync(view_id, event_type, payload=None):
    """Emite un evento al grupo de una vista. Llamable desde codigo sincrono."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    group = _view_group(view_id)
    message = {'type': event_type}
    if payload:
        message.update(payload)
    async_to_sync(channel_layer.group_send)(group, message)
