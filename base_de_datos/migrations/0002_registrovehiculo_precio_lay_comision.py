# Generated manually para añadir campos precio_lay y comision a RegistroVehiculo
# (y su modelo histórico). Estos campos los completa el Cotizador desde Step7
# cuando la tarifa se resolvió sin anomalías.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base_de_datos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='registrovehiculo',
            name='precio_lay',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='registrovehiculo',
            name='comision',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='historicalregistrovehiculo',
            name='precio_lay',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='historicalregistrovehiculo',
            name='comision',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
