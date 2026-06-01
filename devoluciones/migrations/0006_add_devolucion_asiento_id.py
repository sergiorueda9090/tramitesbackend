from django.db import migrations, models


class Migration(migrations.Migration):
    """Agrega Devolucion.asiento_id (UUID, nullable) para vincular cada
    devolucion con el asiento contable activo en MovimientoContable.
    """

    dependencies = [
        ('devoluciones', '0005_alter_historicaldevolucion_sub_cuenta'),
    ]

    operations = [
        migrations.AddField(
            model_name='devolucion',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AddField(
            model_name='historicaldevolucion',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
    ]
