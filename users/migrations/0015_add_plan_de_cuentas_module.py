from django.db import migrations


MODULES = [
    ('Plan de cuentas', 'plan_de_cuentas'),
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
        ('users', '0014_add_computador_ips_module'),
    ]

    operations = [
        migrations.RunPython(populate_modules, reverse_populate),
    ]
