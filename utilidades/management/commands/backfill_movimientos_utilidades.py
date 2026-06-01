"""Backfill: registra en el libro mayor las utilidades existentes que aun
no tienen asiento contable. Util cuando UTILIDADES_SUB_CUENTA_CODIGO fue
configurada DESPUES de que se crearon utilidades.

Reglas:
  - Procesa solo `asiento_id IS NULL` y `deleted_at IS NULL`.
  - D = tramite_finalizado.tarjeta.sub_cuenta (banco).
  - C = utilidad.sub_cuenta si esta poblada; si no, intenta resolverla via
        UTILIDADES_SUB_CUENTA_CODIGO y la guarda en la fila.
  - Valor = comision_proveedor.

Uso:
    python manage.py backfill_movimientos_utilidades --dry-run
    python manage.py backfill_movimientos_utilidades
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction

from movimiento_contable.services import registrar_asiento
from sub_cuentas.models import SubCuenta
from utilidades.models import Utilidad


MODULO_ORIGEN = 'utilidades'


def _sub_cuenta_ingreso():
    codigo = (getattr(settings, 'UTILIDADES_SUB_CUENTA_CODIGO', '') or '').strip()
    if not codigo:
        return None
    return SubCuenta.objects.filter(codigo=codigo, deleted_at__isnull=True).first()


def _descripcion(u):
    return f"Utilidad #{u.id} | Tramite finalizado #{u.tramite_finalizado_id} | Placa: {u.placa or 'sin placa'}"


class Command(BaseCommand):
    help = 'Registra asientos contables para utilidades existentes sin asiento.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        ingreso_global = _sub_cuenta_ingreso()
        if ingreso_global is None:
            self.stdout.write(self.style.WARNING(
                "UTILIDADES_SUB_CUENTA_CODIGO no esta configurada; solo se procesaran "
                "utilidades que ya tengan sub_cuenta poblada."
            ))

        qs = (Utilidad.objects
              .select_related('tramite_finalizado__tarjeta__sub_cuenta',
                              'tramite_finalizado__usuario',
                              'tramite_finalizado__usuario_que_confirma',
                              'sub_cuenta')
              .filter(asiento_id__isnull=True, deleted_at__isnull=True)
              .order_by('id'))
        if limit:
            qs = qs[:limit]

        total = qs.count() if not limit else min(limit, Utilidad.objects.filter(
            asiento_id__isnull=True, deleted_at__isnull=True).count())

        self.stdout.write(self.style.NOTICE(
            f"Utilidades a procesar: {total} (dry_run={dry_run})"
        ))

        ok = saltadas = errores = 0
        for u in qs:
            problema, d_sc, c_sc, monto, asigno_sc = self._resolver(u, ingreso_global)
            if problema:
                saltadas += 1
                self.stdout.write(self.style.WARNING(f"  [SKIP] Utilidad #{u.id}: {problema}"))
                continue

            if dry_run:
                ok += 1
                self.stdout.write(
                    f"  [DRY] Utilidad #{u.id} -> monto={monto} "
                    f"D:{d_sc.codigo} C:{c_sc.codigo}"
                    + (" (sub_cuenta sera asignada)" if asigno_sc else "")
                )
                continue

            try:
                tramite = u.tramite_finalizado
                with transaction.atomic():
                    if asigno_sc:
                        u.sub_cuenta = c_sc
                        u.save(update_fields=['sub_cuenta'])
                    asiento_id = registrar_asiento(
                        fecha=tramite.pago_confirmado_at,
                        debito_sub_cuenta=d_sc,
                        credito_sub_cuenta=c_sc,
                        valor=monto,
                        modulo_origen=MODULO_ORIGEN,
                        origen_id=u.id,
                        descripcion=_descripcion(u),
                        usuario=tramite.usuario_que_confirma or tramite.usuario,
                    )
                    Utilidad.objects.filter(pk=u.pk).update(asiento_id=asiento_id)
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"  [OK] Utilidad #{u.id} -> {asiento_id}"))
            except (ValidationError, Exception) as e:
                errores += 1
                self.stdout.write(self.style.ERROR(f"  [ERR] Utilidad #{u.id}: {e}"))

        self.stdout.write(self.style.NOTICE(
            f"\nResumen: OK={ok}  SKIP={saltadas}  ERR={errores}  TOTAL={total}"
        ))

    def _resolver(self, u, ingreso_global):
        """Resuelve (problema, debito_sc, credito_sc, monto, asigno_sub_cuenta)."""
        tramite = u.tramite_finalizado
        if tramite is None:
            return ('no tiene tramite finalizado', None, None, None, False)
        tarjeta = tramite.tarjeta
        if tarjeta is None or tarjeta.sub_cuenta_id is None:
            return ('tramite sin tarjeta o tarjeta sin sub-cuenta', None, None, None, False)
        if tarjeta.sub_cuenta.is_deleted:
            return (f'sub-cuenta de la tarjeta ({tarjeta.sub_cuenta.codigo}) esta eliminada', None, None, None, False)
        if u.comision_proveedor is None or u.comision_proveedor <= 0:
            return (f'comision invalida ({u.comision_proveedor})', None, None, None, False)

        # Resolver sub_cuenta de credito (ingreso)
        if u.sub_cuenta_id is not None and not u.sub_cuenta.is_deleted:
            credito_sc = u.sub_cuenta
            asigno = False
        elif ingreso_global is not None:
            credito_sc = ingreso_global
            asigno = True
        else:
            return ('utilidad sin sub_cuenta y UTILIDADES_SUB_CUENTA_CODIGO no configurado',
                    None, None, None, False)

        if credito_sc.pk == tarjeta.sub_cuenta_id:
            return ('sub-cuenta de utilidad = sub-cuenta de tarjeta (asiento invalido)',
                    None, None, None, False)

        return (None, tarjeta.sub_cuenta, credito_sc, u.comision_proveedor, asigno)
