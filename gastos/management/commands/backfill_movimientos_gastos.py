"""Backfill: registra en el libro mayor las relaciones de gasto existentes
sin asiento. Procesa solo `asiento_id IS NULL` y `deleted_at IS NULL`.

Asiento: D=gasto_categoria.sub_cuenta, C=relacion.sub_cuenta, valor=total.

Uso:
    python manage.py backfill_movimientos_gastos --dry-run
    python manage.py backfill_movimientos_gastos
"""
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction

from gastos.models import GastoRelacion
from movimiento_contable.services import registrar_asiento


MODULO_ORIGEN = 'gastos'


def _descripcion(r):
    return (f"Gasto #{r.id} | Categoria: {r.gasto.nombre} | "
            f"Tarjeta: {r.tarjeta.numero}")


class Command(BaseCommand):
    help = 'Registra asientos contables para relaciones de gasto sin asiento.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        qs = (GastoRelacion.objects
              .select_related('gasto__sub_cuenta', 'sub_cuenta', 'tarjeta', 'usuario')
              .filter(asiento_id__isnull=True, deleted_at__isnull=True)
              .order_by('id'))
        if limit:
            qs = qs[:limit]

        total = qs.count() if not limit else min(limit, GastoRelacion.objects.filter(
            asiento_id__isnull=True, deleted_at__isnull=True).count())

        self.stdout.write(self.style.NOTICE(
            f"Relaciones de gasto a procesar: {total} (dry_run={dry_run})"
        ))

        ok = saltadas = errores = 0
        for r in qs:
            problema = self._validar(r)
            if problema:
                saltadas += 1
                self.stdout.write(self.style.WARNING(f"  [SKIP] Gasto #{r.id}: {problema}"))
                continue

            if dry_run:
                ok += 1
                self.stdout.write(
                    f"  [DRY] Gasto #{r.id} -> total={r.total} "
                    f"D:{r.gasto.sub_cuenta.codigo} C:{r.sub_cuenta.codigo}"
                )
                continue

            try:
                with transaction.atomic():
                    asiento_id = registrar_asiento(
                        fecha=r.fecha,
                        debito_sub_cuenta=r.gasto.sub_cuenta,
                        credito_sub_cuenta=r.sub_cuenta,
                        valor=r.total,
                        modulo_origen=MODULO_ORIGEN,
                        origen_id=r.id,
                        descripcion=_descripcion(r),
                        usuario=r.usuario,
                    )
                    GastoRelacion.objects.filter(pk=r.pk).update(asiento_id=asiento_id)
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"  [OK] Gasto #{r.id} -> {asiento_id}"))
            except (ValidationError, Exception) as e:
                errores += 1
                self.stdout.write(self.style.ERROR(f"  [ERR] Gasto #{r.id}: {e}"))

        self.stdout.write(self.style.NOTICE(
            f"\nResumen: OK={ok}  SKIP={saltadas}  ERR={errores}  TOTAL={total}"
        ))

    def _validar(self, r):
        if r.gasto_id is None:
            return 'no tiene categoria'
        if r.gasto.deleted_at is not None:
            return f'categoria #{r.gasto_id} eliminada'
        if r.gasto.sub_cuenta_id is None:
            return f'categoria #{r.gasto_id} no tiene sub-cuenta'
        if r.gasto.sub_cuenta.is_deleted:
            return f'sub-cuenta de la categoria ({r.gasto.sub_cuenta.codigo}) esta eliminada'
        if r.sub_cuenta_id is None:
            return 'no tiene sub-cuenta de credito'
        if r.sub_cuenta.is_deleted:
            return f'sub-cuenta de credito ({r.sub_cuenta.codigo}) esta eliminada'
        if r.sub_cuenta_id == r.gasto.sub_cuenta_id:
            return 'sub-cuenta del gasto = sub-cuenta de la categoria (asiento invalido)'
        if r.total is None or r.total <= 0:
            return f'total invalido ({r.total})'
        if r.fecha is None:
            return 'sin fecha contable'
        return None
