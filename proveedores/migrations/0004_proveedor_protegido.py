from django.db import migrations, models


def marcar_protegidos(apps, schema_editor):
    """Marca como protegidos los proveedores del sistema PREVISORA y MUNDIAL.

    Estos dos registros son los únicos con generador de link de pago e
    integración contable; no deben poder editarse ni eliminarse desde el módulo.
    """
    Proveedor = apps.get_model('proveedores', 'Proveedor')
    Proveedor.objects.filter(nombre__iexact='PREVISORA').update(protegido=True)
    Proveedor.objects.filter(nombre__iexact='MUNDIAL').update(protegido=True)


def desmarcar_protegidos(apps, schema_editor):
    Proveedor = apps.get_model('proveedores', 'Proveedor')
    Proveedor.objects.filter(nombre__iexact='PREVISORA').update(protegido=False)
    Proveedor.objects.filter(nombre__iexact='MUNDIAL').update(protegido=False)


class Migration(migrations.Migration):

    dependencies = [
        ('proveedores', '0003_remove_etiqueta'),
    ]

    operations = [
        migrations.AddField(
            model_name='proveedor',
            name='protegido',
            field=models.BooleanField(
                default=False,
                help_text='Proveedor del sistema (PREVISORA/MUNDIAL): no se puede editar ni eliminar',
            ),
        ),
        migrations.AddField(
            model_name='historicalproveedor',
            name='protegido',
            field=models.BooleanField(
                default=False,
                help_text='Proveedor del sistema (PREVISORA/MUNDIAL): no se puede editar ni eliminar',
            ),
        ),
        migrations.RunPython(marcar_protegidos, desmarcar_protegidos),
    ]
