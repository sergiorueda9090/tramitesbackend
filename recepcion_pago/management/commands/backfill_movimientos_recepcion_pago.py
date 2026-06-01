"""Backfill: registra en el libro mayor las recepciones de pago que existian
antes de la integracion con MovimientoContable.

Procesa solo recepciones con `asiento_id IS NULL` y `deleted_at IS NULL`.

Uso:
    python manage.py backfill_movimientos_recepcion_pago --dry-run
    python manage.py backfill_movimientos_recepcion_pago
"""
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction

from recepcion_pago.models import RecepcionPago
from movimiento_contable.services import registrar_asiento


MODULO_ORIGEN = 'recepcion_pago'


def _descripcion(recepcion):
    return (
        f"Recepcion de pago #{recepcion.id} | "
        f"Cliente: {recepcion.cliente.nombre} | "
        f"Tarjeta: {recepcion.tarjeta.numero}"
    )


class Command(BaseCommand):
    help = 'Registra asientos contables para recepciones de pago existentes sin asiento.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='No escribe nada en la base de datos; solo reporta.')
        parser.add_argument('--limit', type=int, default=None,
                            help='Limita el numero de recepciones a procesar.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        qs = (
            RecepcionPago.objects
            .select_related('cliente__sub_cuenta', 'sub_cuenta', 'tarjeta', 'usuario')
            .filter(asiento_id__isnull=True, deleted_at__isnull=True)
            .order_by('id')
        )
        if limit:
            qs = qs[:limit]

        total = qs.count() if not limit else min(limit, RecepcionPago.objects.filter(
            asiento_id__isnull=True, deleted_at__isnull=True).count())

        self.stdout.write(self.style.NOTICE(
            f"Recepciones de pago a procesar: {total} (dry_run={dry_run})"
        ))

        ok = saltadas = errores = 0
        for r in qs:
            problema = self._validar(r)
            if problema:
                saltadas += 1
                self.stdout.write(self.style.WARNING(
                    f"  [SKIP] Recepcion #{r.id}: {problema}"
                ))
                continue

            if dry_run:
                ok += 1
                self.stdout.write(
                    f"  [DRY] Recepcion #{r.id} -> total={r.total} "
                    f"D:{r.sub_cuenta.codigo} C:{r.cliente.sub_cuenta.codigo}"
                )
                continue

            try:
                with transaction.atomic():
                    asiento_id = registrar_asiento(
                        fecha=r.fecha,
                        debito_sub_cuenta=r.sub_cuenta,
                        credito_sub_cuenta=r.cliente.sub_cuenta,
                        valor=r.total,
                        modulo_origen=MODULO_ORIGEN,
                        origen_id=r.id,
                        descripcion=_descripcion(r),
                        usuario=r.usuario,
                    )
                    RecepcionPago.objects.filter(pk=r.pk).update(asiento_id=asiento_id)
                ok += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] Recepcion #{r.id} -> asiento {asiento_id}"
                ))
            except (ValidationError, Exception) as e:
                errores += 1
                self.stdout.write(self.style.ERROR(
                    f"  [ERR] Recepcion #{r.id}: {e}"
                ))

        self.stdout.write(self.style.NOTICE(
            f"\nResumen: OK={ok}  SKIP={saltadas}  ERR={errores}  TOTAL={total}"
        ))

    def _validar(self, r):
        if r.cliente_id is None:
            return 'no tiene cliente'
        if r.cliente.deleted_at is not None:
            return f'cliente #{r.cliente_id} eliminado'
        if r.cliente.sub_cuenta_id is None:
            return f'cliente #{r.cliente_id} no tiene sub-cuenta'
        if r.cliente.sub_cuenta.is_deleted:
            return f'sub-cuenta del cliente ({r.cliente.sub_cuenta.codigo}) esta eliminada'
        if r.sub_cuenta_id is None:
            return 'no tiene sub-cuenta de debito'
        if r.sub_cuenta.is_deleted:
            return f'sub-cuenta de debito ({r.sub_cuenta.codigo}) esta eliminada'
        if r.sub_cuenta_id == r.cliente.sub_cuenta_id:
            return 'sub-cuenta de debito = sub-cuenta del cliente (asiento invalido)'
        if r.total is None or r.total <= 0:
            return f'total invalido ({r.total})'
        if r.fecha is None:
            return 'sin fecha contable'
        return None
