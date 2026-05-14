# Generated manually to add pago_estado + pago_confirmado_at to PasarelaPago.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pasarela_de_pago', '0003_historicalpasarelapago_tarjeta_pasarelapago_tarjeta'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalpasarelapago',
            name='pago_estado',
            field=models.CharField(
                choices=[
                    ('pendiente', 'Pendiente'),
                    ('exitoso', 'Exitoso'),
                    ('no_exitoso', 'No exitoso'),
                ],
                default='pendiente',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='historicalpasarelapago',
            name='pago_confirmado_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Cuándo el operario marcó el resultado del pago',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='pasarelapago',
            name='pago_estado',
            field=models.CharField(
                choices=[
                    ('pendiente', 'Pendiente'),
                    ('exitoso', 'Exitoso'),
                    ('no_exitoso', 'No exitoso'),
                ],
                default='pendiente',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='pasarelapago',
            name='pago_confirmado_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Cuándo el operario marcó el resultado del pago',
                null=True,
            ),
        ),
    ]
