from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_devoluciones,       name='list_devoluciones'),
    path('create/',                 views.create_devolucion,       name='create_devolucion'),
    path('<int:pk>/',               views.get_devolucion,          name='get_devolucion'),
    path('<int:pk>/update/',        views.update_devolucion,       name='update_devolucion'),
    path('<int:pk>/delete/',        views.delete_devolucion,       name='delete_devolucion'),
    path('<int:pk>/restore/',       views.restore_devolucion,      name='restore_devolucion'),
    path('<int:pk>/hard-delete/',   views.hard_delete_devolucion,  name='hard_delete_devolucion'),
    path('<int:pk>/history/',       views.devolucion_history,      name='devolucion_history'),
]
