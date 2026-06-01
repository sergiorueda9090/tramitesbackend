import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from simple_history.models import HistoricalRecords

from sub_cuentas.models import SubCuenta


class TipoMovimiento(models.TextChoices):
    DEBITO  = 'debito',  'Debito'
    CREDITO = 'credito', 'Credito'


class MovimientoContable(models.Model):
    """Libro mayor: cada evento contable se materializa como dos filas
    (un debito y un credito) compartiendo el mismo `asiento_id`.

    No exponemos create/update/delete via API publica: el libro solo se
    modifica desde el servicio `registrar_asiento` / `revertir_asiento`
    invocado por los modulos de origen (devoluciones, recepcion_pago, ...).
    """

    asiento_id      = models.UUIDField(default=uuid.uuid4, editable=False,
                                       help_text='Agrupa el debito y el credito de un mismo evento')
    sub_cuenta      = models.ForeignKey(
        SubCuenta,
        on_delete=models.PROTECT,
        related_name='movimientos',
        help_text='Sub-cuenta sobre la que aplica el movimiento'
    )
    tipo_movimiento = models.CharField(max_length=10, choices=TipoMovimiento.choices)
    valor           = models.DecimalField(
        max_digits=15, decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Valor positivo. El signo se deriva del tipo_movimiento y de cuenta.tipo'
    )
    fecha           = models.DateTimeField(help_text='Fecha contable del movimiento')

    modulo_origen   = models.CharField(
        max_length=40,
        help_text="Nombre de la app que origino el movimiento (ej: 'devoluciones')"
    )
    origen_id       = models.PositiveIntegerField(
        help_text='PK del registro origen dentro de su tabla'
    )

    descripcion     = models.TextField(blank=True)

    usuario         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='movimientos_contables',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'movimiento_contable'
        ordering = ['-fecha', '-id']
        verbose_name = 'Movimiento contable'
        verbose_name_plural = 'Movimientos contables'
        indexes = [
            models.Index(fields=['sub_cuenta', 'fecha']),
            models.Index(fields=['modulo_origen', 'origen_id']),
            models.Index(fields=['asiento_id']),
        ]

    def __str__(self):
        return f'{self.tipo_movimiento.upper()} {self.valor} en {self.sub_cuenta_id} ({self.modulo_origen}#{self.origen_id})'

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
