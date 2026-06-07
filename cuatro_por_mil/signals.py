"""Sincronización del ledger CuatroPorMil con los modelos productores.

Cada vez que un modelo financiero (RecepcionPago, Devolucion, GastoRelacion,
CargoNoRegistrado, UtilidadOcasional, TramiteFinalizado) se guarda, se inserta
o actualiza un registro espejo en `cuatro_por_mil`. La clave natural es
`(modulo, registro_id)`.

Reglas:
- valor 4x1000 > 0 y padre activo  → upsert (restaura si estaba soft-deleted)
- valor 4x1000 = 0 (tarjeta exenta) → soft-delete del espejo si existía
- padre soft-deleted                → soft-delete del espejo
- padre hard-deleted                → hard-delete del espejo
"""

from decimal import Decimal

from django.apps import apps
from django.db.models.signals import post_save, post_delete


# ---------------------------------------------------------------------------
# Configuración por productor
# ---------------------------------------------------------------------------

def _base_valor_default(instance):
    """Para productores cuyo valor base es el campo `valor` directamente."""
    return getattr(instance, 'valor', Decimal('0')) or Decimal('0')


def _base_valor_finalizado(instance):
    """TramiteFinalizado: base = precio_lay + comision."""
    pl = getattr(instance, 'precio_lay', None) or Decimal('0')
    co = getattr(instance, 'comision', None) or Decimal('0')
    return Decimal(pl) + Decimal(co)


PRODUCERS = [
    {
        'app': 'recepcion_pago',
        'model': 'RecepcionPago',
        'modulo': 'recepcion_pago',
        'valor_field': 'cuatro_por_mil',
        'fecha_attr': 'fecha',
        'usuario_attr': 'usuario',
        'tarjeta_attr': 'tarjeta',
        'base_callable': _base_valor_default,
    },
    {
        'app': 'devoluciones',
        'model': 'Devolucion',
        'modulo': 'devoluciones',
        'valor_field': 'cuatro_por_mil',
        'fecha_attr': 'fecha',
        'usuario_attr': 'usuario',
        'tarjeta_attr': 'tarjeta',
        'base_callable': _base_valor_default,
    },
    {
        'app': 'gastos',
        'model': 'GastoRelacion',
        'modulo': 'gastos',
        'valor_field': 'cuatro_por_mil',
        'fecha_attr': 'fecha',
        'usuario_attr': 'usuario',
        'tarjeta_attr': 'tarjeta',
        'base_callable': _base_valor_default,
    },
    {
        'app': 'cargos_no_registrados',
        'model': 'CargoNoRegistrado',
        'modulo': 'cargos_no_registrados',
        'valor_field': 'cuatro_por_mil',
        'fecha_attr': 'fecha',
        'usuario_attr': 'usuario',
        'tarjeta_attr': 'tarjeta',
        'base_callable': _base_valor_default,
    },
    # NOTA: utilidad_ocasional NO esta aqui a proposito. La utilidad ocasional
    # no genera 4x1000 (ni ganancia ni perdida), por lo que no produce espejo en
    # el ledger CuatroPorMil. Los registros historicos se limpian con el comando
    # `limpiar_4xmil_utilidad_ocasional`.
    {
        'app': 'finalizados_tramites',
        'model': 'TramiteFinalizado',
        'modulo': 'finalizados_tramites',
        'valor_field': 'cuatro_por_mil_valor',
        'fecha_attr': 'pago_confirmado_at',
        'usuario_attr': 'usuario',
        'tarjeta_attr': 'tarjeta',
        'base_callable': _base_valor_finalizado,
    },
]


# ---------------------------------------------------------------------------
# Núcleo de sincronización
# ---------------------------------------------------------------------------

def sync_ledger(producer, instance):
    """Crea/actualiza/soft-deletea el espejo en cuatro_por_mil para `instance`."""
    from cuatro_por_mil.models import CuatroPorMil  # import diferido

    modulo = producer['modulo']
    registro_id = instance.pk
    if registro_id is None:
        return

    valor = getattr(instance, producer['valor_field'], None) or Decimal('0')
    valor = Decimal(valor)

    is_parent_deleted = bool(getattr(instance, 'deleted_at', None))

    # Caso 1: padre soft-deleted o valor 0 → asegurar que el espejo quede soft-deleted
    if is_parent_deleted or valor <= Decimal('0'):
        try:
            registro = CuatroPorMil.objects.get(modulo=modulo, registro_id=registro_id)
        except CuatroPorMil.DoesNotExist:
            return
        if registro.deleted_at is None:
            registro.soft_delete()
        # Revertir el asiento contable del 4x1000 (registro inactivo).
        from cuatro_por_mil.services import sincronizar_asiento_4xmil
        sincronizar_asiento_4xmil(registro)
        return

    # Caso 2: upsert
    tarjeta     = getattr(instance, producer['tarjeta_attr'], None)
    fecha       = getattr(instance, producer['fecha_attr'], None)
    usuario     = getattr(instance, producer['usuario_attr'], None)
    observacion = getattr(instance, 'observacion', None)
    valor_base  = producer['base_callable'](instance)

    registro, _ = CuatroPorMil.objects.update_or_create(
        modulo=modulo,
        registro_id=registro_id,
        defaults={
            'valor': valor,
            'valor_base': Decimal(valor_base or 0),
            'tarjeta': tarjeta,
            'fecha': fecha,
            'usuario': usuario,
            'observacion': observacion,
            'deleted_at': None,  # restaura si estaba soft-deleted
        },
    )
    # Postear/actualizar el asiento contable del 4x1000:
    # Debito -> sub-cuenta configurada / Credito -> sub-cuenta de la tarjeta.
    from cuatro_por_mil.services import sincronizar_asiento_4xmil
    sincronizar_asiento_4xmil(registro, usuario=usuario)


def hard_delete_ledger(producer, instance):
    """Elimina permanentemente el espejo cuando el padre se hard-deletea."""
    from cuatro_por_mil.models import CuatroPorMil  # import diferido
    from movimiento_contable.services import revertir_asiento
    if instance.pk is None:
        return
    registros = CuatroPorMil.objects.filter(
        modulo=producer['modulo'],
        registro_id=instance.pk,
    )
    # Revertir el asiento contable de cada registro antes de borrarlo.
    for registro in registros:
        if registro.asiento_id:
            revertir_asiento(registro.asiento_id)
    registros.delete()


# ---------------------------------------------------------------------------
# Wiring de signals
# ---------------------------------------------------------------------------

def _make_post_save_handler(producer):
    def handler(sender, instance, **kwargs):
        sync_ledger(producer, instance)
    return handler


def _make_post_delete_handler(producer):
    def handler(sender, instance, **kwargs):
        hard_delete_ledger(producer, instance)
    return handler


def connect_signals():
    """Conecta post_save / post_delete para todos los productores.

    Llamado desde `CuatroPorMilConfig.ready()`.
    """
    for producer in PRODUCERS:
        try:
            model = apps.get_model(producer['app'], producer['model'])
        except LookupError:
            # La app productora aún no está instalada / registrada
            continue

        dispatch_uid_save   = f"cuatro_por_mil.sync.save.{producer['modulo']}"
        dispatch_uid_delete = f"cuatro_por_mil.sync.delete.{producer['modulo']}"

        post_save.connect(
            _make_post_save_handler(producer),
            sender=model,
            dispatch_uid=dispatch_uid_save,
            weak=False,
        )
        post_delete.connect(
            _make_post_delete_handler(producer),
            sender=model,
            dispatch_uid=dispatch_uid_delete,
            weak=False,
        )
