from django.db import models
from django.conf import settings
from django.utils import timezone
from simple_history.models import HistoricalRecords

from clientes.models import Cliente, PrecioCliente
from etiquetas.models import Etiqueta
from tarifario_soat.models import TarifarioSoat
from tarjetas.models import Tarjeta


# Choices replicadas a propósito para mantener independencia del app de tramites.

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

ENTIDAD_CHOICES = [
    ('MUNDIAL', 'Mundial'),
    ('PREVISORA', 'Previsora'),
    ('SOLIDARIA', 'Solidaria'),
    ('MANUAL', 'Manual'),
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


class TramiteFinalizado(models.Model):
    """Snapshot de un trámite cuyo pago fue confirmado en Pasarela.

    La fila se inserta automáticamente desde `pasarela_de_pago.create_pasarela`
    cuando el POST trae `tramite_origen`. El registro es independiente de
    `tramites.Tramite` y de `pasarela_de_pago.PasarelaPago`: aunque ambos
    se borren, se conserva el snapshot completo.
    """

    # Trazabilidad al origen
    pasarela = models.ForeignKey(
        'pasarela_de_pago.PasarelaPago',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='finalizados',
        help_text='Registro de pasarela que disparó la finalización',
    )
    tramite_origen_id_snapshot = models.IntegerField(
        null=True,
        blank=True,
        help_text='ID original del trámite (se conserva aunque se borre la fila en tramites)',
    )

    # Usuarios
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tramites_finalizados',
        help_text='Usuario dueño del trámite original',
    )
    usuario_que_confirma = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tramites_finalizados_confirmados',
        help_text='Usuario que confirmó el pago en el modal de timer',
    )

    # Snapshot de relaciones
    cliente        = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='tramites_finalizados')
    etiqueta       = models.ForeignKey(Etiqueta, on_delete=models.SET_NULL, null=True, blank=True, related_name='tramites_finalizados')
    precio_cliente = models.ForeignKey(PrecioCliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='tramites_finalizados')
    tarifario_soat = models.ForeignKey(TarifarioSoat, on_delete=models.SET_NULL, null=True, blank=True, related_name='tramites_finalizados', help_text='Tarifa SOAT resuelta')
    tarjeta        = models.ForeignKey(Tarjeta, on_delete=models.SET_NULL, null=True, blank=True, related_name='tramites_finalizados', help_text='Tarjeta usada para el pago')

    # Tipo de trámite (snapshot)
    tipo_tramite  = models.CharField(max_length=20, choices=TIPO_TRAMITE_CHOICES, default='SOAT')
    tipo_vehiculo = models.CharField(max_length=10, choices=TIPO_VEHICULO_CHOICES, blank=True, default='')
    entidad       = models.CharField(max_length=20, choices=ENTIDAD_CHOICES, blank=True, default='', help_text='Aseguradora (snapshot)')

    # Resolución del árbol Grupo SOAT (snapshot)
    grupo_soat          = models.CharField(max_length=20, choices=GRUPO_SOAT_CHOICES, blank=True, default='')
    grupo_clase_runt    = models.CharField(max_length=50, blank=True, default='')
    grupo_subcriterio   = models.CharField(max_length=50, blank=True, default='')
    modulo_pregunta1    = models.CharField(max_length=30, blank=True, default='')
    modulo_pregunta2    = models.CharField(max_length=30, blank=True, default='')
    tarifa_codigo       = models.CharField(max_length=100, blank=True, default='')
    tarifa_manual       = models.BooleanField(default=False)

    # Valores financieros (snapshot)
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

    # Titular / contacto (snapshot)
    tipo_documento   = models.CharField(max_length=20, choices=TYPO_DOCUMENTO, default='CC')
    numero_documento = models.CharField(max_length=50,  blank=True, default='')
    nombre_completo  = models.CharField(max_length=255, blank=True, default='')
    telefono         = models.CharField(max_length=20,  blank=True, default='')
    correo           = models.EmailField(blank=True, default='')
    direccion        = models.TextField(blank=True, default='')

    # Estados snapshot (lo que tenía el trámite cuando se finalizó)
    tramite_estado      = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')
    confirmacion_estado = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='0')
    cargar_pdf_estado   = models.CharField(max_length=1, choices=ESTADO_CHOICES, default='1')

    # Datos del cierre
    observacion         = models.TextField(blank=True, default='', help_text='Observación capturada en el modal de timer al confirmar el pago')
    comprobante_pago    = models.URLField(max_length=1000, blank=True, default='', help_text='URL del comprobante de pago en S3 (snapshot de la pasarela)')
    link_pago           = models.URLField(max_length=1000, blank=True, default='', help_text='Link de pago (Previsora/Mundial) generado para el trámite (snapshot)')
    pago_confirmado_at  = models.DateTimeField(default=timezone.now, help_text='Sello del momento exacto en que se confirmó el pago')

    # Snapshot del 4x1000 al momento del cierre.
    # Se calcula como ((precio_lay + comision) * 4) / 1000 cuando la tarjeta tenía
    # cuatro_por_mil='1', en otro caso 0. Persistido para auditoría: si la tarjeta
    # cambia su flag más adelante, este valor permanece intacto.
    cuatro_por_mil_valor = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text='Snapshot del 4x1000 calculado al confirmar el pago')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'tramites_finalizados'
        ordering = ['-pago_confirmado_at', '-created_at']
        verbose_name = 'Trámite finalizado'
        verbose_name_plural = 'Trámites finalizados'

    def __str__(self):
        return f'Finalizado {self.id} - {self.placa or "sin placa"} - {self.cliente.nombre}'

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()


def _pdf_upload_path(instance, filename):
    """Ruta destino: media/finalizados_tramites/<finalizado_id>/<filename>."""
    fid = instance.finalizado_id or 'tmp'
    return f'finalizados_tramites/{fid}/{filename}'


class TramiteFinalizadoPdf(models.Model):
    """PDF adjunto a un trámite finalizado.

    El usuario puede subir uno o varios. La modificación pre-guardado se hace
    cliente-side; el backend solo recibe el batch final cuando el usuario
    confirma "Guardar cambios".
    """

    finalizado      = models.ForeignKey(
        TramiteFinalizado,
        on_delete=models.CASCADE,
        related_name='pdfs',
    )
    archivo         = models.FileField(upload_to=_pdf_upload_path, max_length=500)
    nombre_original = models.CharField(max_length=255, help_text='Nombre del archivo tal como lo subió el usuario')
    descripcion     = models.CharField(max_length=255, blank=True, default='', help_text='Descripción libre del documento (editable)')
    tamano_bytes    = models.BigIntegerField(default=0)
    content_type    = models.CharField(max_length=100, default='application/pdf')

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='finalizados_pdfs_uploaded',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'tramites_finalizados_pdfs'
        ordering = ['-created_at']
        verbose_name = 'PDF de trámite finalizado'
        verbose_name_plural = 'PDFs de trámites finalizados'

    def __str__(self):
        return f'PDF {self.id} - {self.nombre_original} (finalizado #{self.finalizado_id})'

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()
