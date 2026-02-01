from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_cargos_no_registrados,       name='list_cargos_no_registrados'),
    path('create/',                 views.create_cargo_no_registrado,       name='create_cargo_no_registrado'),
    path('<int:pk>/',               views.get_cargo_no_registrado,          name='get_cargo_no_registrado'),
    path('<int:pk>/update/',        views.update_cargo_no_registrado,       name='update_cargo_no_registrado'),
    path('<int:pk>/delete/',        views.delete_cargo_no_registrado,       name='delete_cargo_no_registrado'),
    path('<int:pk>/restore/',       views.restore_cargo_no_registrado,      name='restore_cargo_no_registrado'),
    path('<int:pk>/hard-delete/',   views.hard_delete_cargo_no_registrado,  name='hard_delete_cargo_no_registrado'),
    path('<int:pk>/history/',       views.cargo_no_registrado_history,      name='cargo_no_registrado_history'),
]
