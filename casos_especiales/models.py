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


class CasoEspecial(models.Model):
    usuario        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='casos_especiales', help_text='Usuario asociado al caso especial')
    cliente        = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='casos_especiales')
    etiqueta       = models.ForeignKey(Etiqueta, on_delete=models.SET_NULL, null=True, blank=True, related_name='casos_especiales')
    precio_cliente = models.ForeignKey(PrecioCliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='casos_especiales')

    descripcion = models.TextField(blank=True, default='')
    precio_lay  = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    comision    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    placa      = models.CharField(max_length=20, blank=True, default='')
    clindraje  = models.CharField(max_length=10, blank=True, default='')
    modelo     = models.CharField(max_length=4,  blank=True, default='')
    chasis     = models.CharField(max_length=50, blank=True, default='')

    tipo_documento   = models.CharField(max_length=20, choices=TYPO_DOCUMENTO, default='CC')
    numero_documento = models.CharField(max_length=50,  blank=True, default='')
    nombre_completo  = models.CharField(max_length=255, blank=True, default='')
    telefono         = models.CharField(max_length=20,  blank=True, default='')
    correo           = models.EmailField(blank=True, default='')
    direccion        = models.TextField(blank=True, default='')

    caso_especial_estado = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='1')
    tramite_estado       = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')
    confirmacion_estado  = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')
    cargar_pdf_estado    = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'casos_especiales'
        ordering = ['-created_at']
        verbose_name = 'Caso Especial'
        verbose_name_plural = 'Casos Especiales'

    def __str__(self):
        return f'Caso Especial {self.id} - Cliente: {self.cliente.nombre}'

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


class CasoEspecialPagos(models.Model):
    caso_especial = models.ForeignKey(CasoEspecial, on_delete=models.CASCADE, related_name='pagos')

    precio_lay  = models.DecimalField(max_digits=10, decimal_places=2)
    comision    = models.DecimalField(max_digits=10, decimal_places=2)

    fecha_pago  = models.DateField()
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'caso_especial_pagos'
        ordering = ['-created_at']
        verbose_name = 'Caso Especial Pago'
        verbose_name_plural = 'Casos Especiales Pagos'

    def __str__(self):
        return f'Pago {self.id} - Caso Especial: {self.caso_especial.id}'
