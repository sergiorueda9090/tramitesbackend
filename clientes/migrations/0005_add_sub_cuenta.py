from django.db import migrations, models
import django.db.models.deletion


def backfill_sub_cuenta(apps, schema_editor):
    """Asigna la primera SubCuenta activa a los clientes con sub_cuenta NULL.

    Necesario antes del AlterField NOT NULL. Si no hay sub-cuentas activas, la
    migracion falla aqui (no puede continuar sin un valor por defecto).
    """
    Cliente = apps.get_model('clientes', 'Cliente')
    SubCuenta = apps.get_model('sub_cuentas', 'SubCuenta')

    if not Cliente.objects.filter(sub_cuenta__isnull=True).exists():
        return  # nada que backfillear

    primera = SubCuenta.objects.filter(deleted_at__isnull=True).order_by('pk').first()
    if not primera:
        raise RuntimeError(
            'No hay sub-cuentas activas para backfillear clientes existentes. '
            'Crea al menos una SubCuenta y vuelve a correr la migracion.'
        )
    Cliente.objects.filter(sub_cuenta__isnull=True).update(sub_cuenta=primera)


def reverse_backfill(apps, schema_editor):
    # No-op: no podemos saber el estado previo
    pass


class Migration(migrations.Migration):
    """Agrega sub_cuenta (FK obligatoria, no unique) a Cliente.

    Estrategia: AddField nullable -> RunPython backfill -> AlterField NOT NULL.
    """

    dependencies = [
        ('clientes', '0004_cliente_email_historicalcliente_email'),
        ('sub_cuentas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='sub_cuenta',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='clientes',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable asociada al cliente (obligatoria)',
            ),
        ),
        migrations.RunPython(backfill_sub_cuenta, reverse_backfill),
        migrations.AlterField(
            model_name='cliente',
            name='sub_cuenta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='clientes',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable asociada al cliente (obligatoria)',
            ),
        ),
        # Tabla historica (siempre nullable, sin FK constraint)
        migrations.AddField(
            model_name='historicalcliente',
            name='sub_cuenta',
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+',
                to='sub_cuentas.subcuenta',
                help_text='Sub-cuenta contable asociada al cliente (obligatoria)',
            ),
        ),
    ]
