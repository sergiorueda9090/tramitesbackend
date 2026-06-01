from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Sincroniza el help_text de Devolucion.sub_cuenta despues de invertir
    la direccion del asiento contable. La sub-cuenta del registro ahora
    representa el CREDITO (caja/banco) en el asiento; el DEBITO va contra
    `cliente.sub_cuenta` (cuenta por cobrar).

    Solo cambia metadata (help_text); no hay cambio de esquema en la BD.
    """

    dependencies = [
        ('devoluciones', '0006_add_devolucion_asiento_id'),
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
                help_text='Sub-cuenta contable de credito (caja/banco) asociada al registro',
            ),
        ),
        migrations.AlterField(
            model_name='historicaldevolucion',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de credito (caja/banco) asociada al registro',
            ),
        ),
    ]
