import uuid

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('sub_cuentas', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MovimientoContable',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asiento_id', models.UUIDField(default=uuid.uuid4, editable=False, help_text='Agrupa el debito y el credito de un mismo evento')),
                ('tipo_movimiento', models.CharField(choices=[('debito', 'Debito'), ('credito', 'Credito')], max_length=10)),
                ('valor', models.DecimalField(decimal_places=2, help_text='Valor positivo. El signo se deriva del tipo_movimiento y de cuenta.tipo', max_digits=15, validators=[django.core.validators.MinValueValidator(0)])),
                ('fecha', models.DateTimeField(help_text='Fecha contable del movimiento')),
                ('modulo_origen', models.CharField(help_text="Nombre de la app que origino el movimiento (ej: 'devoluciones')", max_length=40)),
                ('origen_id', models.PositiveIntegerField(help_text='PK del registro origen dentro de su tabla')),
                ('descripcion', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('sub_cuenta', models.ForeignKey(help_text='Sub-cuenta sobre la que aplica el movimiento', on_delete=django.db.models.deletion.PROTECT, related_name='movimientos', to='sub_cuentas.subcuenta')),
                ('usuario', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='movimientos_contables', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Movimiento contable',
                'verbose_name_plural': 'Movimientos contables',
                'db_table': 'movimiento_contable',
                'ordering': ['-fecha', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='movimientocontable',
            index=models.Index(fields=['sub_cuenta', 'fecha'], name='movimiento__sub_cue_3a2c1f_idx'),
        ),
        migrations.AddIndex(
            model_name='movimientocontable',
            index=models.Index(fields=['modulo_origen', 'origen_id'], name='movimiento__modulo__8b1d9e_idx'),
        ),
        migrations.AddIndex(
            model_name='movimientocontable',
            index=models.Index(fields=['asiento_id'], name='movimiento__asiento_2f5a8c_idx'),
        ),
        migrations.CreateModel(
            name='HistoricalMovimientoContable',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('asiento_id', models.UUIDField(default=uuid.uuid4, editable=False, help_text='Agrupa el debito y el credito de un mismo evento')),
                ('tipo_movimiento', models.CharField(choices=[('debito', 'Debito'), ('credito', 'Credito')], max_length=10)),
                ('valor', models.DecimalField(decimal_places=2, help_text='Valor positivo. El signo se deriva del tipo_movimiento y de cuenta.tipo', max_digits=15, validators=[django.core.validators.MinValueValidator(0)])),
                ('fecha', models.DateTimeField(help_text='Fecha contable del movimiento')),
                ('modulo_origen', models.CharField(help_text="Nombre de la app que origino el movimiento (ej: 'devoluciones')", max_length=40)),
                ('origen_id', models.PositiveIntegerField(help_text='PK del registro origen dentro de su tabla')),
                ('descripcion', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('sub_cuenta', models.ForeignKey(blank=True, db_constraint=False, help_text='Sub-cuenta sobre la que aplica el movimiento', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='sub_cuentas.subcuenta')),
                ('usuario', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical Movimiento contable',
                'verbose_name_plural': 'historical Movimientos contables',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
