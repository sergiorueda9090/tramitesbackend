from django.db import migrations


class Migration(migrations.Migration):
    """Elimina el campo `etiqueta` de Proveedor.

    La columna `etiqueta_id` desaparece de la tabla principal y de la historica.
    Es un cambio destructivo: cualquier dato en esa columna se pierde.
    """

    dependencies = [
        ('proveedores', '0002_add_sub_cuenta'),
        ('etiquetas', '0002_rename_created_by_etiqueta_user_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='proveedor',
            name='etiqueta',
        ),
        migrations.RemoveField(
            model_name='historicalproveedor',
            name='etiqueta',
        ),
    ]
