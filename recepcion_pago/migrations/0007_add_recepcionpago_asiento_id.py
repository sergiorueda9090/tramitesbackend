from django.db import migrations, models


class Migration(migrations.Migration):
    """Agrega RecepcionPago.asiento_id (UUID, nullable) para vincular cada
    recepcion de pago con el asiento contable activo en MovimientoContable.
    """

    dependencies = [
        ('recepcion_pago', '0006_remove_recepcionpago_sub_cuenta_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='recepcionpago',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AddField(
            model_name='historicalrecepcionpago',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
    ]
