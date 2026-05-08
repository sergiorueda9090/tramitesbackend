"""Backfill del ledger CuatroPorMil desde los registros financieros existentes.

Recorre todos los productores configurados en `cuatro_por_mil.signals.PRODUCERS`
y, para cada fila con `cuatro_por_mil > 0`, inserta o actualiza la fila espejo.
Es idempotente: correrlo varias veces no duplica registros (la clave natural
`(modulo, registro_id)` es única).

Uso:
    python manage.py backfill_cuatro_por_mil               # todos los módulos
    python manage.py backfill_cuatro_por_mil --modulo gastos
    python manage.py backfill_cuatro_por_mil --include-deleted
    python manage.py backfill_cuatro_por_mil --dry-run
"""

from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from cuatro_por_mil.signals import PRODUCERS, sync_ledger


class Command(BaseCommand):
    help = 'Sincroniza el ledger cuatro_por_mil con los registros existentes en los módulos productores.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--modulo',
            type=str,
            default=None,
            help='Sólo procesar este módulo (e.g. gastos, recepcion_pago).',
        )
        parser.add_argument(
            '--include-deleted',
            action='store_true',
            help='Incluir registros con deleted_at != NULL (los reflejará como soft-deleted).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Sólo reportar qué se haría, sin escribir nada.',
        )

    def handle(self, *args, **options):
        target_modulo   = options.get('modulo')
        include_deleted = options.get('include_deleted')
        dry_run         = options.get('dry_run')

        producers = PRODUCERS
        if target_modulo:
            producers = [p for p in PRODUCERS if p['modulo'] == target_modulo]
            if not producers:
                self.stderr.write(self.style.ERROR(f"Módulo desconocido: {target_modulo}"))
                self.stderr.write(f"Disponibles: {', '.join(p['modulo'] for p in PRODUCERS)}")
                return

        total_procesados = 0
        total_con_4xmil  = 0

        for producer in producers:
            try:
                model = apps.get_model(producer['app'], producer['model'])
            except LookupError:
                self.stderr.write(self.style.WARNING(
                    f"Modelo no encontrado: {producer['app']}.{producer['model']} — se omite"
                ))
                continue

            qs = model.objects.all()
            if not include_deleted:
                qs = qs.filter(deleted_at__isnull=True)

            count_total = qs.count()

            valor_field = producer['valor_field']
            qs_con_4xmil = qs.filter(**{f'{valor_field}__gt': 0})
            count_4xmil  = qs_con_4xmil.count()

            self.stdout.write(self.style.HTTP_INFO(
                f"[{producer['modulo']}] {producer['app']}.{producer['model']} — "
                f"{count_total} registros totales, {count_4xmil} con 4x1000 > 0"
            ))

            if dry_run:
                total_procesados += count_total
                total_con_4xmil  += count_4xmil
                continue

            iterable = qs.select_related(
                producer['tarjeta_attr'], producer['usuario_attr']
            ).iterator() if not include_deleted else qs.iterator()

            with transaction.atomic():
                for instance in iterable:
                    sync_ledger(producer, instance)

            total_procesados += count_total
            total_con_4xmil  += count_4xmil

            self.stdout.write(self.style.SUCCESS(
                f"  → {producer['modulo']}: sincronizados {count_total} registros"
            ))

        prefix = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Total: {total_procesados} registros recorridos, "
            f"{total_con_4xmil} con 4x1000 > 0."
        ))
