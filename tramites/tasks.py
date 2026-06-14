"""
Tareas Celery para la generación asíncrona del link de pago de un trámite.

La tarea decide proveedor (Previsora / Mundial), llama al generador externo
(lento), persiste el resultado en `LinkPagoJob` y empuja el estado al listado de
Trámites por WebSocket (reutilizando `users.realtime.notify_view_sync` +
`PresenceConsumer`). El estado vive en BD, así que aunque el worker muera a mitad
(`acks_late`) o el usuario recargue, nada se pierde.
"""
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import LinkPagoJob
from .services.generar_link import (
    resolver_proveedor, obtener_correo_aleatorio, construir_payload,
    post_json_externo, extraer_url_pago,
)
from users.realtime import notify_view_sync


def _emit(job, event_type):
    """Empuja el estado del job al listado de Trámites por WebSocket."""
    try:
        notify_view_sync(
            view_id='tramites_list',
            event_type=event_type,
            payload={
                'tramite_id': job.tramite_id,
                'link_pago': {
                    'estado': job.estado,
                    'proveedor': job.proveedor,
                    'url_pago': job.url_pago,
                    'correo_usado': job.correo_usado,
                    'error_mensaje': job.error_mensaje,
                    'intentos': job.intentos,
                },
            },
        )
    except Exception as e:
        print(f'WARNING: notify_view_sync (_emit) fallo: {e}')


@shared_task(bind=True, acks_late=True, max_retries=0, default_retry_delay=20)
def generar_link_pago(self, job_id):
    try:
        job = LinkPagoJob.objects.select_related('tramite').get(pk=job_id)
    except LinkPagoJob.DoesNotExist:
        return

    # Idempotencia: si ya quedó exitoso, no repetir.
    if job.estado == 'exitoso' and job.url_pago:
        return

    tramite = job.tramite
    job.proveedor = resolver_proveedor(tramite)
    job.estado = 'en_proceso'
    job.intentos += 1
    job.task_id = self.request.id or ''
    job.save(update_fields=['proveedor', 'estado', 'intentos', 'task_id', 'updated_at'])
    _emit(job, 'link_pago_started_event')

    correo_obj = obtener_correo_aleatorio()
    if not correo_obj:
        job.estado = 'error'
        job.error_mensaje = 'No hay correos aleatorios activos en el pool.'
        job.save(update_fields=['estado', 'error_mensaje', 'updated_at'])
        _emit(job, 'link_pago_done_event')
        return

    url, payload = construir_payload(tramite, job.proveedor, correo_obj.correo)
    job.payload_enviado = payload
    job.correo_usado = correo_obj.correo

    data, error = post_json_externo(url, payload)

    if error:
        # ¿Quedan reintentos? Si sí, reintenta con backoff (default_retry_delay).
        # Si no, marca error.
        #
        # OJO: NO usar `except self.MaxRetriesExceededError`, porque
        # `self.retry(exc=...)` al agotar los reintentos RE-LANZA `exc` (el
        # Exception que le pasamos), NO MaxRetriesExceededError. Atraparlo así
        # dejaría el job colgado en 'en_proceso'. Por eso chequeamos los
        # reintentos a mano antes de reintentar.
        if self.request.retries < self.max_retries:
            raise self.retry(exc=Exception(error))
        job.estado = 'error'
        job.error_mensaje = error
        job.save(update_fields=['estado', 'error_mensaje', 'correo_usado',
                                'payload_enviado', 'updated_at'])
        _emit(job, 'link_pago_done_event')
        return

    url_pago = extraer_url_pago(data)
    job.respuesta_cruda = data
    if url_pago:
        job.estado = 'exitoso'
        job.url_pago = url_pago
        job.error_mensaje = ''
        correo_obj.registrar_uso()   # marca uso del correo del pool
    else:
        job.estado = 'error'
        job.error_mensaje = 'El servicio respondió pero sin URL de pago.'

    job.save(update_fields=['estado', 'url_pago', 'error_mensaje', 'correo_usado',
                            'payload_enviado', 'respuesta_cruda', 'updated_at'])
    _emit(job, 'link_pago_done_event')


@shared_task
def reencolar_jobs_colgados():
    """
    Red de seguridad (corre por Celery beat cada ~2 min): si Redis o el worker
    estuvieron caídos al encolar, o un job quedó 'en_proceso' colgado, lo
    re-encola. Garantía dura de 'no se pierde ninguno'.
    """
    limite = timezone.now() - timedelta(minutes=10)
    qs = LinkPagoJob.objects.filter(
        estado__in=['pendiente', 'en_proceso'],
        updated_at__lt=limite,
    )
    for job in qs[:200]:   # tope por corrida para no inundar
        generar_link_pago.delay(job.id)
