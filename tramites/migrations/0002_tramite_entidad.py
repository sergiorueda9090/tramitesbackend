# Generated manually para añadir el campo `entidad` a Tramite (y su modelo
# histórico). La entidad depende del tipo_vehiculo:
#   USADO   → MUNDIAL (default) / PREVISORA / MANUAL
#   CERO_KM → PREVISORA (default) / SOLIDARIA / MANUAL

from django.db import migrations, models


ENTIDAD_CHOICES = [
    ('MUNDIAL', 'Mundial'),
    ('PREVISORA', 'Previsora'),
    ('SOLIDARIA', 'Solidaria'),
    ('MANUAL', 'Manual'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('tramites', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tramite',
            name='entidad',
            field=models.CharField(blank=True, choices=ENTIDAD_CHOICES, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='historicaltramite',
            name='entidad',
            field=models.CharField(blank=True, choices=ENTIDAD_CHOICES, default='', max_length=20),
        ),
    ]
