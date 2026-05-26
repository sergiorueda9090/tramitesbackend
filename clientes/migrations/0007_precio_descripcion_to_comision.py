from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    """Reemplaza descripcion por comision en PrecioCliente.

    La descripcion deja de capturarse (el codigo_tarifa ya aporta su propia
    descripcion); en su lugar el cliente agrega una comision (COP).
    comision es NOT NULL: se aplica default 0 a filas existentes, pero el
    modelo no conserva default (lo exige la capa de vistas en cada alta).
    """

    dependencies = [
        ('clientes', '0006_precio_codigo_tarifa'),
    ]

    operations = [
        # 1) Eliminar descripcion (modelo + historico)
        migrations.RemoveField(
            model_name='preciocliente',
            name='descripcion',
        ),
        migrations.RemoveField(
            model_name='historicalpreciocliente',
            name='descripcion',
        ),
        # 2) Agregar comision en PrecioCliente (NOT NULL; default temporal para filas existentes)
        migrations.AddField(
            model_name='preciocliente',
            name='comision',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                default=Decimal('0'),
                help_text='Comision (COP) que agrega el cliente para esta tarifa',
            ),
            preserve_default=False,
        ),
        # 3) Agregar comision en HistoricalPrecioCliente
        migrations.AddField(
            model_name='historicalpreciocliente',
            name='comision',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                default=Decimal('0'),
                help_text='Comision (COP) que agrega el cliente para esta tarifa',
            ),
            preserve_default=False,
        ),
    ]
