from django.apps import AppConfig


class CuatroPorMilConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cuatro_por_mil'

    def ready(self):
        from cuatro_por_mil.signals import connect_signals
        connect_signals()
