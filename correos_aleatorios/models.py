from django.db import models
from django.conf import settings
from simple_history.models import HistoricalRecords


class CorreoAleatorio(models.Model):
    """
    Pool de correos aleatorios. Cada vez que se genera un link de pago
    (Previsora / Mundial) se toma un correo de este pool para enviarlo al
    generador externo. Mismo patrón de diseño que los demás módulos:
    soft-delete + history.
    """
    correo      = models.EmailField(unique=True)
    descripcion = models.CharField(max_length=255, blank=True, default='')
    activo      = models.BooleanField(default=True, help_text='Solo los activos entran en la selección aleatoria')

    # Telemetría de uso
    veces_usado = models.PositiveIntegerField(default=0)
    ultimo_uso  = models.DateTimeField(null=True, blank=True)

    usuario     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='correos_aleatorios')

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'correos_aleatorios'
        ordering = ['-created_at']
        verbose_name = 'Correo Aleatorio'
        verbose_name_plural = 'Correos Aleatorios'

    def __str__(self):
        return self.correo

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

    def registrar_uso(self):
        from django.utils import timezone
        self.veces_usado = (self.veces_usado or 0) + 1
        self.ultimo_uso = timezone.now()
        self.save()
