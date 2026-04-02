from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


METODO_HTTP_CHOICES = [
    ('GET', 'GET'),
    ('POST', 'POST'),
]


class ExternalEndpoint(models.Model):
    """
    Catálogo de endpoints externos disponibles.
    Cada registro representa una API externa que el sistema puede consumir.
    """
    nombre = models.CharField(max_length=100, help_text='Nombre descriptivo del endpoint')
    codigo = models.CharField(max_length=50, unique=True, help_text='Código interno único (ej: RUNT_VEHICULO)')
    url_base = models.CharField(max_length=500, help_text='URL base del endpoint externo')
    metodo_http = models.CharField(max_length=10, choices=METODO_HTTP_CHOICES, default='GET')
    descripcion = models.TextField(blank=True, null=True, help_text='Descripción del propósito del endpoint')
    activo = models.BooleanField(default=True, help_text='Si el endpoint está habilitado para uso')
    timeout = models.IntegerField(default=30, help_text='Timeout en segundos para la petición')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'api_app_external_endpoints'
        ordering = ['nombre']
        verbose_name = 'Endpoint Externo'
        verbose_name_plural = 'Endpoints Externos'

    def __str__(self):
        return f'{self.nombre} ({self.codigo}) - {self.metodo_http}'

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()
