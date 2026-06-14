# Cargar la app de Celery al iniciar Django para que las tareas @shared_task
# queden registradas (patrón estándar de Celery + Django).
#
# DEFENSIVO: si Celery NO está instalado (p.ej. el venv de la web aún no corrió
# `pip install -r requirements.txt`, o un entorno solo-web sin las deps del
# worker), esto NO debe tumbar Daphne/Django ni el WebSocket de presencia.
# En ese caso la generación asíncrona del link de pago queda inactiva
# (create_tramite ya degrada con try/except), pero el resto del sistema funciona.
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except Exception as _celery_import_error:  # pragma: no cover
    celery_app = None
    __all__ = ()
    import logging
    logging.getLogger(__name__).warning(
        'Celery no disponible (%s); la generacion asincrona de links de pago '
        'queda inactiva. Instala las dependencias (pip install -r requirements.txt) '
        'y reinicia el worker.', _celery_import_error,
    )
