from django.db import models
from django.conf import settings
from tarjetas.models import Tarjeta
from sub_cuentas.models import SubCuenta
from simple_history.models import HistoricalRecords
import uuid


class TipoUtilidad(models.TextChoices):
    GANANCIA = 'ganancia', 'Ganancia'
    PERDIDA  = 'perdida',  'Pérdida'


class UtilidadOcasional(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='utilidades_ocasionales'
    )

    tarjeta = models.ForeignKey(
        Tarjeta,
        on_delete=models.CASCADE,
        related_name='utilidades_ocasionales'
    )

    # El valor SIEMPRE se almacena positivo (magnitud). `tipo` indica si la
    # utilidad es ganancia o perdida (antes se inferia del signo del valor).
    tipo = models.CharField(
        max_length=10,
        choices=TipoUtilidad.choices,
        default=TipoUtilidad.GANANCIA,
        help_text='Ganancia o perdida; define la sub-cuenta y la direccion del asiento.'
    )
    valor           = models.DecimalField(max_digits=10, decimal_places=2)
    observacion     = models.TextField(blank=True, null=True)
    fecha           = models.DateTimeField()

    cuatro_por_mil = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total          = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    debito  = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento débito')
    credito = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Movimiento crédito')
    sub_cuenta = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        related_name='utilidad_ocasional_registros',
        help_text='Sub-cuenta contable de credito (ingreso) asociada al registro'
    )

    asiento_id = models.UUIDField(
        null=True, blank=True, default=None, editable=False,
        help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'utilidad_ocasional'
        ordering = ['-created_at']
        verbose_name = 'Utilidad Ocasional'
        verbose_name_plural = 'Utilidades Ocasionales'

    def __str__(self):
        return f'UtilidadOcasional {self.id} - Tarjeta: {self.tarjeta} - Valor: {self.valor}'

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


class UtilidadOcasionalConfig(models.Model):
    """Configuracion global (singleton) de las sub-cuentas contracuenta usadas
    por Utilidad Ocasional segun el signo del valor:
      - sub_cuenta_positiva: contracuenta (ingreso) cuando el valor es > 0 (ganancia).
      - sub_cuenta_negativa: contracuenta cuando el valor es < 0 (perdida).
    Solo existe un registro (pk=1); se obtiene/crea con `load()`.
    """
    sub_cuenta_positiva = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='utilidad_ocasional_config_positiva',
        help_text='Sub-cuenta contracuenta para utilidades con valor positivo (ganancia).'
    )
    sub_cuenta_negativa = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='utilidad_ocasional_config_negativa',
        help_text='Sub-cuenta contracuenta para utilidades con valor negativo (perdida).'
    )

    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'utilidad_ocasional_config'
        verbose_name = 'Configuracion Utilidad Ocasional'
        verbose_name_plural = 'Configuracion Utilidad Ocasional'

    def __str__(self):
        return 'Configuracion Utilidad Ocasional'

    def save(self, *args, **kwargs):
        # Forzar singleton: siempre pk=1.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
