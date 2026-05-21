from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from simple_history.models import HistoricalRecords


class TipoCuenta(models.TextChoices):
    ACTIVO     = 'activo',     'Activo'
    PASIVO     = 'pasivo',     'Pasivo'
    PATRIMONIO = 'patrimonio', 'Patrimonio'
    INGRESO    = 'ingreso',    'Ingreso'
    GASTO      = 'gasto',      'Gasto'


class AcumuladoTipo(models.TextChoices):
    DEBITO_CREDITO = 'debito_credito', 'Débito (-) Crédito'
    CREDITO_DEBITO = 'credito_debito', 'Crédito (-) Débito'


# Naturaleza contable: la columna 'acumulado' se deriva siempre del 'tipo'.
# Activo y Gasto acumulan saldo débito; Pasivo, Patrimonio e Ingreso acumulan saldo crédito.
ACUMULADO_POR_TIPO = {
    TipoCuenta.ACTIVO:     AcumuladoTipo.DEBITO_CREDITO,
    TipoCuenta.PASIVO:     AcumuladoTipo.CREDITO_DEBITO,
    TipoCuenta.PATRIMONIO: AcumuladoTipo.CREDITO_DEBITO,
    TipoCuenta.INGRESO:    AcumuladoTipo.CREDITO_DEBITO,
    TipoCuenta.GASTO:      AcumuladoTipo.DEBITO_CREDITO,
}


class PlanDeCuentas(models.Model):
    tipo = models.CharField(
        max_length=20,
        choices=TipoCuenta.choices,
        help_text='Tipo de cuenta contable'
    )
    codigo_puc = models.CharField(
        max_length=4,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^\d{4}$',
                message='El Código PUC debe ser numérico de 4 dígitos.'
            )
        ],
        help_text='Código PUC numérico de 4 dígitos (único, ingreso manual)'
    )
    nombre_cuenta = models.CharField(
        max_length=200,
        help_text='Nombre alfanumérico de la cuenta'
    )
    acumulado = models.CharField(
        max_length=20,
        choices=AcumuladoTipo.choices,
        help_text='Naturaleza acumulada de la cuenta'
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='plan_de_cuentas_creadas',
        help_text='Usuario que creó el registro'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'plan_de_cuentas'
        ordering = ['codigo_puc']
        verbose_name = 'Cuenta del PUC'
        verbose_name_plural = 'Plan de cuentas'

    def __str__(self):
        return f'{self.codigo_puc} - {self.nombre_cuenta}'

    def save(self, *args, **kwargs):
        # 'acumulado' se deriva del 'tipo'. Forzamos la regla antes de persistir
        # para que admin, API, shell y migraciones queden todos consistentes.
        if self.tipo in ACUMULADO_POR_TIPO:
            self.acumulado = ACUMULADO_POR_TIPO[self.tipo]
        super().save(*args, **kwargs)

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
