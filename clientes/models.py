from django.db import models
from django.conf import settings
from sub_cuentas.models import SubCuenta
from tarifario_soat.models import TarifarioSoat
from simple_history.models import HistoricalRecords


class TipoCliente(models.TextChoices):
    CDA = 'cda', 'CDA'
    CONCESIONARIO = 'concesionario', 'Concesionario'
    PARTICULAR = 'particular', 'Particular'
    PUNTO_ALIADO = 'punto_aliado', 'Punto aliado'


class MedioComunicacion(models.TextChoices):
    EMAIL = 'email', 'Email'
    WHATSAPP = 'whatsapp', 'WhatsApp'


class Cliente(models.Model):
    color = models.CharField(max_length=7, default='#1976d2', help_text='Color hexadecimal')
    nombre = models.CharField(max_length=255)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clientes_asignados',
        help_text='Usuario asociado al cliente'
    )
    tipo_cliente = models.CharField(
        max_length=20,
        choices=TipoCliente.choices,
        default=TipoCliente.PARTICULAR
    )
    medio_comunicacion = models.CharField(
        max_length=10,
        choices=MedioComunicacion.choices,
        default=MedioComunicacion.EMAIL
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='clientes_creados',
        help_text='Usuario que creó el registro'
    )
    sub_cuenta = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        related_name='clientes',
        help_text='Sub-cuenta contable asociada al cliente (obligatoria)'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'clientes'
        ordering = ['-created_at']
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

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

class PrecioCliente(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='precios'
    )
    codigo_tarifa = models.ForeignKey(
        TarifarioSoat,
        on_delete=models.PROTECT,
        related_name='precios_clientes',
        help_text='Codigo de tarifa del Tarifario SOAT'
    )
    comision = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Comision (COP) que agrega el cliente para esta tarifa'
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'precios_clientes'
        ordering = ['-created_at']
        verbose_name = 'Precio Cliente'
        verbose_name_plural = 'Precios Clientes'

    def __str__(self):
        codigo = self.codigo_tarifa.codigo_tarifa if self.codigo_tarifa else '-'
        return f'Tarifa: {codigo} - Comision: {self.comision}'
