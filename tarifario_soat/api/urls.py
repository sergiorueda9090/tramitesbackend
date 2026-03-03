from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_tarifarios,      name='list_tarifarios'),
    path('create/',                 views.create_tarifario,     name='create_tarifario'),
    path('<int:pk>/',               views.get_tarifario,        name='get_tarifario'),
    path('<int:pk>/update/',        views.update_tarifario,     name='update_tarifario'),
    path('<int:pk>/delete/',        views.delete_tarifario,     name='delete_tarifario'),
    path('<int:pk>/restore/',       views.restore_tarifario,    name='restore_tarifario'),
    path('<int:pk>/hard-delete/',   views.hard_delete_tarifario, name='hard_delete_tarifario'),
    path('<int:pk>/history/',       views.tarifario_history,    name='tarifario_history'),
]
