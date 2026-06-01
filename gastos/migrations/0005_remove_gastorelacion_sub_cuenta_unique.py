from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Quita unique=True de GastoRelacion.sub_cuenta y sincroniza help_text."""

    dependencies = [
        ('gastos', '0004_alter_historicalgastorelacion_gasto'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gastorelacion',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='gasto_relaciones',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de debito asociada al registro',
            ),
        ),
        migrations.AlterField(
            model_name='historicalgastorelacion',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de debito asociada al registro',
            ),
        ),
    ]
