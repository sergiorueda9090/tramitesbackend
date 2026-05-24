from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega debito, credito y sub_cuenta (FK obligatoria UNIQUE) a Tarjeta.

    Estrategia: AddField nullable -> AlterField NOT NULL+UNIQUE en la misma migracion.
    Si la tabla `tarjetas` tiene filas, el AlterField fallara con IntegrityError.
    En ese caso: TRUNCATE TABLE tarjetas (y sus historicas) o backfill manual.
    """

    dependencies = [
        ('tarjetas', '0002_historicaltarjeta_usuario_tarjeta_usuario'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tarjeta',
            name='debito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento débito', max_digits=15),
        ),
        migrations.AddField(
            model_name='tarjeta',
            name='credito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento crédito', max_digits=15),
        ),
        migrations.AddField(
            model_name='tarjeta',
            name='sub_cuenta',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='tarjetas', to='sub_cuentas.subcuenta', help_text='Sub-cuenta contable asociada (obligatoria y unica por tarjeta)'),
        ),
        migrations.AlterField(
            model_name='tarjeta',
            name='sub_cuenta',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tarjetas', to='sub_cuentas.subcuenta', unique=True, help_text='Sub-cuenta contable asociada (obligatoria y unica por tarjeta)'),
        ),
        # Historical (siempre nullable, sin FK)
        migrations.AddField(
            model_name='historicaltarjeta',
            name='debito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento débito', max_digits=15),
        ),
        migrations.AddField(
            model_name='historicaltarjeta',
            name='credito',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Movimiento crédito', max_digits=15),
        ),
        migrations.AddField(
            model_name='historicaltarjeta',
            name='sub_cuenta',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='sub_cuentas.subcuenta', help_text='Sub-cuenta contable asociada (obligatoria y unica por tarjeta)'),
        ),
    ]
