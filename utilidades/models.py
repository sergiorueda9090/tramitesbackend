from django.db import models
from django.utils import timezone
from sub_cuentas.models import SubCuenta
from simple_history.models import HistoricalRecords
import uuid


class Utilidad(models.Model):
    """Snapshot por cada trámite finalizado para reportes de utilidad.

    Se inserta automáticamente vía signal `post_save` sobre
    `finalizados_tramites.TramiteFinalizado`. La fila se conserva aunque
    el trámite finalizado origen se borre (FK con SET_NULL), lo que
    permite mantener el reporte histórico intacto.
    """

    tramite_finalizado = models.OneToOneField(
        'finalizados_tramites.TramiteFinalizado',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utilidad',
        help_text='Trámite finalizado origen del registro de utilidad',
    )

    fecha              = models.DateTimeField(default=timezone.now, help_text='Fecha del trámite (snapshot de pago_confirmado_at)')
    placa              = models.CharField(max_length=20, blank=True, default='')
    comision_proveedor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Snapshot de la comisión (TramiteFinalizado.comision)')
    cilindraje         = models.CharField(max_length=10, blank=True, default='')
    modelo             = models.CharField(max_length=4,  blank=True, default='')
    chasis             = models.CharField(max_length=50, blank=True, default='')

    debito  = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento débito')
    credito = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento crédito')
    sub_cuenta = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        related_name='utilidades',
        null=True, blank=True,
        help_text='Sub-cuenta contable de credito (ingreso por utilidad). Puede quedar null si no esta configurada UTILIDADES_SUB_CUENTA_CODIGO'
    )

    asiento_id = models.UUIDField(
        null=True, blank=True, default=None, editable=False,
        help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'utilidades'
        ordering = ['-fecha', '-created_at']
        verbose_name = 'Utilidad'
        verbose_name_plural = 'Utilidades'

    def __str__(self):
        return f'Utilidad {self.id} - {self.placa or "sin placa"}'

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()
