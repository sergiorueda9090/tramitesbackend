from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Reemplaza precio_lay/comision por codigo_tarifa (FK a TarifarioSoat).

    La tabla precios_clientes fue truncada en una fase previa (junto con su
    historica), asi que el FK NOT NULL puede aplicarse directamente.
    """

    dependencies = [
        ('clientes', '0005_add_sub_cuenta'),
        ('tarifario_soat', '0001_initial'),
    ]

    operations = [
        # 1) Eliminar campos viejos en PrecioCliente
        migrations.RemoveField(
            model_name='preciocliente',
            name='precio_lay',
        ),
        migrations.RemoveField(
            model_name='preciocliente',
            name='comision',
        ),
        # 2) Eliminar campos viejos en HistoricalPrecioCliente
        migrations.RemoveField(
            model_name='historicalpreciocliente',
            name='precio_lay',
        ),
        migrations.RemoveField(
            model_name='historicalpreciocliente',
            name='comision',
        ),
        # 3) Agregar codigo_tarifa en PrecioCliente (NOT NULL, tabla vacia)
        migrations.AddField(
            model_name='preciocliente',
            name='codigo_tarifa',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='precios_clientes',
                to='tarifario_soat.tarifariosoat',
                help_text='Codigo de tarifa del Tarifario SOAT',
            ),
        ),
        # 4) Agregar codigo_tarifa en HistoricalPrecioCliente (siempre nullable, sin FK constraint)
        migrations.AddField(
            model_name='historicalpreciocliente',
            name='codigo_tarifa',
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+',
                to='tarifario_soat.tarifariosoat',
                help_text='Codigo de tarifa del Tarifario SOAT',
            ),
        ),
    ]
