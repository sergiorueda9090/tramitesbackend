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


class Cotizador(models.Model):
    """
    Cotización rápida (módulo Cotizador Rápido).

    Mismo patrón de diseño que el módulo `cotizador` (soft-delete + history +
    máquina de estados), pero con tabla y related_name propios para no colisionar
    con aquel. La cotización rápida se genera a partir de la placa: el precio se
    toma de la API de Previsora y se contrasta con la consulta normal por VIN.
    """
    usuario        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='cotizadores_rapidos', help_text='Usuario asociado a la cotización rápida')
    cliente        = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='cotizadores_rapidos', null=True, blank=True)
    etiqueta       = models.ForeignKey(Etiqueta, on_delete=models.CASCADE, related_name='cotizadores_rapidos', null=True, blank=True)
    precio_cliente = models.ForeignKey(PrecioCliente, on_delete=models.CASCADE, related_name='cotizadores_rapidos', null=True, blank=True)

    descripcion = models.TextField(blank=True, default='')
    precio_lay  = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    comision    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Precios de la cotización rápida y su comparación
    precio_previsora = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Precio devuelto por la API de Previsora')
    precio_runt      = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Precio calculado por la consulta normal (por VIN/RUNT)')
    precios_coinciden = models.BooleanField(default=False, help_text='True si el precio de Previsora coincide con el de la consulta normal')
    es_caso_especial  = models.BooleanField(default=False)

    placa      = models.CharField(max_length=20)
    vin        = models.CharField(max_length=50, blank=True, default='')
    clindraje  = models.CharField(max_length=10, blank=True, default='')
    modelo     = models.CharField(max_length=4, blank=True, default='')
    chasis     = models.CharField(max_length=50, blank=True, default='')

    tipo_documento   = models.CharField(max_length=20, choices=TYPO_DOCUMENTO, default='CC')
    numero_documento = models.CharField(max_length=50, blank=True, default='')
    nombre_completo  = models.CharField(max_length=255, blank=True, default='')
    telefono         = models.CharField(max_length=20, blank=True, default='')
    correo           = models.EmailField(blank=True, default='')
    direccion        = models.TextField(blank=True, default='')

    cotizador_estado     = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='1')
    tramite_estado       = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')
    confirmacion_estado  = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')
    cargar_pdf_estado    = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'cotizador_rapido_cotizadores'
        ordering = ['-created_at']
        verbose_name = 'Cotización Rápida'
        verbose_name_plural = 'Cotizaciones Rápidas'

    def __str__(self):
        return f'Cotización rápida {self.id} - {self.placa}'

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
        db_table = 'cotizador_rapido_pagos'
        ordering = ['-created_at']
        verbose_name = 'Pago Cotización Rápida'
        verbose_name_plural = 'Pagos Cotización Rápida'

    def __str__(self):
        return f'Pago {self.id} - Cotización rápida: {self.cotizador.id}'
