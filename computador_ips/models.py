from django.db import models
from django.conf import settings
from django.utils import timezone
from simple_history.models import HistoricalRecords


PROTOCOLO_CHOICES = [
    ('http',  'HTTP'),
    ('https', 'HTTPS'),
]


class ComputadorIP(models.Model):
    """Registro de IPs gestionadas por el conmutador.

    Sirve como catálogo de IPs (servidores, APIs externas, etc.) con la
    capacidad de marcar una como `activo=True` para enrutar tráfico hacia
    ella. Por ahora solo se manejan los datos básicos: nombre, IP, puerto,
    protocolo y descripción. La lógica de conmutación (selección exclusiva
    de la IP activa) puede agregarse después.
    """

    nombre      = models.CharField(max_length=100, help_text='Alias o nombre identificador de la IP')
    ip          = models.GenericIPAddressField(help_text='Dirección IPv4 o IPv6')
    puerto      = models.PositiveIntegerField(null=True, blank=True, help_text='Puerto opcional (1-65535)')
    protocolo   = models.CharField(max_length=10, choices=PROTOCOLO_CHOICES, default='http')
    descripcion = models.TextField(blank=True, default='')
    activo      = models.BooleanField(default=False, help_text='Si la IP está activa en el conmutador')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='computador_ips_creadas',
        help_text='Usuario que registró la IP',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'computador_ips'
        ordering = ['-created_at']
        verbose_name = 'IP del conmutador'
        verbose_name_plural = 'IPs del conmutador'

    def __str__(self):
        port = f':{self.puerto}' if self.puerto else ''
        return f'{self.nombre} ({self.protocolo}://{self.ip}{port})'

    @property
    def url(self):
        port = f':{self.puerto}' if self.puerto else ''
        return f'{self.protocolo}://{self.ip}{port}'

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()
