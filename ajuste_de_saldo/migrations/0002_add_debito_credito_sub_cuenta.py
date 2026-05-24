from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega debito, credito y sub_cuenta (FK obligatoria UNIQUE) a AjusteDeSaldo."""

    dependencies = [
        ('ajuste_de_saldo', '0001_initial'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ajustedesaldo',
            name='debito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento débito', max_digits=15),
        ),
        migrations.AddField(
            model_name='ajustedesaldo',
            name='credito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento crédito', max_digits=15),
        ),
        migrations.AddField(
            model_name='ajustedesaldo',
            name='sub_cuenta',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ajustes_de_saldo', to='sub_cuentas.subcuenta', help_text='Sub-cuenta contable asociada (obligatoria y unica por registro)'),
        ),
        migrations.AlterField(
            model_name='ajustedesaldo',
            name='sub_cuenta',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='ajustes_de_saldo', to='sub_cuentas.subcuenta', unique=True, help_text='Sub-cuenta contable asociada (obligatoria y unica por registro)'),
        ),
        migrations.AddField(
            model_name='historicalajustedesaldo',
            name='debito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento débito', max_digits=15),
        ),
        migrations.AddField(
            model_name='historicalajustedesaldo',
            name='credito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento crédito', max_digits=15),
        ),
        migrations.AddField(
            model_name='historicalajustedesaldo',
            name='sub_cuenta',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='sub_cuentas.subcuenta', help_text='Sub-cuenta contable asociada (obligatoria y unica por registro)'),
        ),
    ]
