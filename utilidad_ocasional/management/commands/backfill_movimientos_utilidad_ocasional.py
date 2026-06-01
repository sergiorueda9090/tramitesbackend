"""Backfill: registra en el libro mayor las utilidades ocasionales existentes
sin asiento. Procesa solo `asiento_id IS NULL` y `deleted_at IS NULL`.

Asiento: D=tarjeta.sub_cuenta, C=utilidad.sub_cuenta, valor=total.

Uso:
    python manage.py backfill_movimientos_utilidad_ocasional --dry-run
    python manage.py backfill_movimientos_utilidad_ocasional
"""
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction

from utilidad_ocasional.models import UtilidadOcasional
from movimiento_contable.services import registrar_asiento


MODULO_ORIGEN = 'utilidad_ocasional'


def _descripcion(u):
    return f"Utilidad ocasional #{u.id} | Tarjeta: {u.tarjeta.numero}"


class Command(BaseCommand):
    help = 'Registra asientos contables para utilidades ocasionales sin asiento.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        qs = (UtilidadOcasional.objects
              .select_related('tarjeta__sub_cuenta', 'sub_cuenta', 'usuario')
              .filter(asiento_id__isnull=True, deleted_at__isnull=True)
              .order_by('id'))
        if limit:
            qs = qs[:limit]

        total = qs.count() if not limit else min(limit, UtilidadOcasional.objects.filter(
            asiento_id__isnull=True, deleted_at__isnull=True).count())

        self.stdout.write(self.style.NOTICE(
            f"Utilidades ocasionales a procesar: {total} (dry_run={dry_run})"
        ))

        ok = saltadas = errores = 0
        for u in qs:
            problema = self._validar(u)
            if problema:
                saltadas += 1
                self.stdout.write(self.style.WARNING(f"  [SKIP] UtilidadOcasional #{u.id}: {problema}"))
                continue

            if dry_run:
                ok += 1
                self.stdout.write(
                    f"  [DRY] UtilidadOcasional #{u.id} -> total={u.total} "
                    f"D:{u.tarjeta.sub_cuenta.codigo} C:{u.sub_cuenta.codigo}"
                )
                continue

            try:
                with transaction.atomic():
                    asiento_id = registrar_asiento(
                        fecha=u.fecha,
                        debito_sub_cuenta=u.tarjeta.sub_cuenta,
                        credito_sub_cuenta=u.sub_cuenta,
                        valor=u.total,
                        modulo_origen=MODULO_ORIGEN,
                        origen_id=u.id,
                        descripcion=_descripcion(u),
                        usuario=u.usuario,
                    )
                    UtilidadOcasional.objects.filter(pk=u.pk).update(asiento_id=asiento_id)
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"  [OK] UtilidadOcasional #{u.id} -> {asiento_id}"))
            except (ValidationError, Exception) as e:
                errores += 1
                self.stdout.write(self.style.ERROR(f"  [ERR] UtilidadOcasional #{u.id}: {e}"))

        self.stdout.write(self.style.NOTICE(
            f"\nResumen: OK={ok}  SKIP={saltadas}  ERR={errores}  TOTAL={total}"
        ))

    def _validar(self, u):
        if u.tarjeta_id is None:
            return 'no tiene tarjeta'
        if u.tarjeta.deleted_at is not None:
            return f'tarjeta #{u.tarjeta_id} eliminada'
        if u.tarjeta.sub_cuenta_id is None:
            return f'tarjeta #{u.tarjeta_id} no tiene sub-cuenta'
        if u.tarjeta.sub_cuenta.is_deleted:
            return f'sub-cuenta de la tarjeta ({u.tarjeta.sub_cuenta.codigo}) esta eliminada'
        if u.sub_cuenta_id is None:
            return 'no tiene sub-cuenta de credito (ingreso)'
        if u.sub_cuenta.is_deleted:
            return f'sub-cuenta de credito ({u.sub_cuenta.codigo}) esta eliminada'
        if u.sub_cuenta_id == u.tarjeta.sub_cuenta_id:
            return 'sub-cuenta de la utilidad = sub-cuenta de la tarjeta (asiento invalido)'
        if u.total is None or u.total <= 0:
            return f'total invalido ({u.total})'
        if u.fecha is None:
            return 'sin fecha contable'
        return None
