from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Quita unique=True de CargoNoRegistrado.sub_cuenta y sincroniza help_text."""

    dependencies = [
        ('cargos_no_registrados', '0003_add_debito_credito_sub_cuenta'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cargonoregistrado',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='cargos_no_registrados',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de debito asociada al registro',
            ),
        ),
        migrations.AlterField(
            model_name='historicalcargonoregistrado',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de debito asociada al registro',
            ),
        ),
    ]
