from django.urls import path
from . import views

urlpatterns = [
    # Gastos
    path('list/',                   views.list_gastos,          name='list_gastos'),
    path('create/',                 views.create_gasto,         name='create_gasto'),
    path('<int:pk>/',               views.get_gasto,            name='get_gasto'),
    path('<int:pk>/update/',        views.update_gasto,         name='update_gasto'),
    path('<int:pk>/delete/',        views.delete_gasto,         name='delete_gasto'),
    path('<int:pk>/restore/',       views.restore_gasto,        name='restore_gasto'),
    path('<int:pk>/hard-delete/',   views.hard_delete_gasto,    name='hard_delete_gasto'),
    path('<int:pk>/history/',       views.gasto_history,        name='gasto_history'),

    # Gasto Relaciones
    path('relaciones/list/',                    views.list_gasto_relaciones,        name='list_gasto_relaciones'),
    path('relaciones/create/',                  views.create_gasto_relacion,        name='create_gasto_relacion'),
    path('relaciones/<int:pk>/',                views.get_gasto_relacion,           name='get_gasto_relacion'),
    path('relaciones/<int:pk>/update/',         views.update_gasto_relacion,        name='update_gasto_relacion'),
    path('relaciones/<int:pk>/delete/',         views.delete_gasto_relacion,        name='delete_gasto_relacion'),
    path('relaciones/<int:pk>/restore/',        views.restore_gasto_relacion,       name='restore_gasto_relacion'),
    path('relaciones/<int:pk>/hard-delete/',    views.hard_delete_gasto_relacion,   name='hard_delete_gasto_relacion'),
    path('relaciones/<int:pk>/history/',        views.gasto_relacion_history,       name='gasto_relacion_history'),
]
