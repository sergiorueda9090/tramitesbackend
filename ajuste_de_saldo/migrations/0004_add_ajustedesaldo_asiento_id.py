from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega AjusteDeSaldo.asiento_id y sincroniza help_text de sub_cuenta.

    La direccion del asiento (D/C) se determina por los campos `debito` y
    `credito` del payload:
      - debito  > 0 → D=cliente.sub_cuenta, C=ajuste.sub_cuenta, valor=debito.
      - credito > 0 → D=ajuste.sub_cuenta,  C=cliente.sub_cuenta, valor=credito.
    """

    dependencies = [
        ('ajuste_de_saldo', '0003_remove_ajustedesaldo_sub_cuenta_unique'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ajustedesaldo',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AddField(
            model_name='historicalajustedesaldo',
            name='asiento_id',
            field=models.UUIDField(
                blank=True, null=True, default=None, editable=False,
                help_text='UUID del asiento contable activo en MovimientoContable (null si aun no se registro o fue revertido)',
            ),
        ),
        migrations.AlterField(
            model_name='ajustedesaldo',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='ajustes_de_saldo',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contraparte del ajuste (la otra es la del cliente)',
            ),
        ),
        migrations.AlterField(
            model_name='historicalajustedesaldo',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contraparte del ajuste (la otra es la del cliente)',
            ),
        ),
    ]
