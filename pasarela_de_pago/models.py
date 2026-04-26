from django.db import models
from django.conf import settings
from simple_history.models import HistoricalRecords

from clientes.models import Cliente, PrecioCliente
from etiquetas.models import Etiqueta
from tarifario_soat.models import TarifarioSoat


# Choices duplicadas a propósito para mantener independencia del app de tramites.
# Si cambian en tramites, replicar acá (o refactorizar a un módulo compartido más adelante).

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

TIPO_TRAMITE_CHOICES = [
    ('SOAT', 'SOAT'),
    ('SOAT_ESPECIAL', 'SOAT Especial'),
]

TIPO_VEHICULO_CHOICES = [
    ('USADO', 'Usado'),
    ('CERO_KM', 'Cero Kilómetros'),
]

GRUPO_SOAT_CHOICES = [
    ('MOTOS', 'Motos'),
    ('MOTOCARROS', 'Motocarros'),
    ('CICLOMOTORES', 'Ciclomotores'),
    ('CARGA', 'Carga'),
    ('CAMPEROS', 'Camperos'),
    ('FAMILIAR_5P', 'Familiares 5P'),
    ('INTERMUNICIPAL', 'Intermunicipal'),
    ('TAXI', 'Taxi'),
    ('BUS_URBANO', 'Bus Urbano'),
    ('6_PASAJEROS', '6+ Pasajeros'),
]


class PasarelaPago(models.Model):
    # Trazabilidad al trámite origen (se crea al "enviar a pasarela" desde tramites)
    tramite_origen = models.ForeignKey(
        'tramites.Tramite',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pasarela_pagos',
        help_text='Trámite desde el cual se envió a pasarela'
    )

    usuario        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='pasarela_pagos', help_text='Usuario que creó el registro en pasarela')
    cliente        = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='pasarela_pagos')
    etiqueta       = models.ForeignKey(Etiqueta, on_delete=models.SET_NULL, null=True, blank=True, related_name='pasarela_pagos')
    precio_cliente = models.ForeignKey(PrecioCliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='pasarela_pagos')
    tarifario_soat = models.ForeignKey(TarifarioSoat, on_delete=models.SET_NULL, null=True, blank=True, related_name='pasarela_pagos', help_text='Tarifa SOAT resuelta')

    # Tipo de trámite (snapshot)
    tipo_tramite  = models.CharField(max_length=20, choices=TIPO_TRAMITE_CHOICES, default='SOAT')
    tipo_vehiculo = models.CharField(max_length=10, choices=TIPO_VEHICULO_CHOICES, blank=True, default='')

    # Resolución del árbol Grupo SOAT → Módulo → Tarifa (snapshot)
    grupo_soat          = models.CharField(max_length=20, choices=GRUPO_SOAT_CHOICES, blank=True, default='')
    grupo_clase_runt    = models.CharField(max_length=50, blank=True, default='')
    grupo_subcriterio   = models.CharField(max_length=50, blank=True, default='')
    modulo_pregunta1    = models.CharField(max_length=30, blank=True, default='')
    modulo_pregunta2    = models.CharField(max_length=30, blank=True, default='')
    tarifa_codigo       = models.CharField(max_length=100, blank=True, default='', help_text='Snapshot del código de tarifa')
    tarifa_manual       = models.BooleanField(default=False, help_text='True si la tarifa fue seleccionada manualmente')

    # Valores financieros
    precio_lay = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    comision   = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Datos del vehículo (snapshot RUNT)
    placa              = models.CharField(max_length=20,  blank=True, default='')
    clase              = models.CharField(max_length=100, blank=True, default='')
    tipo_servicio      = models.CharField(max_length=50,  blank=True, default='')
    marca              = models.CharField(max_length=100, blank=True, default='')
    linea              = models.CharField(max_length=100, blank=True, default='')
    modelo             = models.CharField(max_length=4,   blank=True, default='')
    color              = models.CharField(max_length=50,  blank=True, default='')
    cilindraje         = models.CharField(max_length=10,  blank=True, default='')
    pasajeros_sentados = models.CharField(max_length=10,  blank=True, default='')
    capacidad_carga    = models.CharField(max_length=20,  blank=True, default='')
    peso_bruto         = models.CharField(max_length=20,  blank=True, default='')
    chasis             = models.CharField(max_length=50,  blank=True, default='')
    vin                = models.CharField(max_length=50,  blank=True, default='')

    # Titular / datos de contacto
    tipo_documento   = models.CharField(max_length=20, choices=TYPO_DOCUMENTO, default='CC')
    numero_documento = models.CharField(max_length=50,  blank=True, default='')
    nombre_completo  = models.CharField(max_length=255, blank=True, default='')
    telefono         = models.CharField(max_length=20,  blank=True, default='')
    correo           = models.EmailField(blank=True, default='')
    direccion        = models.TextField(blank=True, default='')

    # Estados del workflow (misma estructura que tramites)
    tramite_estado      = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='1')
    confirmacion_estado = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')
    cargar_pdf_estado   = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'pasarela_de_pago'
        ordering = ['-created_at']
        verbose_name = 'Pasarela de Pago'
        verbose_name_plural = 'Pasarela de Pagos'

    def __str__(self):
        return f'Pasarela {self.id} - {self.placa or "sin placa"} - Cliente: {self.cliente.nombre}'

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
