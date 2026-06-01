from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Quita unique=True de Devolucion.sub_cuenta.

    Justificacion: la misma sub-cuenta acumula multiples movimientos contables
    a lo largo del tiempo. La restriccion UNIQUE introducida en 0003 impedia
    que dos devoluciones compartieran sub-cuenta, lo cual es incompatible con
    el libro mayor (MovimientoContable) que se introduce a continuacion.
    """

    dependencies = [
        ('devoluciones', '0003_add_debito_credito_sub_cuenta'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='devolucion',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='devoluciones',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de debito asociada al registro',
            ),
        ),
    ]
