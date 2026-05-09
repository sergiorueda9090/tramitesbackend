"""Backfill de Utilidad desde TramiteFinalizado existentes.

Recorre todos los registros de `finalizados_tramites.TramiteFinalizado` y, por
cada uno, hace `update_or_create` de `utilidades.Utilidad`. Es idempotente
gracias a la OneToOneField (correrlo varias veces no duplica filas).

Uso:
    python manage.py backfill_utilidades
    python manage.py backfill_utilidades --include-deleted
    python manage.py backfill_utilidades --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from finalizados_tramites.models import TramiteFinalizado
from utilidades.models import Utilidad


class Command(BaseCommand):
    help = 'Sincroniza la tabla utilidades con los TramiteFinalizado existentes.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--include-deleted',
            action='store_true',
            help='Incluir TramiteFinalizado con deleted_at != NULL.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Sólo reportar qué se haría, sin escribir nada.',
        )

    def handle(self, *args, **options):
        include_deleted = options.get('include_deleted')
        dry_run         = options.get('dry_run')

        qs = TramiteFinalizado.objects.all()
        if not include_deleted:
            qs = qs.filter(deleted_at__isnull=True)

        total = qs.count()
        self.stdout.write(self.style.HTTP_INFO(
            f"TramiteFinalizado a procesar: {total} "
            f"({'incluye eliminados' if include_deleted else 'sólo activos'})"
        ))

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY-RUN] Se crearían/actualizarían {total} filas en utilidades."
            ))
            return

        creados      = 0
        actualizados = 0

        with transaction.atomic():
            for tf in qs.iterator():
                _, created = Utilidad.objects.update_or_create(
                    tramite_finalizado=tf,
                    defaults={
                        'fecha':              tf.pago_confirmado_at,
                        'placa':              tf.placa or '',
                        'comision_proveedor': tf.comision,
                        'cilindraje':         tf.cilindraje or '',
                        'modelo':              tf.modelo or '',
                        'chasis':              tf.chasis or '',
                    },
                )
                if created:
                    creados += 1
                else:
                    actualizados += 1

        self.stdout.write(self.style.SUCCESS(
            f"Backfill completo: {creados} creados, {actualizados} actualizados "
            f"({creados + actualizados}/{total})."
        ))
