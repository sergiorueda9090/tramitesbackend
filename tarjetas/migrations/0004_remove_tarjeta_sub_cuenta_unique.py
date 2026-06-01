from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Quita unique=True de Tarjeta.sub_cuenta y sincroniza help_text."""

    dependencies = [
        ('tarjetas', '0003_add_debito_credito_sub_cuenta'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tarjeta',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='tarjetas',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable asociada a la tarjeta',
            ),
        ),
        migrations.AlterField(
            model_name='historicaltarjeta',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable asociada a la tarjeta',
            ),
        ),
    ]
