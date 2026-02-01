from django.db import models
from clientes.models import Cliente, PrecioCliente
from etiquetas.models import Etiqueta
from django.conf import settings
from simple_history.models import HistoricalRecords

TYPO_DOCUMENTO = [
    ('CC', 'Cédula de Ciudadanía'),
    ('CE', 'Cédula de Extranjería'),
    ('NIT', 'Número de Identificación Tributaria'),
    ('PAS', 'Pasaporte'),
]

ESTADO_CHOICES = [
    ('0', 'Inactivo'),
    ('1', 'Activo'),
]
# Create your models here.
class Cotizador(models.Model):
    usuario        = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,related_name='cotizadores',help_text='Usuario asociado al cotizador'),
    cliente        = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='cotizadores')
    etiqueta       = models.ForeignKey(Etiqueta, on_delete=models.CASCADE, related_name='cotizadores')
    precio_cliente = models.ForeignKey(PrecioCliente, on_delete=models.CASCADE, related_name='cotizadores')
   
    descripcion = models.TextField()
    precio_lay  = models.DecimalField(max_digits=10, decimal_places=2)
    comision    = models.DecimalField(max_digits=10, decimal_places=2)

    placa      = models.CharField(max_length=20)
    clindraje  = models.CharField(max_length=10)
    modelo     = models.CharField(max_length=4)
    chasis     = models.CharField(max_length=50)

    tipo_documento   = models.CharField(max_length=20, choices=TYPO_DOCUMENTO, default='CC')
    numero_documento = models.CharField(max_length=50)
    nombre_completo  = models.CharField(max_length=255)
    telefono         = models.CharField(max_length=20)
    correo           = models.EmailField()
    direccion        = models.TextField()

    cotizador_estado     = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='1')
    tramite_estado       = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')
    confirmacion_estado  = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')
    cargar_pdf_estado    = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')

    #image_url = models.ImageField(upload_to='cotizadores/images/', null=True, blank=True)
    #pdf_url   = models.FileField(upload_to='cotizadores/pdfs/', null=True, blank=True)
    
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'cotizadores'
        ordering = ['-created_at']
        verbose_name = 'Cotizador'
        verbose_name_plural = 'Cotizadores'

    def __str__(self):
        return f'Cotizador {self.id} - Cliente: {self.cliente.nombre}'
    
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

class CotizadorPagos(models.Model):
    cotizador   = models.ForeignKey(Cotizador, on_delete=models.CASCADE, related_name='pagos')
    
    precio_lay  = models.DecimalField(max_digits=10, decimal_places=2)
    comision    = models.DecimalField(max_digits=10, decimal_places=2)

    fecha_pago  = models.DateField()
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()
    
    class Meta:
        db_table = 'cotizador_pagos'
        ordering = ['-created_at']
        verbose_name = 'Cotizador Pago'
        verbose_name_plural = 'Cotizador Pagos'

    def __str__(self):
        return f'Pago {self.id} - Cotizador: {self.cotizador.id}'