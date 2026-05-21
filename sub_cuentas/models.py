from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from simple_history.models import HistoricalRecords

from plan_de_cuentas.models import PlanDeCuentas


class SubCuenta(models.Model):
    codigo = models.CharField(
        max_length=6,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[A-Z]{3}\d{3}$',
                message='El ID debe ser 3 letras mayúsculas seguidas de 3 dígitos (ej: ABC123).'
            )
        ],
        help_text='ID manual único: 3 letras mayúsculas + 3 dígitos (ej: ABC123)'
    )
    cuenta = models.ForeignKey(
        PlanDeCuentas,
        on_delete=models.PROTECT,
        related_name='sub_cuentas',
        help_text='Cuenta del PUC asociada (Plan de cuentas)'
    )
    nombre_sub_cuenta = models.CharField(
        max_length=200,
        help_text='Nombre alfanumérico de la sub-cuenta (ej: BANCOLCP)'
    )

    debito    = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                    help_text='Movimiento débito')
    credito   = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                    help_text='Movimiento crédito')
    acumulado = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                    help_text='Saldo acumulado de la sub-cuenta')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sub_cuentas_creadas',
        help_text='Usuario que creó el registro'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'sub_cuentas'
        ordering = ['codigo']
        verbose_name = 'Sub-cuenta'
        verbose_name_plural = 'Sub-cuentas'

    def __str__(self):
        return f'{self.codigo} - {self.nombre_sub_cuenta}'

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
