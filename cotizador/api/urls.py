from django.urls import path
from . import views

urlpatterns = [
    # Cotizador
    path('list/',                   views.list_cotizadores,     name='list_cotizadores'),
    path('create/',                 views.create_cotizador,     name='create_cotizador'),
    path('<int:pk>/',               views.get_cotizador,        name='get_cotizador'),
    path('<int:pk>/update/',        views.update_cotizador,     name='update_cotizador'),
    path('<int:pk>/delete/',        views.delete_cotizador,     name='delete_cotizador'),
    path('<int:pk>/restore/',       views.restore_cotizador,    name='restore_cotizador'),
    path('<int:pk>/hard-delete/',   views.hard_delete_cotizador,name='hard_delete_cotizador'),
    path('<int:pk>/history/',       views.cotizador_history,    name='cotizador_history'),

    # Transiciones de estado
    path('<int:pk>/cambiar-estado/',  views.cambiar_estado,     name='cambiar_estado'),
    path('<int:pk>/revertir-estado/', views.revertir_estado,    name='revertir_estado'),

    # Pagos
    path('<int:cotizador_pk>/pagos/',        views.list_pagos,   name='list_pagos'),
    path('<int:cotizador_pk>/pagos/create/', views.create_pago,  name='create_pago'),
    path('pagos/<int:pk>/update/',           views.update_pago,  name='update_pago'),
    path('pagos/<int:pk>/delete/',           views.delete_pago,  name='delete_pago'),
]
