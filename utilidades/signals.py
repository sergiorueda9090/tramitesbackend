from django.db.models.signals import post_save
from django.dispatch import receiver

from finalizados_tramites.models import TramiteFinalizado
from utilidades.models import Utilidad


@receiver(post_save, sender=TramiteFinalizado)
def crear_utilidad_desde_tramite_finalizado(sender, instance, created, **kwargs):
    """Crea (o actualiza) un registro de Utilidad por cada TramiteFinalizado.

    Se mantiene un snapshot 1-a-1 con los 6 campos requeridos por el reporte:
    fecha, placa, comision_proveedor, cilindraje, modelo, chasis.
    """
    defaults = {
        'fecha':              instance.pago_confirmado_at,
        'placa':              instance.placa or '',
        'comision_proveedor': instance.comision,
        'cilindraje':         instance.cilindraje or '',
        'modelo':              instance.modelo or '',
        'chasis':              instance.chasis or '',
    }
    Utilidad.objects.update_or_create(
        tramite_finalizado=instance,
        defaults=defaults,
    )
