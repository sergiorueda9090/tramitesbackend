from django.db import models
from django.conf import settings
from tarjetas.models import Tarjeta
from sub_cuentas.models import SubCuenta
from simple_history.models import HistoricalRecords


class ModuloOrigen(models.TextChoices):
    RECEPCION_PAGO        = 'recepcion_pago',        'Recepción de pagos'
    DEVOLUCIONES          = 'devoluciones',          'Devoluciones'
    GASTOS                = 'gastos',                'Gastos'
    CARGOS_NO_REGISTRADOS = 'cargos_no_registrados', 'Cargos no registrados'
    UTILIDAD_OCASIONAL    = 'utilidad_ocasional',    'Utilidad ocasional'
    PASARELA_DE_PAGO      = 'pasarela_de_pago',      'Pasarela de pago'
    FINALIZADOS_TRAMITES  = 'finalizados_tramites',  'Trámites finalizados'


class CuatroPorMil(models.Model):
    modulo = models.CharField(
        max_length=50,
        choices=ModuloOrigen.choices,
        help_text='Módulo origen del 4x1000'
    )
    registro_id = models.PositiveIntegerField(
        help_text='ID del registro en el módulo origen'
    )

    valor      = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                     help_text='Valor del 4x1000')
    valor_base = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                     help_text='Valor base sobre el que se calculó')

    tarjeta = models.ForeignKey(
        Tarjeta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cuatro_por_mil_registros',
        help_text='Tarjeta asociada (cuando aplique)'
    )

    observacion = models.TextField(blank=True, null=True)
    fecha       = models.DateTimeField(null=True, blank=True,
                                       help_text='Fecha de la transacción origen')

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='cuatro_por_mil_registros',
        help_text='Usuario que registró el 4x1000'
    )

    debito  = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento débito')
    credito = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento crédito')
    sub_cuenta = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        unique=True,
        related_name='cuatro_por_mil_registros',
        help_text='Sub-cuenta contable asociada (obligatoria y unica por registro)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'cuatro_por_mil'
        ordering = ['-created_at']
        verbose_name = 'Cuatro por mil'
        verbose_name_plural = 'Cuatros por mil'
        indexes = [
            models.Index(fields=['modulo', 'registro_id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['modulo', 'registro_id'],
                name='uniq_cuatro_por_mil_origen',
            ),
        ]

    def __str__(self):
        return f'{self.modulo}#{self.registro_id} - {self.valor}'

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
