from django.db import migrations


MODULES = [
    ('Trámites finalizados', 'finalizados_tramites'),
]


def populate_modules(apps, schema_editor):
    Module = apps.get_model('users', 'Module')
    for name, code in MODULES:
        Module.objects.get_or_create(code=code, defaults={'name': name})


def reverse_populate(apps, schema_editor):
    Module = apps.get_model('users', 'Module')
    codes = [code for _, code in MODULES]
    Module.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_add_pasarela_de_pago_module'),
    ]

    operations = [
        migrations.RunPython(populate_modules, reverse_populate),
    ]
