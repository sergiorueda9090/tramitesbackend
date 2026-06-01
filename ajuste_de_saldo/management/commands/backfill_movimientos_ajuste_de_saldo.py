"""Backfill: registra en el libro mayor los ajustes de saldo existentes
sin asiento. La direccion (D/C) se deriva del propio registro:
  - debito  > 0 → D=cliente.sub_cuenta, C=ajuste.sub_cuenta.
  - credito > 0 → D=ajuste.sub_cuenta,  C=cliente.sub_cuenta.

Uso:
    python manage.py backfill_movimientos_ajuste_de_saldo --dry-run
    python manage.py backfill_movimientos_ajuste_de_saldo
"""
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction

from ajuste_de_saldo.models import AjusteDeSaldo
from movimiento_contable.services import registrar_asiento


MODULO_ORIGEN = 'ajuste_de_saldo'


def _descripcion(a):
    return f"Ajuste de saldo #{a.id} | Cliente: {a.cliente.nombre}"


class Command(BaseCommand):
    help = 'Registra asientos contables para ajustes de saldo sin asiento.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        qs = (AjusteDeSaldo.objects
              .select_related('cliente__sub_cuenta', 'sub_cuenta', 'usuario')
              .filter(asiento_id__isnull=True, deleted_at__isnull=True)
              .order_by('id'))
        if limit:
            qs = qs[:limit]

        total = qs.count() if not limit else min(limit, AjusteDeSaldo.objects.filter(
            asiento_id__isnull=True, deleted_at__isnull=True).count())

        self.stdout.write(self.style.NOTICE(
            f"Ajustes de saldo a procesar: {total} (dry_run={dry_run})"
        ))

        ok = saltadas = errores = 0
        for a in qs:
            problema = self._validar(a)
            if problema:
                saltadas += 1
                self.stdout.write(self.style.WARNING(f"  [SKIP] Ajuste #{a.id}: {problema}"))
                continue

            if a.debito > 0:
                d_sc, c_sc, monto = a.cliente.sub_cuenta, a.sub_cuenta, a.debito
            else:
                d_sc, c_sc, monto = a.sub_cuenta, a.cliente.sub_cuenta, a.credito

            if dry_run:
                ok += 1
                self.stdout.write(
                    f"  [DRY] Ajuste #{a.id} -> monto={monto} D:{d_sc.codigo} C:{c_sc.codigo}"
                )
                continue

            try:
                with transaction.atomic():
                    asiento_id = registrar_asiento(
                        fecha=a.fecha,
                        debito_sub_cuenta=d_sc,
                        credito_sub_cuenta=c_sc,
                        valor=monto,
                        modulo_origen=MODULO_ORIGEN,
                        origen_id=a.id,
                        descripcion=_descripcion(a),
                        usuario=a.usuario,
                    )
                    AjusteDeSaldo.objects.filter(pk=a.pk).update(asiento_id=asiento_id)
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"  [OK] Ajuste #{a.id} -> {asiento_id}"))
            except (ValidationError, Exception) as e:
                errores += 1
                self.stdout.write(self.style.ERROR(f"  [ERR] Ajuste #{a.id}: {e}"))

        self.stdout.write(self.style.NOTICE(
            f"\nResumen: OK={ok}  SKIP={saltadas}  ERR={errores}  TOTAL={total}"
        ))

    def _validar(self, a):
        if a.cliente_id is None:
            return 'no tiene cliente'
        if a.cliente.deleted_at is not None:
            return f'cliente #{a.cliente_id} eliminado'
        if a.cliente.sub_cuenta_id is None:
            return f'cliente #{a.cliente_id} no tiene sub-cuenta'
        if a.cliente.sub_cuenta.is_deleted:
            return f'sub-cuenta del cliente ({a.cliente.sub_cuenta.codigo}) esta eliminada'
        if a.sub_cuenta_id is None:
            return 'no tiene sub-cuenta contraparte'
        if a.sub_cuenta.is_deleted:
            return f'sub-cuenta contraparte ({a.sub_cuenta.codigo}) esta eliminada'
        if a.sub_cuenta_id == a.cliente.sub_cuenta_id:
            return 'sub-cuenta del ajuste = sub-cuenta del cliente (asiento invalido)'
        if a.debito > 0 and a.credito > 0:
            return 'debito y credito > 0 (direccion ambigua)'
        if a.debito <= 0 and a.credito <= 0:
            return 'debito y credito = 0 (nada que asentar)'
        if a.fecha is None:
            return 'sin fecha contable'
        return None
