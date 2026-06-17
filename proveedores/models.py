from django.db import models
from django.conf import settings
from sub_cuentas.models import SubCuenta
from simple_history.models import HistoricalRecords


class Proveedor(models.Model):
    nombre = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default='#1976d2', help_text='Color hexadecimal')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='proveedores_creados',
        help_text='Usuario que creó el registro'
    )
    sub_cuenta = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        related_name='proveedores',
        help_text='Sub-cuenta contable asociada al proveedor (obligatoria)'
    )
    protegido = models.BooleanField(
        default=False,
        help_text='Proveedor del sistema (PREVISORA/MUNDIAL): no se puede editar ni eliminar'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'proveedores'
        ordering = ['-created_at']
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'

    def __str__(self):
        return self.nombre

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
