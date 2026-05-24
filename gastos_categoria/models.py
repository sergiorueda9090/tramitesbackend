from django.db import models
from django.conf import settings
from django.utils import timezone
from sub_cuentas.models import SubCuenta
from simple_history.models import HistoricalRecords


class GastoCategoria(models.Model):
    """Categoría a la que pertenece un gasto.

    Mismo patrón que el resto de modelos del proyecto:
    soft delete (`deleted_at` + `soft_delete()`/`restore()`) e historial
    (`HistoricalRecords`).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gastos_categorias_creadas',
        help_text='Usuario que creó la categoría',
    )

    nombre      = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255, blank=True, default='')

    debito  = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento débito')
    credito = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento crédito')
    sub_cuenta = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        unique=True,
        related_name='gastos_categorias',
        help_text='Sub-cuenta contable asociada (obligatoria y unica por registro)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'gastos_categorias'
        ordering = ['-created_at']
        verbose_name = 'Categoría de gasto'
        verbose_name_plural = 'Categorías de gasto'

    def __str__(self):
        return self.nombre

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()
