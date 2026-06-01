from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega Utilidad.asiento_id y vuelve sub_cuenta nullable.

    Razon: la signal post_save de TramiteFinalizado crea la Utilidad
    automaticamente; si la setting UTILIDADES_SUB_CUENTA_CODIGO no esta
    configurada (o la sub-cuenta no existe), la Utilidad se crea sin
    sub_cuenta y sin asiento, para que el backfill la procese despues.

    El asiento se registra como D=tarjeta.sub_cuenta (banco), C=utilidad.sub_cuenta
    (ingreso), valor=comision.
    """

    dependencies = [
        ('utilidades', '0003_remove_utilidad_sub_cuenta_unique'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilidad',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AddField(
            model_name='historicalutilidad',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AlterField(
            model_name='utilidad',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='utilidades',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de credito (ingreso por utilidad). Puede quedar null si no esta configurada UTILIDADES_SUB_CUENTA_CODIGO',
            ),
        ),
        migrations.AlterField(
            model_name='historicalutilidad',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable de credito (ingreso por utilidad). Puede quedar null si no esta configurada UTILIDADES_SUB_CUENTA_CODIGO',
            ),
        ),
    ]
