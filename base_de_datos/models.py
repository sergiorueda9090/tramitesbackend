from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


TIPO_TRAMITE_CHOICES = [
    ('SOAT', 'SOAT'),
    ('SOAT_ESPECIAL', 'SOAT Especial'),
]

TIPO_VEHICULO_CHOICES = [
    ('USADO', 'Usado'),
    ('CERO_KM', 'Cero Kilómetros'),
]

TIPO_DOCUMENTO_CHOICES = [
    ('C', 'Cédula de Ciudadanía'),
    ('E', 'Cédula de Extranjería'),
    ('N', 'NIT'),
    ('P', 'Pasaporte'),
    ('T', 'Tarjeta de Identidad'),
    ('R', 'Registro Civil'),
    ('D', 'Documento de Identificación Extranjero'),
    ('S', 'Salvoconducto'),
    ('L', 'Licencia de Conducción'),
    ('PE', 'Permiso Especial de Permanencia (PEP)'),
    ('PT', 'Permiso por Protección Temporal (PPT)'),
]


class RegistroVehiculo(models.Model):
    # Relaciones
    usuario = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='registros_vehiculo'
    )
    cliente = models.ForeignKey(
        'clientes.Cliente', on_delete=models.CASCADE,
        related_name='registros_vehiculo'
    )

    # Datos del trámite
    tipo_tramite = models.CharField(max_length=20, choices=TIPO_TRAMITE_CHOICES, default='SOAT')
    tipo_vehiculo = models.CharField(max_length=20, choices=TIPO_VEHICULO_CHOICES, default='USADO')

    # Datos del titular
    es_propietario = models.BooleanField(default=True)
    tipo_documento = models.CharField(max_length=5, choices=TIPO_DOCUMENTO_CHOICES, default='C')
    numero_documento = models.CharField(max_length=50)
    nombre_completo = models.CharField(max_length=255)
    telefono = models.CharField(max_length=20, null=True, blank=True)

    # Datos del vehículo
    placa = models.CharField(max_length=20, null=True, blank=True)
    clase = models.CharField(max_length=100, null=True, blank=True)
    clasificacion = models.CharField(max_length=100, null=True, blank=True)
    tipo_servicio = models.CharField(max_length=100, null=True, blank=True)
    tipo_carroceria = models.CharField(max_length=100, null=True, blank=True)
    vin = models.CharField(max_length=50, null=True, blank=True)
    num_motor = models.CharField(max_length=50, null=True, blank=True)
    num_chasis = models.CharField(max_length=50, null=True, blank=True)
    marca = models.CharField(max_length=100, null=True, blank=True)
    linea = models.CharField(max_length=100, null=True, blank=True)
    modelo = models.CharField(max_length=10, null=True, blank=True)
    cilindraje = models.CharField(max_length=20, null=True, blank=True)
    color = models.CharField(max_length=50, null=True, blank=True)
    organismo_transito = models.CharField(max_length=255, null=True, blank=True)

    # Cotización (solo se completan si el flujo del Cotizador resolvió la
    # tarifa sin anomalías — ver guardarRegistroDesdeCotizadorThunk y la
    # actualización desde Step7).
    precio_lay = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    comision   = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Timestamps y soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Historial
    history = HistoricalRecords()

    class Meta:
        db_table = 'base_de_datos_registro_vehiculo'
        ordering = ['-created_at']
        verbose_name = 'Registro de Vehículo'
        verbose_name_plural = 'Registros de Vehículos'

    def __str__(self):
        return f"{self.placa or 'Sin placa'} - {self.nombre_completo} ({self.numero_documento})"

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()
