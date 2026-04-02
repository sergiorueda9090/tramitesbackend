from django.urls import path
from . import views

urlpatterns = [
    # CRUD — Catálogo de endpoints externos
    path('endpoints/list/',                   views.list_endpoints,       name='api_list_endpoints'),
    path('endpoints/create/',                 views.create_endpoint,      name='api_create_endpoint'),
    path('endpoints/<int:pk>/',               views.get_endpoint,         name='api_get_endpoint'),
    path('endpoints/<int:pk>/update/',        views.update_endpoint,      name='api_update_endpoint'),
    path('endpoints/<int:pk>/delete/',        views.delete_endpoint,      name='api_delete_endpoint'),
    path('endpoints/<int:pk>/restore/',       views.restore_endpoint,     name='api_restore_endpoint'),
    path('endpoints/<int:pk>/hard-delete/',   views.hard_delete_endpoint, name='api_hard_delete_endpoint'),
    path('endpoints/<int:pk>/history/',       views.endpoint_history,     name='api_endpoint_history'),

    # Proxy — APIs externas
    path('runt_vehiculo/',          views.runt_vehiculo,        name='api_runt_vehiculo'),
    path('runt_vehiculo_vin/',      views.runt_vehiculo_vin,    name='api_runt_vehiculo_vin'),
    path('tarjeta_propiedad/',      views.tarjeta_propiedad,    name='api_tarjeta_propiedad'),
    path('vin/',                    views.vin_extractor,        name='api_vin_extractor'),
    path('runt_persona/',           views.runt_persona,         name='api_runt_persona'),
    path('nombre_cliente/',         views.nombre_cliente,       name='api_nombre_cliente'),
    path('previsora/',              views.previsora,            name='api_previsora'),
]
