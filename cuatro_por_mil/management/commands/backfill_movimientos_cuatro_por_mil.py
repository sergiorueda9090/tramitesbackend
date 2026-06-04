"""Backfill de los asientos contables del modulo Cuatro por mil.

Recorre los registros de `CuatroPorMil` activos (no eliminados, valor > 0) y postea
su asiento de partida doble usando `cuatro_por_mil.services.sincronizar_asiento_4xmil`:
    Debito  -> CuatroPorMilConfig.sub_cuenta_debito (sub-cuenta por defecto)
    Credito -> sub-cuenta de la tarjeta del registro

Es idempotente: `sincronizar_asiento_4xmil` revierte el asiento previo (si lo hay)
antes de postear, asi que correrlo varias veces no duplica movimientos.

Por defecto solo procesa registros SIN asiento (asiento_id IS NULL). Con `--resync`
re-postea TODOS (revirtiendo y volviendo a postear), util si cambio la config.

Uso:
    python manage.py backfill_movimientos_cuatro_por_mil
    python manage.py backfill_movimientos_cuatro_por_mil --modulo gastos
    python manage.py backfill_movimientos_cuatro_por_mil --resync
    python manage.py backfill_movimientos_cuatro_por_mil --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from cuatro_por_mil.models import CuatroPorMil, CuatroPorMilConfig, ModuloOrigen
from cuatro_por_mil.services import sincronizar_asiento_4xmil


class Command(BaseCommand):
    help = ('Postea los asientos contables de los registros 4x1000 existentes '
            '(Debito -> sub-cuenta configurada / Credito -> sub-cuenta de la tarjeta).')

    def add_arguments(self, parser):
        parser.add_argument(
            '--modulo',
            type=str,
            default=None,
            help='Solo procesar registros de este modulo origen (e.g. gastos, devoluciones).',
        )
        parser.add_argument(
            '--resync',
            action='store_true',
            help='Re-postear TODOS los registros activos (revierte y vuelve a postear), '
                 'no solo los que no tienen asiento.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo reportar que se haria, sin escribir nada.',
        )

    def handle(self, *args, **options):
        target_modulo = options.get('modulo')
        resync        = options.get('resync')
        dry_run       = options.get('dry_run')

        if target_modulo and target_modulo not in {c.value for c in ModuloOrigen}:
            self.stderr.write(self.style.ERROR(f"Modulo desconocido: {target_modulo}"))
            self.stderr.write(f"Disponibles: {', '.join(c.value for c in ModuloOrigen)}")
            return

        # Verificar la sub-cuenta de debito configurada.
        cfg = CuatroPorMilConfig.load()
        debito_sc = cfg.sub_cuenta_debito
        if debito_sc is None or debito_sc.is_deleted:
            self.stderr.write(self.style.ERROR(
                "No hay una sub-cuenta de debito configurada (o esta eliminada). "
                "Configurala en la pantalla de Cuatro por mil antes de correr el backfill."
            ))
            return
        self.stdout.write(self.style.HTTP_INFO(
            f"Sub-cuenta de debito configurada: {debito_sc.codigo} — {debito_sc.nombre_sub_cuenta}"
        ))

        # Registros candidatos: activos y con valor > 0.
        qs = (CuatroPorMil.objects
              .select_related('tarjeta__sub_cuenta', 'usuario')
              .filter(deleted_at__isnull=True, valor__gt=0))
        if target_modulo:
            qs = qs.filter(modulo=target_modulo)
        if not resync:
            qs = qs.filter(asiento_id__isnull=True)

        total = qs.count()
        self.stdout.write(self.style.HTTP_INFO(
            f"{total} registro(s) a procesar"
            f"{' (todos, --resync)' if resync else ' sin asiento'}"
            f"{f' del modulo {target_modulo}' if target_modulo else ''}."
        ))

        posteados            = 0
        sin_subcuenta_tarjeta = 0
        misma_subcuenta       = 0
        errores               = 0

        for registro in qs.iterator():
            credito_sc = registro.tarjeta.sub_cuenta if registro.tarjeta_id else None

            # Clasificar por que no se podria postear (para un reporte claro).
            if credito_sc is None or credito_sc.is_deleted:
                sin_subcuenta_tarjeta += 1
                self.stdout.write(self.style.WARNING(
                    f"  - #{registro.id} [{registro.modulo}#{registro.registro_id}]: "
                    f"la tarjeta no tiene sub-cuenta valida → sin asiento."
                ))
                continue
            if credito_sc.pk == debito_sc.pk:
                misma_subcuenta += 1
                self.stdout.write(self.style.WARNING(
                    f"  - #{registro.id} [{registro.modulo}#{registro.registro_id}]: "
                    f"la sub-cuenta de la tarjeta coincide con la de debito → sin asiento."
                ))
                continue

            if dry_run:
                posteados += 1
                continue

            try:
                with transaction.atomic():
                    asiento_id = sincronizar_asiento_4xmil(registro)
                if asiento_id:
                    posteados += 1
                else:
                    # Caso defensivo: el servicio decidio no postear por alguna razon.
                    errores += 1
                    self.stdout.write(self.style.WARNING(
                        f"  - #{registro.id}: no se posteo el asiento (revisa la config / sub-cuentas)."
                    ))
            except Exception as e:  # noqa: BLE001
                errores += 1
                self.stderr.write(self.style.ERROR(
                    f"  - #{registro.id} [{registro.modulo}#{registro.registro_id}]: error → {e}"
                ))

        prefix = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Resumen: {posteados} asiento(s) "
            f"{'a postear' if dry_run else 'posteados'}, "
            f"{sin_subcuenta_tarjeta} sin sub-cuenta de tarjeta, "
            f"{misma_subcuenta} con sub-cuenta repetida, "
            f"{errores} error(es)."
        ))
