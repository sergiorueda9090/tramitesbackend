import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from finalizados_tramites.models import TramiteFinalizado
from movimiento_contable.services import registrar_asiento, revertir_asiento
from sub_cuentas.models import SubCuenta
from utilidades.models import Utilidad

logger = logging.getLogger(__name__)


MODULO_ORIGEN = 'utilidades'


def _sub_cuenta_ingreso_utilidad():
    """SubCuenta de credito (ingreso) configurada via UTILIDADES_SUB_CUENTA_CODIGO.

    Devuelve None si no esta configurada o no existe; el caller debe
    crear/dejar la Utilidad sin asiento y loggear.
    """
    codigo = (getattr(settings, 'UTILIDADES_SUB_CUENTA_CODIGO', '') or '').strip()
    if not codigo:
        return None
    try:
        return SubCuenta.objects.get(codigo=codigo, deleted_at__isnull=True)
    except SubCuenta.DoesNotExist:
        logger.warning(
            "Sub-cuenta '%s' (UTILIDADES_SUB_CUENTA_CODIGO) no existe o esta eliminada", codigo
        )
        return None


def _descripcion(utilidad, tramite):
    return f"Utilidad #{utilidad.id} | Tramite finalizado #{tramite.id} | Placa: {tramite.placa or 'sin placa'}"


@receiver(post_save, sender=TramiteFinalizado)
def crear_utilidad_desde_tramite_finalizado(sender, instance, created, **kwargs):
    """Crea (o actualiza) la Utilidad asociada al TramiteFinalizado.

    Si hay datos contables suficientes (tarjeta con sub_cuenta + setting
    UTILIDADES_SUB_CUENTA_CODIGO + comision > 0), registra el asiento de
    partida doble:
      D=tarjeta.sub_cuenta (banco), C=utilidad.sub_cuenta (ingreso),
      valor=comision_proveedor.

    NUNCA falla la finalizacion del tramite — los errores se loggean y se
    deja la Utilidad sin asiento para que el management command de backfill
    la procese mas adelante.
    """
    defaults = {
        'fecha':              instance.pago_confirmado_at,
        'placa':              instance.placa or '',
        'comision_proveedor': instance.comision,
        'cilindraje':         instance.cilindraje or '',
        'modelo':             instance.modelo or '',
        'chasis':             instance.chasis or '',
    }

    sub_cuenta_ingreso = _sub_cuenta_ingreso_utilidad()
    tarjeta = instance.tarjeta
    tarjeta_sub_cuenta = tarjeta.sub_cuenta if (tarjeta and tarjeta.sub_cuenta_id) else None
    comision = instance.comision

    try:
        existente = Utilidad.objects.filter(tramite_finalizado=instance).first()
        if existente:
            for k, v in defaults.items():
                setattr(existente, k, v)
            existente.sub_cuenta = sub_cuenta_ingreso  # puede ser None
            existente.save()

            # Re-asentar si tenemos los datos completos.
            _try_register(existente, instance, tarjeta_sub_cuenta, sub_cuenta_ingreso, comision)
            return

        utilidad = Utilidad.objects.create(
            tramite_finalizado=instance,
            sub_cuenta=sub_cuenta_ingreso,
            **defaults,
        )
        _try_register(utilidad, instance, tarjeta_sub_cuenta, sub_cuenta_ingreso, comision)

    except Exception as e:
        # Cualquier fallo en el flujo de utilidades NO debe romper la finalizacion.
        logger.exception("Error creando/asentando Utilidad para tramite %s: %s", instance.pk, e)


def _try_register(utilidad, tramite, tarjeta_sub_cuenta, sub_cuenta_ingreso, comision):
    """Intenta registrar el asiento. Si falta algun dato, deja la Utilidad sin asiento."""
    if utilidad.asiento_id:
        try:
            revertir_asiento(utilidad.asiento_id)
            Utilidad.objects.filter(pk=utilidad.pk).update(asiento_id=None)
            utilidad.asiento_id = None
        except Exception as e:
            logger.warning("No se pudo revertir asiento previo de Utilidad %s: %s", utilidad.pk, e)
            return

    if tarjeta_sub_cuenta is None:
        logger.info("Utilidad %s sin asiento: tramite finalizado %s no tiene tarjeta con sub-cuenta",
                    utilidad.pk, tramite.pk)
        return
    if sub_cuenta_ingreso is None:
        logger.info("Utilidad %s sin asiento: UTILIDADES_SUB_CUENTA_CODIGO no configurada", utilidad.pk)
        return
    if not comision or comision <= 0:
        logger.info("Utilidad %s sin asiento: comision_proveedor invalida (%s)", utilidad.pk, comision)
        return
    if tarjeta_sub_cuenta.pk == sub_cuenta_ingreso.pk:
        logger.warning(
            "Utilidad %s sin asiento: tarjeta.sub_cuenta = utilidad.sub_cuenta (ambas %s)",
            utilidad.pk, tarjeta_sub_cuenta.codigo,
        )
        return

    try:
        with transaction.atomic():
            asiento_id = registrar_asiento(
                fecha=tramite.pago_confirmado_at,
                debito_sub_cuenta=tarjeta_sub_cuenta,
                credito_sub_cuenta=sub_cuenta_ingreso,
                valor=comision,
                modulo_origen=MODULO_ORIGEN,
                origen_id=utilidad.pk,
                descripcion=_descripcion(utilidad, tramite),
                usuario=tramite.usuario_que_confirma or tramite.usuario,
            )
            Utilidad.objects.filter(pk=utilidad.pk).update(asiento_id=asiento_id)
            utilidad.asiento_id = asiento_id
    except (ValidationError, Exception) as e:
        logger.warning("No se pudo registrar asiento de Utilidad %s: %s", utilidad.pk, e)
