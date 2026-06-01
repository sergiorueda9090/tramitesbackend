from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega UtilidadOcasional.asiento_id y sincroniza help_text de sub_cuenta.

    Asiento: D=tarjeta.sub_cuenta (banco sube), C=utilidad.sub_cuenta (ingreso).
    """

    dependencies = [
        ('utilidad_ocasional', '0003_remove_utilidadocasional_sub_cuenta_unique'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilidadocasional',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AddField(
            model_name='historicalutilidadocasional',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AlterField(
            model_name='utilidadocasional',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='utilidad_ocasional_registros',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de credito (ingreso) asociada al registro',
            ),
        ),
        migrations.AlterField(
            model_name='historicalutilidadocasional',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de credito (ingreso) asociada al registro',
            ),
        ),
    ]
