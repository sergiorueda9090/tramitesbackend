"""Backfill: registra en el libro mayor las devoluciones que existian antes
de la integracion con MovimientoContable.

Procesa solo devoluciones con `asiento_id IS NULL` y `deleted_at IS NULL`
(no toca devoluciones eliminadas ni las que ya tienen asiento).

Uso:
    python manage.py backfill_movimientos_devoluciones --dry-run
    python manage.py backfill_movimientos_devoluciones
"""
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction

from devoluciones.models import Devolucion
from movimiento_contable.services import registrar_asiento


MODULO_ORIGEN = 'devoluciones'


def _descripcion(devolucion):
    return (
        f"Devolucion #{devolucion.id} | "
        f"Cliente: {devolucion.cliente.nombre} | "
        f"Tarjeta: {devolucion.tarjeta.numero}"
    )


class Command(BaseCommand):
    help = 'Registra asientos contables para devoluciones existentes que aun no tienen asiento.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='No escribe nada en la base de datos; solo reporta lo que haria.'
        )
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Limita el numero de devoluciones a procesar (util para pruebas).'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        qs = (
            Devolucion.objects
            .select_related('cliente__sub_cuenta', 'sub_cuenta', 'tarjeta', 'usuario')
            .filter(asiento_id__isnull=True, deleted_at__isnull=True)
            .order_by('id')
        )
        if limit:
            qs = qs[:limit]

        total = qs.count() if not limit else min(limit, Devolucion.objects.filter(
            asiento_id__isnull=True, deleted_at__isnull=True).count())

        self.stdout.write(self.style.NOTICE(
            f"Devoluciones a procesar: {total} (dry_run={dry_run})"
        ))

        ok = 0
        saltadas = 0
        errores = 0
        for d in qs:
            problema = self._validar(d)
            if problema:
                saltadas += 1
                self.stdout.write(self.style.WARNING(
                    f"  [SKIP] Devolucion #{d.id}: {problema}"
                ))
                continue

            if dry_run:
                ok += 1
                self.stdout.write(
                    f"  [DRY] Devolucion #{d.id} -> total={d.total} "
                    f"D:{d.cliente.sub_cuenta.codigo} C:{d.sub_cuenta.codigo}"
                )
                continue

            try:
                with transaction.atomic():
                    asiento_id = registrar_asiento(
                        fecha=d.fecha,
                        debito_sub_cuenta=d.cliente.sub_cuenta,
                        credito_sub_cuenta=d.sub_cuenta,
                        valor=d.total,
                        modulo_origen=MODULO_ORIGEN,
                        origen_id=d.id,
                        descripcion=_descripcion(d),
                        usuario=d.usuario,
                    )
                    Devolucion.objects.filter(pk=d.pk).update(asiento_id=asiento_id)
                ok += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] Devolucion #{d.id} -> asiento {asiento_id}"
                ))
            except (ValidationError, Exception) as e:
                errores += 1
                self.stdout.write(self.style.ERROR(
                    f"  [ERR] Devolucion #{d.id}: {e}"
                ))

        self.stdout.write(self.style.NOTICE(
            f"\nResumen: OK={ok}  SKIP={saltadas}  ERR={errores}  TOTAL={total}"
        ))

    def _validar(self, d):
        """Devuelve un string con el problema, o None si la devolucion es procesable."""
        if d.cliente_id is None:
            return 'no tiene cliente'
        if d.cliente.deleted_at is not None:
            return f'cliente #{d.cliente_id} eliminado'
        if d.cliente.sub_cuenta_id is None:
            return f'cliente #{d.cliente_id} no tiene sub-cuenta'
        if d.cliente.sub_cuenta.is_deleted:
            return f'sub-cuenta del cliente ({d.cliente.sub_cuenta.codigo}) esta eliminada'
        if d.sub_cuenta_id is None:
            return 'no tiene sub-cuenta de debito'
        if d.sub_cuenta.is_deleted:
            return f'sub-cuenta de debito ({d.sub_cuenta.codigo}) esta eliminada'
        if d.sub_cuenta_id == d.cliente.sub_cuenta_id:
            return 'sub-cuenta de debito = sub-cuenta del cliente (asiento invalido)'
        if d.total is None or d.total <= 0:
            return f'total invalido ({d.total})'
        if d.fecha is None:
            return 'sin fecha contable'
        return None
