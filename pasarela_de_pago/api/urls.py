from django.urls import path
from . import views

urlpatterns = [
    # Pasarela de pago
    path('list/',                   views.list_pasarelas,      name='list_pasarelas'),
    path('create/',                 views.create_pasarela,     name='create_pasarela'),
    path('<int:pk>/',               views.get_pasarela,        name='get_pasarela'),
    path('<int:pk>/update/',        views.update_pasarela,     name='update_pasarela'),
    path('<int:pk>/delete/',        views.delete_pasarela,     name='delete_pasarela'),
    path('<int:pk>/restore/',       views.restore_pasarela,    name='restore_pasarela'),
    path('<int:pk>/hard-delete/',   views.hard_delete_pasarela, name='hard_delete_pasarela'),
    path('<int:pk>/history/',       views.pasarela_history,    name='pasarela_history'),

    # Confirmar pago (modal de timer)
    path('<int:pk>/confirmar-pago/',  views.confirmar_pago_pasarela, name='confirmar_pago_pasarela'),

    # Transiciones de estado
    path('<int:pk>/cambiar-estado/',  views.cambiar_estado,   name='cambiar_estado_pasarela'),
    path('<int:pk>/revertir-estado/', views.revertir_estado,  name='revertir_estado_pasarela'),
]
