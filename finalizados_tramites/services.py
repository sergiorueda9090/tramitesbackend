"""
Creación de un TramiteFinalizado a partir de una PasarelaPago.

Lógica compartida por:
  - finalizados_tramites.api.views.crear_desde_pasarela (botón manual en Pasarela)
  - pasarela_de_pago.api.views.confirmar_pago_pasarela (auto al marcar "Pago exitoso")

Hace el snapshot completo + soft-delete de la pasarela en una transacción. NO
emite eventos WS ni valida permisos: eso es responsabilidad del caller.

Al crear el finalizado se postean DOS asientos contables (libro mayor), según
el diseño SOAT:
  1. Emisión SOAT  → Débito cliente / Crédito proveedor   (valor = precio_lay)
  2. Comisión SOAT → Débito cliente / Crédito 4135 ingresos (valor = comision)
El posteo es best-effort: si falta una sub-cuenta o el valor es <= 0, ese
asiento se omite y se loguea un warning (el pago se finaliza igual).
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import TramiteFinalizado

logger = logging.getLogger(__name__)

MODULO_ORIGEN = 'finalizados_tramites'


def _resolver_proveedor_sub_cuenta(entidad):
    """Sub-cuenta del proveedor (PREVISORA/MUNDIAL) cuyo nombre = entidad.
    Devuelve None para SOLIDARIA/MANUAL/'' o si el proveedor no tiene sub-cuenta."""
    if not entidad:
        return None
    from proveedores.models import Proveedor
    prov = (Proveedor.objects
            .select_related('sub_cuenta')
            .filter(nombre__iexact=entidad, deleted_at__isnull=True)
            .first())
    if not prov or prov.sub_cuenta_id is None or prov.sub_cuenta.is_deleted:
        return None
    return prov.sub_cuenta


def _resolver_ingresos_sub_cuenta():
    """Sub-cuenta de ingresos por SOAT (4135), resuelta por el código configurado
    en INGRESOS_SOAT_SUB_CUENTA_CODIGO. Devuelve None si no existe / está vacía."""
    codigo = getattr(settings, 'INGRESOS_SOAT_SUB_CUENTA_CODIGO', '') or ''
    if not codigo:
        return None
    from sub_cuentas.models import SubCuenta
    sub = SubCuenta.objects.filter(codigo=codigo, deleted_at__isnull=True).first()
    if not sub or sub.is_deleted:
        return None
    return sub


def _registrar_asientos_soat(finalizado, usuario):
    """Postea los asientos de emisión y comisión para un finalizado recién creado.
    Guarda los UUID en el finalizado. Cada asiento es independiente y best-effort:
    si falta su sub-cuenta o su valor es <= 0, se omite con warning."""
    from movimiento_contable.services import registrar_asiento
    from django.core.exceptions import ValidationError

    cliente_sub = None
    if finalizado.cliente_id and finalizado.cliente.sub_cuenta_id and not finalizado.cliente.sub_cuenta.is_deleted:
        cliente_sub = finalizado.cliente.sub_cuenta

    proveedor_sub = _resolver_proveedor_sub_cuenta(finalizado.entidad)
    ingresos_sub = _resolver_ingresos_sub_cuenta()

    precio_lay = finalizado.precio_lay or Decimal('0')
    comision = finalizado.comision or Decimal('0')

    actualizar = {}

    # Asiento 1 — Emisión SOAT: Débito cliente / Crédito proveedor.
    if cliente_sub and proveedor_sub and precio_lay > 0:
        try:
            actualizar['asiento_emision_id'] = registrar_asiento(
                fecha=finalizado.pago_confirmado_at,
                debito_sub_cuenta=cliente_sub,
                credito_sub_cuenta=proveedor_sub,
                valor=precio_lay,
                modulo_origen=MODULO_ORIGEN,
                origen_id=finalizado.id,
                descripcion=f'Emisión SOAT finalizado #{finalizado.id} - placa {finalizado.placa or "s/placa"}',
                usuario=usuario,
            )
        except ValidationError as e:
            logger.warning('No se pudo postear asiento de emisión (finalizado #%s): %s', finalizado.id, e)
    else:
        logger.warning(
            'Asiento de emisión omitido (finalizado #%s): cliente_sub=%s proveedor_sub=%s precio_lay=%s',
            finalizado.id, bool(cliente_sub), bool(proveedor_sub), precio_lay,
        )

    # Asiento 2 — Comisión SOAT: Débito cliente / Crédito ingresos (4135).
    if cliente_sub and ingresos_sub and comision > 0:
        try:
            actualizar['asiento_comision_id'] = registrar_asiento(
                fecha=finalizado.pago_confirmado_at,
                debito_sub_cuenta=cliente_sub,
                credito_sub_cuenta=ingresos_sub,
                valor=comision,
                modulo_origen=MODULO_ORIGEN,
                origen_id=finalizado.id,
                descripcion=f'Comisión SOAT finalizado #{finalizado.id} - placa {finalizado.placa or "s/placa"}',
                usuario=usuario,
            )
        except ValidationError as e:
            logger.warning('No se pudo postear asiento de comisión (finalizado #%s): %s', finalizado.id, e)
    else:
        logger.warning(
            'Asiento de comisión omitido (finalizado #%s): cliente_sub=%s ingresos_sub=%s comision=%s',
            finalizado.id, bool(cliente_sub), bool(ingresos_sub), comision,
        )

    if actualizar:
        for campo, valor in actualizar.items():
            setattr(finalizado, campo, valor)
        TramiteFinalizado.objects.filter(pk=finalizado.pk).update(**actualizar)


def crear_finalizado_desde_pasarela(pasarela, usuario_que_confirma=None,
                                    observacion_override=None, tarjeta_override=None):
    """Crea el TramiteFinalizado (snapshot) desde `pasarela` y soft-borra la
    pasarela. Devuelve el TramiteFinalizado creado."""
    tarjeta_final = tarjeta_override or pasarela.tarjeta

    # Snapshot del 4x1000 al momento del cierre.
    aplica_4x1000 = bool(tarjeta_final and tarjeta_final.cuatro_por_mil == '1')
    base = (pasarela.precio_lay or Decimal('0')) + (pasarela.comision or Decimal('0'))
    cuatro_por_mil_valor = (base * Decimal('4') / Decimal('1000')) if aplica_4x1000 else Decimal('0')

    with transaction.atomic():
        finalizado = TramiteFinalizado.objects.create(
            pasarela=pasarela,
            tramite_origen_id_snapshot=pasarela.tramite_origen_id,
            usuario=pasarela.tramite_origen.usuario if pasarela.tramite_origen else pasarela.usuario,
            usuario_que_confirma=usuario_que_confirma,
            cliente=pasarela.cliente,
            etiqueta=pasarela.etiqueta,
            precio_cliente=pasarela.precio_cliente,
            tarifario_soat=pasarela.tarifario_soat,
            tarjeta=tarjeta_final,
            tipo_tramite=pasarela.tipo_tramite,
            tipo_vehiculo=pasarela.tipo_vehiculo,
            entidad=pasarela.entidad,
            grupo_soat=pasarela.grupo_soat,
            grupo_clase_runt=pasarela.grupo_clase_runt,
            grupo_subcriterio=pasarela.grupo_subcriterio,
            modulo_pregunta1=pasarela.modulo_pregunta1,
            modulo_pregunta2=pasarela.modulo_pregunta2,
            tarifa_codigo=pasarela.tarifa_codigo,
            tarifa_manual=pasarela.tarifa_manual,
            precio_lay=pasarela.precio_lay,
            comision=pasarela.comision,
            placa=pasarela.placa,
            clase=pasarela.clase,
            tipo_servicio=pasarela.tipo_servicio,
            marca=pasarela.marca,
            linea=pasarela.linea,
            modelo=pasarela.modelo,
            color=pasarela.color,
            cilindraje=pasarela.cilindraje,
            pasajeros_sentados=pasarela.pasajeros_sentados,
            capacidad_carga=pasarela.capacidad_carga,
            peso_bruto=pasarela.peso_bruto,
            chasis=pasarela.chasis,
            vin=pasarela.vin,
            tipo_documento=pasarela.tipo_documento,
            numero_documento=pasarela.numero_documento,
            nombre_completo=pasarela.nombre_completo,
            telefono=pasarela.telefono,
            correo=pasarela.correo,
            direccion=pasarela.direccion,
            tramite_estado=pasarela.tramite_estado,
            confirmacion_estado=pasarela.confirmacion_estado,
            cargar_pdf_estado=pasarela.cargar_pdf_estado,
            observacion=observacion_override if observacion_override is not None else pasarela.observacion,
            comprobante_pago=pasarela.comprobante_pago,
            link_pago=pasarela.link_pago,
            pago_confirmado_at=timezone.now(),
            cuatro_por_mil_valor=cuatro_por_mil_valor,
        )
        # Contabilidad: postear los asientos de emisión + comisión (best-effort).
        _registrar_asientos_soat(finalizado, usuario_que_confirma)
        pasarela.soft_delete()

    return finalizado
