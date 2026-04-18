from django.urls import path
from . import views

urlpatterns = [
    # Casos Especiales
    path('list/',                   views.list_casos_especiales,      name='list_casos_especiales'),
    path('create/',                 views.create_caso_especial,       name='create_caso_especial'),
    path('<int:pk>/',               views.get_caso_especial,          name='get_caso_especial'),
    path('<int:pk>/update/',        views.update_caso_especial,       name='update_caso_especial'),
    path('<int:pk>/delete/',        views.delete_caso_especial,       name='delete_caso_especial'),
    path('<int:pk>/restore/',       views.restore_caso_especial,      name='restore_caso_especial'),
    path('<int:pk>/hard-delete/',   views.hard_delete_caso_especial,  name='hard_delete_caso_especial'),
    path('<int:pk>/history/',       views.caso_especial_history,      name='caso_especial_history'),

    # Transiciones de estado
    path('<int:pk>/cambiar-estado/',  views.cambiar_estado,   name='cambiar_estado_caso_especial'),
    path('<int:pk>/revertir-estado/', views.revertir_estado,  name='revertir_estado_caso_especial'),

    # Pagos
    path('<int:caso_especial_pk>/pagos/',        views.list_pagos,   name='list_pagos_caso_especial'),
    path('<int:caso_especial_pk>/pagos/create/', views.create_pago,  name='create_pago_caso_especial'),
    path('pagos/<int:pk>/update/',               views.update_pago,  name='update_pago_caso_especial'),
    path('pagos/<int:pk>/delete/',               views.delete_pago,  name='delete_pago_caso_especial'),
]
