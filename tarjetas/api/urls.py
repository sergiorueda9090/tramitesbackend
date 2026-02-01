from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_tarjetas,       name='list_tarjetas'),
    path('create/',                 views.create_tarjeta,      name='create_tarjeta'),
    path('<int:pk>/',               views.get_tarjeta,         name='get_tarjeta'),
    path('<int:pk>/update/',        views.update_tarjeta,      name='update_tarjeta'),
    path('<int:pk>/delete/',        views.delete_tarjeta,      name='delete_tarjeta'),
    path('<int:pk>/restore/',       views.restore_tarjeta,     name='restore_tarjeta'),
    path('<int:pk>/hard-delete/',   views.hard_delete_tarjeta, name='hard_delete_tarjeta'),
    path('<int:pk>/history/',       views.tarjeta_history,     name='tarjeta_history'),
]
