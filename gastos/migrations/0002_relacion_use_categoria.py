from django.db import migrations, models
import django.db.models.deletion


def copy_gastos_to_categorias(apps, schema_editor):
    """Copia rows de Gasto (legacy) a GastoCategoria preservando IDs.

    Idempotente: si ya existe un GastoCategoria con el mismo ID, se respeta.
    Esto garantiza integridad referencial cuando luego cambiamos el FK de
    GastoRelacion.gasto: las filas que apuntaban a `Gasto.id` seguirán
    apuntando válidamente a `GastoCategoria.id`.
    """
    Gasto = apps.get_model('gastos', 'Gasto')
    GastoCategoria = apps.get_model('gastos_categoria', 'GastoCategoria')

    for g in Gasto.objects.all():
        if GastoCategoria.objects.filter(pk=g.pk).exists():
            continue
        GastoCategoria.objects.create(
            pk=g.pk,
            nombre=g.nombre,
            descripcion=g.descripcion or '',
            user_id=g.user_id,
            created_at=g.created_at,
            updated_at=g.updated_at,
            deleted_at=g.deleted_at,
        )


def reverse_noop(apps, schema_editor):
    # No revertimos los datos. La migración estructural sí se revierte
    # automáticamente por la AlterField inversa de Django.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('gastos', '0001_initial'),
        ('gastos_categoria', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(copy_gastos_to_categorias, reverse_noop),
        migrations.AlterField(
            model_name='gastorelacion',
            name='gasto',
            field=models.ForeignKey(
                to='gastos_categoria.gastocategoria',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='gasto_relaciones',
                help_text='Categoría asociada al gasto',
            ),
        ),
        migrations.AlterField(
            model_name='historicalgastorelacion',
            name='gasto',
            field=models.ForeignKey(
                to='gastos_categoria.gastocategoria',
                on_delete=django.db.models.deletion.DO_NOTHING,
                blank=True,
                null=True,
                db_constraint=False,
                related_name='+',
            ),
        ),
    ]
