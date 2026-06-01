"""Backfill: registra en el libro mayor los cargos no registrados existentes
sin asiento. Procesa solo `asiento_id IS NULL` y `deleted_at IS NULL`.

Asiento: D=cliente.sub_cuenta, C=cargo.sub_cuenta, valor=total.

Uso:
    python manage.py backfill_movimientos_cargos_no_registrados --dry-run
    python manage.py backfill_movimientos_cargos_no_registrados
"""
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction

from cargos_no_registrados.models import CargoNoRegistrado
from movimiento_contable.services import registrar_asiento


MODULO_ORIGEN = 'cargos_no_registrados'


def _descripcion(c):
    return (f"Cargo no registrado #{c.id} | "
            f"Cliente: {c.cliente.nombre} | Tarjeta: {c.tarjeta.numero}")


class Command(BaseCommand):
    help = 'Registra asientos contables para cargos no registrados existentes sin asiento.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        qs = (CargoNoRegistrado.objects
              .select_related('cliente__sub_cuenta', 'sub_cuenta', 'tarjeta', 'usuario')
              .filter(asiento_id__isnull=True, deleted_at__isnull=True)
              .order_by('id'))
        if limit:
            qs = qs[:limit]

        total = qs.count() if not limit else min(limit, CargoNoRegistrado.objects.filter(
            asiento_id__isnull=True, deleted_at__isnull=True).count())

        self.stdout.write(self.style.NOTICE(
            f"Cargos no registrados a procesar: {total} (dry_run={dry_run})"
        ))

        ok = saltadas = errores = 0
        for c in qs:
            problema = self._validar(c)
            if problema:
                saltadas += 1
                self.stdout.write(self.style.WARNING(f"  [SKIP] Cargo #{c.id}: {problema}"))
                continue

            if dry_run:
                ok += 1
                self.stdout.write(
                    f"  [DRY] Cargo #{c.id} -> total={c.total} "
                    f"D:{c.cliente.sub_cuenta.codigo} C:{c.sub_cuenta.codigo}"
                )
                continue

            try:
                with transaction.atomic():
                    asiento_id = registrar_asiento(
                        fecha=c.fecha,
                        debito_sub_cuenta=c.cliente.sub_cuenta,
                        credito_sub_cuenta=c.sub_cuenta,
                        valor=c.total,
                        modulo_origen=MODULO_ORIGEN,
                        origen_id=c.id,
                        descripcion=_descripcion(c),
                        usuario=c.usuario,
                    )
                    CargoNoRegistrado.objects.filter(pk=c.pk).update(asiento_id=asiento_id)
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"  [OK] Cargo #{c.id} -> {asiento_id}"))
            except (ValidationError, Exception) as e:
                errores += 1
                self.stdout.write(self.style.ERROR(f"  [ERR] Cargo #{c.id}: {e}"))

        self.stdout.write(self.style.NOTICE(
            f"\nResumen: OK={ok}  SKIP={saltadas}  ERR={errores}  TOTAL={total}"
        ))

    def _validar(self, c):
        if c.cliente_id is None:
            return 'no tiene cliente'
        if c.cliente.deleted_at is not None:
            return f'cliente #{c.cliente_id} eliminado'
        if c.cliente.sub_cuenta_id is None:
            return f'cliente #{c.cliente_id} no tiene sub-cuenta'
        if c.cliente.sub_cuenta.is_deleted:
            return f'sub-cuenta del cliente ({c.cliente.sub_cuenta.codigo}) esta eliminada'
        if c.sub_cuenta_id is None:
            return 'no tiene sub-cuenta de credito'
        if c.sub_cuenta.is_deleted:
            return f'sub-cuenta de credito ({c.sub_cuenta.codigo}) esta eliminada'
        if c.sub_cuenta_id == c.cliente.sub_cuenta_id:
            return 'sub-cuenta del cargo = sub-cuenta del cliente (asiento invalido)'
        if c.total is None or c.total <= 0:
            return f'total invalido ({c.total})'
        if c.fecha is None:
            return 'sin fecha contable'
        return None
