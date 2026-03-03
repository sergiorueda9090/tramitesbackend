from django.db import models
from django.conf import settings
from simple_history.models import HistoricalRecords


class TarifarioSoat(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='tarifarios_soat',
        help_text='Usuario que creó el tarifario'
    )
    codigo_tarifa = models.CharField(max_length=100)
    descripcion   = models.CharField(max_length=255)
    valor         = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'tarifario_soat'
        ordering = ['-created_at']
        verbose_name = 'Tarifario SOAT'
        verbose_name_plural = 'Tarifarios SOAT'

    def __str__(self):
        return f"{self.codigo_tarifa} - {self.descripcion}"

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
