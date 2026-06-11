from django.urls import path
from . import views

urlpatterns = [
    # Trámites
    path('crear-desde-base-de-datos/', views.crear_desde_base_de_datos, name='crear_desde_base_de_datos'),
    path('list/',                   views.list_tramites,      name='list_tramites'),
    path('create/',                 views.create_tramite,     name='create_tramite'),
    path('<int:pk>/',               views.get_tramite,        name='get_tramite'),
    path('<int:pk>/update/',        views.update_tramite,     name='update_tramite'),
    path('<int:pk>/delete/',        views.delete_tramite,     name='delete_tramite'),
    path('<int:pk>/restore/',       views.restore_tramite,    name='restore_tramite'),
    path('<int:pk>/hard-delete/',   views.hard_delete_tramite, name='hard_delete_tramite'),
    path('<int:pk>/history/',       views.tramite_history,    name='tramite_history'),

    # Transiciones de estado
    path('<int:pk>/cambiar-estado/',  views.cambiar_estado,   name='cambiar_estado_tramite'),
    path('<int:pk>/revertir-estado/', views.revertir_estado,  name='revertir_estado_tramite'),

    # Generadores de links de pago (usan un correo aleatorio del pool)
    path('generar-link/previsora/', views.generar_link_previsora, name='generar_link_previsora'),
    path('generar-link/mundial/',   views.generar_link_mundial,   name='generar_link_mundial'),
]
