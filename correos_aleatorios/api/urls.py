from django.urls import path
from . import views

urlpatterns = [
    # Pool de correos aleatorios
    path('list/',                 views.list_correos,        name='list_correos'),
    path('create/',               views.create_correo,       name='create_correo'),
    path('<int:pk>/',             views.get_correo,          name='get_correo'),
    path('<int:pk>/update/',      views.update_correo,       name='update_correo'),
    path('<int:pk>/delete/',      views.delete_correo,       name='delete_correo'),
    path('<int:pk>/restore/',     views.restore_correo,      name='restore_correo'),
    path('<int:pk>/hard-delete/', views.hard_delete_correo,  name='hard_delete_correo'),
    path('<int:pk>/history/',     views.correo_history,      name='correo_history'),

    # Carga masiva desde Excel (el frontend parsea el .xlsx y envía las filas)
    path('bulk-create/',          views.bulk_create_correos, name='bulk_create_correos'),
]
