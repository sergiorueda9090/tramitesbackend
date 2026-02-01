from django.db import models
from django.conf import settings
from clientes.models import Cliente 
from simple_history.models import HistoricalRecords

class AjusteDeSaldo(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ajustes_de_saldo'
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='ajustes_de_saldo'
    )

    valor       = models.DecimalField(max_digits=10, decimal_places=2)
    observacion = models.TextField(blank=True, null=True)
    fecha       = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'ajustes_de_saldo'
        ordering = ['-created_at']
        verbose_name = 'Ajuste De Saldo'
        verbose_name_plural = 'Ajustes De Saldo'

    def __str__(self):
        return f'AjusteDeSaldo {self.id} - Cliente: {self.cliente} - Valor: {self.valor}'

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