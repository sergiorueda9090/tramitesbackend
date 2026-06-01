from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega CargoNoRegistrado.asiento_id (UUID) y sincroniza help_text de sub_cuenta.

    El asiento se registra como D=cliente.sub_cuenta (deuda sube), C=cargo.sub_cuenta.
    """

    dependencies = [
        ('cargos_no_registrados', '0004_remove_cargonoregistrado_sub_cuenta_unique'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cargonoregistrado',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AddField(
            model_name='historicalcargonoregistrado',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AlterField(
            model_name='cargonoregistrado',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='cargos_no_registrados',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de credito (contraparte del cargo) asociada al registro',
            ),
        ),
        migrations.AlterField(
            model_name='historicalcargonoregistrado',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de credito (contraparte del cargo) asociada al registro',
            ),
        ),
    ]
