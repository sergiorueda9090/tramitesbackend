"""Normaliza los registros existentes al nuevo esquema:
- `tipo` = 'perdida' si el valor era negativo, si no 'ganancia'.
- `valor`, `debito`, `credito`, `total` pasan a su magnitud positiva.

No toca los asientos contables ya posteados (su direccion se fijo al registrarlos).
"""

from django.db import migrations


def normalizar(apps, schema_editor):
    UtilidadOcasional = apps.get_model('utilidad_ocasional', 'UtilidadOcasional')
    for u in UtilidadOcasional.objects.all():
        u.tipo = 'perdida' if (u.valor is not None and u.valor < 0) else 'ganancia'
        if u.valor is not None:
            u.valor = abs(u.valor)
        if u.debito is not None:
            u.debito = abs(u.debito)
        if u.credito is not None:
            u.credito = abs(u.credito)
        if u.total is not None:
            u.total = abs(u.total)
        u.save(update_fields=['tipo', 'valor', 'debito', 'credito', 'total'])


def revertir(apps, schema_editor):
    # Irreversible de forma segura: se deja el dato normalizado.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('utilidad_ocasional', '0006_historicalutilidadocasional_tipo_and_more'),
    ]

    operations = [
        migrations.RunPython(normalizar, revertir),
    ]
