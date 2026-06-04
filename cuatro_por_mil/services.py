"""Servicio contable del modulo Cuatro por mil.

Cada registro de `CuatroPorMil` activo (no eliminado y con valor > 0) materializa
un asiento de partida doble:
  - Debito  -> sub-cuenta configurada en CuatroPorMilConfig.sub_cuenta_debito
  - Credito -> sub-cuenta de la tarjeta asociada al registro

`sincronizar_asiento_4xmil` es idempotente: revierte el asiento previo y postea
uno nuevo segun el estado actual del registro. Si falta configuracion o la tarjeta
no tiene sub-cuenta valida, NO se postea (el registro queda igual, sin asiento) y
se deja constancia en el log.
"""

import logging
from decimal import Decimal

from movimiento_contable.services import registrar_asiento, revertir_asiento

logger = logging.getLogger(__name__)

MODULO_ORIGEN = 'cuatro_por_mil'


def _descripcion_asiento(registro):
    return f"4x1000 {registro.modulo}#{registro.registro_id}"


def sincronizar_asiento_4xmil(registro, usuario=None):
    """Mantiene el asiento contable del 4x1000 sincronizado con `registro`.

    Revierte siempre el asiento previo (idempotente) y, si el registro debe tener
    asiento (activo + valor > 0 + config y tarjeta validas), postea uno nuevo y
    guarda su asiento_id. Devuelve el asiento_id resultante (o None).
    """
    # Import diferido para evitar ciclos al cargar la app.
    from .models import CuatroPorMil, CuatroPorMilConfig
    from django.utils import timezone

    if registro.pk is None:
        return None

    # 1) Revertir el asiento previo (si lo hay). Idempotente.
    if registro.asiento_id:
        revertir_asiento(registro.asiento_id)
        CuatroPorMil.objects.filter(pk=registro.pk).update(asiento_id=None)
        registro.asiento_id = None

    # 2) ¿Debe existir asiento? Solo si el registro esta activo y con valor > 0.
    valor = Decimal(registro.valor or 0)
    if registro.is_deleted or valor <= 0:
        return None

    # 3) Resolver las dos patas del asiento.
    cfg = CuatroPorMilConfig.load()
    debito_sc = cfg.sub_cuenta_debito
    credito_sc = registro.tarjeta.sub_cuenta if registro.tarjeta_id else None

    if debito_sc is None or debito_sc.is_deleted:
        logger.warning(
            "Cuatro por mil #%s sin sub-cuenta de debito configurada (o eliminada); "
            "no se registra asiento contable.", registro.pk
        )
        return None
    if credito_sc is None or credito_sc.is_deleted:
        logger.warning(
            "Cuatro por mil #%s: la tarjeta no tiene sub-cuenta contable valida; "
            "no se registra asiento contable.", registro.pk
        )
        return None
    if debito_sc.pk == credito_sc.pk:
        logger.warning(
            "Cuatro por mil #%s: la sub-cuenta de debito coincide con la de la tarjeta; "
            "no se registra asiento contable.", registro.pk
        )
        return None

    # 4) Postear el asiento.
    fecha = registro.fecha or registro.created_at or timezone.now()
    asiento_id = registrar_asiento(
        fecha=fecha,
        debito_sub_cuenta=debito_sc,
        credito_sub_cuenta=credito_sc,
        valor=valor,
        modulo_origen=MODULO_ORIGEN,
        origen_id=registro.pk,
        descripcion=_descripcion_asiento(registro),
        usuario=usuario or registro.usuario,
    )
    CuatroPorMil.objects.filter(pk=registro.pk).update(asiento_id=asiento_id)
    registro.asiento_id = asiento_id
    return asiento_id
