from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega la FK obligatoria `sub_cuenta` a Proveedor.

    Estrategia: AddField nullable -> AlterField NOT NULL en la misma migracion.
    Si la tabla `proveedores` tiene filas sin backfill, el segundo paso fallara
    con IntegrityError. En ese caso: TRUNCATE TABLE proveedores; (o backfill manual).
    """

    dependencies = [
        ('proveedores', '0001_initial'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        # 1) Agregar columna como nullable para que la migracion corra aunque haya filas.
        migrations.AddField(
            model_name='proveedor',
            name='sub_cuenta',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='proveedores',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable asociada al proveedor (obligatoria)',
            ),
        ),
        # 2) Promover a NOT NULL (fallara si hay filas con sub_cuenta=NULL).
        migrations.AlterField(
            model_name='proveedor',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='proveedores',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable asociada al proveedor (obligatoria)',
            ),
        ),
        # 3) Misma columna en la tabla historica (simple_history). Siempre nullable
        #    a nivel de tabla historica, sin FK constraint.
        migrations.AddField(
            model_name='historicalproveedor',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable asociada al proveedor (obligatoria)',
            ),
        ),
    ]
