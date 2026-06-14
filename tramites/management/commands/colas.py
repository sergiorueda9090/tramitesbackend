"""
Muestra de un vistazo el estado de las colas de generación de links de pago:
  1) mensajes esperando en el broker (Redis),
  2) jobs por estado en la BD (la verdad final),
  3) workers conectados y tareas activas,
  4) los últimos jobs.

Uso:
    python manage.py colas
    python manage.py colas --watch        # refresca cada 2s (Ctrl+C para salir)
    python manage.py colas --watch --intervalo 5
"""
import time

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models import Count


class Command(BaseCommand):
    help = 'Estado de las colas de generación de links de pago (Celery + Redis + BD).'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true', help='Refresca en bucle.')
        parser.add_argument('--intervalo', type=int, default=2, help='Segundos entre refrescos (con --watch).')

    def handle(self, *args, **options):
        if options['watch']:
            try:
                while True:
                    self.stdout.write('\033[2J\033[H', ending='')  # limpia pantalla
                    self._snapshot()
                    time.sleep(max(1, options['intervalo']))
            except KeyboardInterrupt:
                self.stdout.write('\n(fin)')
        else:
            self._snapshot()

    # ------------------------------------------------------------------

    def _snapshot(self):
        self._cola_broker()
        self._estados_bd()
        self._workers()
        self._ultimos()
        self.stdout.write('')

    def _h(self, txt):
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n== {txt} =='))

    def _cola_broker(self):
        self._h('Mensajes esperando en la cola (Redis broker)')
        try:
            import redis
            r = redis.Redis.from_url(settings.CELERY_BROKER_URL)
            self.stdout.write(f"  esperando: {r.llen('celery')}   (broker: {settings.CELERY_BROKER_URL})")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  no se pudo leer el broker: {e}'))

    def _estados_bd(self):
        self._h('Jobs por estado (BD = verdad final)')
        from tramites.models import LinkPagoJob
        rows = list(LinkPagoJob.objects.values('estado').annotate(n=Count('id')).order_by('-n'))
        if not rows:
            self.stdout.write('  (sin jobs)')
        for r in rows:
            self.stdout.write(f"  {r['estado']:<12} {r['n']}")

    def _workers(self):
        self._h('Workers en vivo')
        try:
            from backend.celery import app
            insp = app.control.inspect(timeout=2)
            ping = insp.ping() or {}
            if not ping:
                self.stdout.write(self.style.WARNING('  ningún worker conectado (¿arrancaste el worker?)'))
                return
            active = insp.active() or {}
            for node in sorted(ping):
                n = len(active.get(node, []))
                self.stdout.write(self.style.SUCCESS(f'  {node}: online, {n} tarea(s) activa(s)'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  no se pudo inspeccionar: {e}'))

    def _ultimos(self):
        self._h('Últimos 10 jobs')
        from tramites.models import LinkPagoJob
        jobs = list(LinkPagoJob.objects.all()[:10])
        if not jobs:
            self.stdout.write('  (sin jobs)')
        for j in jobs:
            err = (j.error_mensaje or '').replace('\n', ' ')[:45]
            self.stdout.write(f"  tramite #{j.tramite_id:<5} {j.proveedor or '-':<9} {j.estado:<11} intentos={j.intentos}  {err}")
