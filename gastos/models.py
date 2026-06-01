from django.db import models
from django.conf import settings
from tarjetas.models import Tarjeta
from sub_cuentas.models import SubCuenta
from simple_history.models import HistoricalRecords
import uuid

# Create your models here.
class Gasto(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='gastos_creados',
        help_text='Usuario que creó el gasto'
    )
    nombre      = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'gastos'
        ordering = ['-created_at']
        verbose_name = 'Gasto'
        verbose_name_plural = 'Gastos'

    def __str__(self):
        return f"{self.nombre}"
    
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
    
class GastoRelacion(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gasto_relaciones'
    )

    gasto = models.ForeignKey(
        'gastos_categoria.GastoCategoria',
        on_delete=models.CASCADE,
        related_name='gasto_relaciones',
        help_text='Categoría asociada al gasto'
    )

    tarjeta = models.ForeignKey(
        Tarjeta,
        on_delete=models.CASCADE,
        related_name='gasto_relaciones'
    )

    valor       = models.DecimalField(max_digits=10, decimal_places=2)
    observacion = models.TextField(blank=True, null=True)
    fecha       = models.DateTimeField()

    cuatro_por_mil = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total          = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    debito  = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento débito')
    credito = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento crédito')
    sub_cuenta = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        related_name='gasto_relaciones',
        help_text='Sub-cuenta contable de credito (medio de pago) asociada al registro'
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
        db_table = 'gasto_relaciones'
        ordering = ['-created_at']
        verbose_name = 'Relación Gasto'
        verbose_name_plural = 'Relaciones Gasto'

    def __str__(self):
        return f"Gasto: {self.gasto.nombre} - Tarjeta: {self.tarjeta.numero}"

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