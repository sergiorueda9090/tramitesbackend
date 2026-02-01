from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_etiquetas,       name='list_etiquetas'),
    path('create/',                 views.create_etiqueta,      name='create_etiqueta'),
    path('<int:pk>/',               views.get_etiqueta,         name='get_etiqueta'),
    path('<int:pk>/update/',        views.update_etiqueta,      name='update_etiqueta'),
    path('<int:pk>/delete/',        views.delete_etiqueta,      name='delete_etiqueta'),
    path('<int:pk>/restore/',       views.restore_etiqueta,     name='restore_etiqueta'),
    path('<int:pk>/hard-delete/',   views.hard_delete_etiqueta, name='hard_delete_etiqueta'),
    path('<int:pk>/history/',       views.etiqueta_history,     name='etiqueta_history'),
]
