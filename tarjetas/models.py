from django.db import models
from django.conf import settings
from simple_history.models import HistoricalRecords

CUATRO_POR_MIL_CHOICES = (
    ('1', 'Activo'),
    ('0', 'Exento'),
)

# Create your models here.
class Tarjeta(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL,
                                on_delete=models.SET_NULL,
                                null=True,
                                related_name='tarjetas',
                                help_text='Usuario asociado a la tarjeta')
  
    numero      = models.CharField(max_length=32, unique=True)
    titular     = models.CharField(max_length=200)
    descripcion = models.CharField(max_length=255)
    
    cuatro_por_mil = models.CharField(
        max_length=1,
        choices=CUATRO_POR_MIL_CHOICES,
        default='0'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    history = HistoricalRecords()
   
    class Meta:
        db_table     = 'tarjetas'
        verbose_name = 'Tarjeta'
        verbose_name_plural = 'Tarjetas'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.titular} - {self.numero[-4:]}"