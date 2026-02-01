from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_ajustes_de_saldo,       name='list_ajustes_de_saldo'),
    path('create/',                 views.create_ajuste_de_saldo,      name='create_ajuste_de_saldo'),
    path('<int:pk>/',               views.get_ajuste_de_saldo,         name='get_ajuste_de_saldo'),
    path('<int:pk>/update/',        views.update_ajuste_de_saldo,      name='update_ajuste_de_saldo'),
    path('<int:pk>/delete/',        views.delete_ajuste_de_saldo,      name='delete_ajuste_de_saldo'),
    path('<int:pk>/restore/',       views.restore_ajuste_de_saldo,     name='restore_ajuste_de_saldo'),
    path('<int:pk>/hard-delete/',   views.hard_delete_ajuste_de_saldo, name='hard_delete_ajuste_de_saldo'),
    path('<int:pk>/history/',       views.ajuste_de_saldo_history,     name='ajuste_de_saldo_history'),
]
