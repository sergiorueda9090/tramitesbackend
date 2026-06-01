"""Servicios del libro mayor.

Punto de entrada unico para que los modulos de origen
(devoluciones, recepcion_pago, gastos, ...) registren y reviertan asientos
contables. NO escribir en `MovimientoContable` ni recalcular `SubCuenta`
desde otros lugares: pasar siempre por aqui para garantizar partida doble
+ acumulado consistente.
"""
import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from movimiento_contable.models import MovimientoContable, TipoMovimiento
from plan_de_cuentas.models import AcumuladoTipo
from sub_cuentas.models import SubCuenta


def _to_decimal(valor):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(f'Valor numerico invalido para asiento contable: {valor!r}')


def _recalcular_acumulado(sub_cuenta_id: int) -> None:
    """Recalcula `debito`, `credito` y `acumulado` de una SubCuenta a partir
    de la tabla `MovimientoContable` (excluyendo soft-deleted).

    Debe ejecutarse dentro de transaction.atomic; toma un lock de fila
    sobre la SubCuenta para evitar races con asientos concurrentes.
    """
    locked = SubCuenta.objects.select_for_update().select_related('cuenta').get(pk=sub_cuenta_id)

    movimientos = MovimientoContable.objects.filter(
        sub_cuenta_id=locked.pk, deleted_at__isnull=True
    )
    total_debito  = movimientos.filter(tipo_movimiento=TipoMovimiento.DEBITO ).aggregate(s=Sum('valor'))['s'] or Decimal('0')
    total_credito = movimientos.filter(tipo_movimiento=TipoMovimiento.CREDITO).aggregate(s=Sum('valor'))['s'] or Decimal('0')

    if locked.cuenta.acumulado == AcumuladoTipo.DEBITO_CREDITO:
        acumulado = total_debito - total_credito
    else:  # CREDITO_DEBITO
        acumulado = total_credito - total_debito

    SubCuenta.objects.filter(pk=locked.pk).update(
        debito=total_debito, credito=total_credito, acumulado=acumulado
    )


@transaction.atomic
def registrar_asiento(*, fecha, debito_sub_cuenta: SubCuenta, credito_sub_cuenta: SubCuenta,
                      valor, modulo_origen: str, origen_id: int,
                      descripcion: str = '', usuario=None) -> uuid.UUID:
    """Registra un asiento de partida doble: 1 debito + 1 credito vinculados
    por `asiento_id`. Devuelve el UUID del asiento (guardarlo en el modelo
    de origen para poder revertir despues).
    """
    valor = _to_decimal(valor)
    if valor <= 0:
        raise ValidationError('El valor del asiento debe ser positivo.')
    if debito_sub_cuenta.pk == credito_sub_cuenta.pk:
        raise ValidationError('Las sub-cuentas de debito y credito deben ser distintas.')
    if debito_sub_cuenta.is_deleted or credito_sub_cuenta.is_deleted:
        raise ValidationError('No se puede asentar movimientos sobre sub-cuentas eliminadas.')
    if not modulo_origen or origen_id is None:
        raise ValidationError('modulo_origen y origen_id son obligatorios.')

    asiento_id = uuid.uuid4()

    MovimientoContable.objects.create(
        asiento_id=asiento_id,
        sub_cuenta=debito_sub_cuenta,
        tipo_movimiento=TipoMovimiento.DEBITO,
        valor=valor,
        fecha=fecha,
        modulo_origen=modulo_origen,
        origen_id=origen_id,
        descripcion=descripcion,
        usuario=usuario,
    )
    MovimientoContable.objects.create(
        asiento_id=asiento_id,
        sub_cuenta=credito_sub_cuenta,
        tipo_movimiento=TipoMovimiento.CREDITO,
        valor=valor,
        fecha=fecha,
        modulo_origen=modulo_origen,
        origen_id=origen_id,
        descripcion=descripcion,
        usuario=usuario,
    )

    _recalcular_acumulado(debito_sub_cuenta.pk)
    _recalcular_acumulado(credito_sub_cuenta.pk)

    return asiento_id


@transaction.atomic
def revertir_asiento(asiento_id) -> None:
    """Soft-delete de las filas del asiento + recalculo de las sub-cuentas
    afectadas. Idempotente: si el asiento no existe o ya estaba revertido,
    no hace nada.
    """
    if asiento_id in (None, ''):
        return

    movimientos = list(
        MovimientoContable.objects.filter(asiento_id=asiento_id, deleted_at__isnull=True)
    )
    if not movimientos:
        return

    sub_cuentas_afectadas = {m.sub_cuenta_id for m in movimientos}
    for mov in movimientos:
        mov.soft_delete()

    for sc_id in sub_cuentas_afectadas:
        _recalcular_acumulado(sc_id)
