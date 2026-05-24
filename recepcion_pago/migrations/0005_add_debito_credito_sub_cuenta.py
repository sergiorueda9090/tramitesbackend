from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega debito, credito y sub_cuenta (FK obligatoria UNIQUE) a RecepcionPago.

    Estrategia: AddField nullable -> AlterField NOT NULL+UNIQUE en la misma migracion.
    Si la tabla tiene filas, el AlterField fallara. En ese caso: TRUNCATE TABLE recepciones_pago;
    """

    dependencies = [
        ('recepcion_pago', '0004_historicalrecepcionpago_cuatro_por_mil_and_more'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='recepcionpago',
            name='debito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento débito', max_digits=15),
        ),
        migrations.AddField(
            model_name='recepcionpago',
            name='credito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento crédito', max_digits=15),
        ),
        migrations.AddField(
            model_name='recepcionpago',
            name='sub_cuenta',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='recepciones_pago', to='sub_cuentas.subcuenta', help_text='Sub-cuenta contable asociada (obligatoria y unica por registro)'),
        ),
        migrations.AlterField(
            model_name='recepcionpago',
            name='sub_cuenta',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='recepciones_pago', to='sub_cuentas.subcuenta', unique=True, help_text='Sub-cuenta contable asociada (obligatoria y unica por registro)'),
        ),
        # Historical (siempre nullable, sin FK constraint)
        migrations.AddField(
            model_name='historicalrecepcionpago',
            name='debito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento débito', max_digits=15),
        ),
        migrations.AddField(
            model_name='historicalrecepcionpago',
            name='credito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento crédito', max_digits=15),
        ),
        migrations.AddField(
            model_name='historicalrecepcionpago',
            name='sub_cuenta',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='sub_cuentas.subcuenta', help_text='Sub-cuenta contable asociada (obligatoria y unica por registro)'),
        ),
    ]
