from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega GastoRelacion.asiento_id y sincroniza help_text de sub_cuenta.

    Asiento: D=gasto_categoria.sub_cuenta (cuenta de gasto del PUC),
              C=gasto_relacion.sub_cuenta (medio de pago).
    """

    dependencies = [
        ('gastos', '0005_remove_gastorelacion_sub_cuenta_unique'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='gastorelacion',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AddField(
            model_name='historicalgastorelacion',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AlterField(
            model_name='gastorelacion',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='gasto_relaciones',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de credito (medio de pago) asociada al registro',
            ),
        ),
        migrations.AlterField(
            model_name='historicalgastorelacion',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de credito (medio de pago) asociada al registro',
            ),
        ),
    ]
