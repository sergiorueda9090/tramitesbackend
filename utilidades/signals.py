import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from finalizados_tramites.models import TramiteFinalizado
from utilidades.models import Utilidad
from sub_cuentas.models import SubCuenta

logger = logging.getLogger(__name__)


@receiver(post_save, sender=TramiteFinalizado)
def crear_utilidad_desde_tramite_finalizado(sender, instance, created, **kwargs):
    """Crea (o actualiza) un registro de Utilidad por cada TramiteFinalizado.

    Snapshot 1-a-1 con los campos del reporte. La sub_cuenta es obligatoria y
    UNIQUE por registro: el signal toma la primera SubCuenta activa que no este
    ya asignada a otra Utilidad. Si no hay sub-cuentas disponibles, se omite la
    creacion y se loggea — la finalizacion del tramite NO falla.
    """
    defaults = {
        'fecha':              instance.pago_confirmado_at,
        'placa':              instance.placa or '',
        'comision_proveedor': instance.comision,
        'cilindraje':         instance.cilindraje or '',
        'modelo':              instance.modelo or '',
        'chasis':             instance.chasis or '',
    }

    # Si ya existe Utilidad para este tramite -> solo actualizar campos snapshot.
    existente = Utilidad.objects.filter(tramite_finalizado=instance).first()
    if existente:
        for k, v in defaults.items():
            setattr(existente, k, v)
        existente.save()
        return

    # Buscar sub-cuenta libre (no asignada a ninguna otra Utilidad ni eliminada)
    sub_libre = (
        SubCuenta.objects
        .filter(deleted_at__isnull=True)
        .exclude(pk__in=Utilidad.objects.values_list('sub_cuenta_id', flat=True))
        .order_by('pk')
        .first()
    )
    if not sub_libre:
        logger.warning(
            "No hay sub-cuentas libres para crear Utilidad del tramite %s — registro omitido",
            instance.pk,
        )
        return

    Utilidad.objects.create(
        tramite_finalizado=instance,
        sub_cuenta=sub_libre,
        **defaults,
    )
