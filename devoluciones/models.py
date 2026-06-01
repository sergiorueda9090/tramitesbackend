from django.db import models
from django.conf import settings
from clientes.models import Cliente
from tarjetas.models import Tarjeta
from sub_cuentas.models import SubCuenta
from simple_history.models import HistoricalRecords
import uuid

class Devolucion(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='devoluciones'
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='devoluciones'
    )

    tarjeta = models.ForeignKey(
        Tarjeta,
        on_delete=models.CASCADE,
        related_name='devoluciones'
    )

    valor           = models.DecimalField(max_digits=10, decimal_places=2)
    observacion     = models.TextField(blank=True, null=True)
    fecha           = models.DateTimeField()
    
    cuatro_por_mil = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total          = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    debito  = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento débito')
    credito = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento crédito')
    sub_cuenta = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        related_name='devoluciones',
        help_text='Sub-cuenta contable de credito (caja/banco) asociada al registro'
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
        db_table = 'devoluciones'
        ordering = ['-created_at']
        verbose_name = 'Devolucion'
        verbose_name_plural = 'Devoluciones'

    def __str__(self):
        return f'Devolucion {self.id} - Cliente: {self.cliente} - Tarjeta: {self.tarjeta} - Valor: {self.valor}'

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        from django.utils import timezone
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()