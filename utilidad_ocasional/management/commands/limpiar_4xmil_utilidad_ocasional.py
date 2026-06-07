"""Limpieza de 4x1000 en utilidades ocasionales historicas.

A partir del cambio de regla, la utilidad ocasional NO genera 4x1000 (ni
ganancia ni perdida). Este comando corrige los registros creados antes del
cambio:

1. UtilidadOcasional con cuatro_por_mil != 0  -> cuatro_por_mil=0, total=valor.
2. Espejos en el ledger CuatroPorMil (modulo='utilidad_ocasional'):
   - revierte su asiento contable de 4x1000 (idempotente).
   - soft-delete del espejo (consistente con el comportamiento de la senal
     cuando el valor pasa a 0).

Uso:
    python manage.py limpiar_4xmil_utilidad_ocasional --dry-run
    python manage.py limpiar_4xmil_utilidad_ocasional
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from utilidad_ocasional.models import UtilidadOcasional
from cuatro_por_mil.models import CuatroPorMil
from movimiento_contable.services import revertir_asiento


MODULO = 'utilidad_ocasional'


class Command(BaseCommand):
    help = 'Limpia el 4x1000 historico de las utilidades ocasionales (ya no aplica).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Muestra lo que haria sin escribir cambios.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        utilidades = UtilidadOcasional.objects.exclude(cuatro_por_mil=Decimal('0'))
        espejos = CuatroPorMil.objects.filter(modulo=MODULO)

        self.stdout.write(self.style.NOTICE(
            f"UtilidadOcasional con 4x1000 != 0: {utilidades.count()}\n"
            f"Espejos CuatroPorMil ({MODULO}): {espejos.count()}\n"
            f"(dry_run={dry_run})"
        ))

        if dry_run:
            for u in utilidades.order_by('id'):
                self.stdout.write(
                    f"  [DRY] UtilidadOcasional #{u.id}: cuatro_por_mil {u.total} -> total={u.valor}"
                )
            for r in espejos.order_by('id'):
                accion = 'revertir asiento + soft-delete' if r.deleted_at is None else 'revertir asiento'
                self.stdout.write(
                    f"  [DRY] CuatroPorMil #{r.id} (registro {r.registro_id}, asiento={r.asiento_id}): {accion}"
                )
            self.stdout.write(self.style.NOTICE("\nDry-run: no se escribio nada."))
            return

        utilidades_ok = espejos_ok = errores = 0

        for u in utilidades.order_by('id'):
            try:
                with transaction.atomic():
                    UtilidadOcasional.objects.filter(pk=u.pk).update(
                        cuatro_por_mil=Decimal('0'), total=u.valor
                    )
                utilidades_ok += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] UtilidadOcasional #{u.id} -> cuatro_por_mil=0, total={u.valor}"
                ))
            except Exception as e:
                errores += 1
                self.stdout.write(self.style.ERROR(f"  [ERR] UtilidadOcasional #{u.id}: {e}"))

        for r in espejos.order_by('id'):
            try:
                with transaction.atomic():
                    revertir_asiento(r.asiento_id)
                    CuatroPorMil.objects.filter(pk=r.pk).update(asiento_id=None)
                    if r.deleted_at is None:
                        r.refresh_from_db(fields=['asiento_id'])
                        r.soft_delete()
                espejos_ok += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] CuatroPorMil #{r.id} (registro {r.registro_id}) revertido + soft-deleted"
                ))
            except Exception as e:
                errores += 1
                self.stdout.write(self.style.ERROR(f"  [ERR] CuatroPorMil #{r.id}: {e}"))

        self.stdout.write(self.style.NOTICE(
            f"\nResumen: utilidades={utilidades_ok}  espejos={espejos_ok}  errores={errores}"
        ))
