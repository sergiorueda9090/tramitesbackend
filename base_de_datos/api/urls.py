from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_registros,       name='list_registros'),
    path('export-excel/',           views.export_registros_excel, name='export_registros_excel'),
    path('create/',                 views.create_registro,      name='create_registro'),
    path('<int:pk>/',               views.get_registro,         name='get_registro'),
    path('<int:pk>/update/',        views.update_registro,      name='update_registro'),
    path('<int:pk>/delete/',        views.delete_registro,      name='delete_registro'),
    path('<int:pk>/restore/',       views.restore_registro,     name='restore_registro'),
    path('<int:pk>/hard-delete/',   views.hard_delete_registro, name='hard_delete_registro'),
    path('<int:pk>/history/',       views.registro_history,     name='registro_history'),
]
