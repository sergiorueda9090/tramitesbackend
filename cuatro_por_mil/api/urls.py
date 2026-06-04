from django.urls import path
from . import views

urlpatterns = [
    path('config/',                 views.get_config,                 name='get_cuatro_por_mil_config'),
    path('config/update/',          views.update_config,              name='update_cuatro_por_mil_config'),
    path('list/',                   views.list_cuatro_por_mil,        name='list_cuatro_por_mil'),
    path('stats/',                  views.stats_cuatro_por_mil,       name='stats_cuatro_por_mil'),
    path('create/',                 views.create_cuatro_por_mil,      name='create_cuatro_por_mil'),
    path('<int:pk>/',               views.get_cuatro_por_mil,         name='get_cuatro_por_mil'),
    path('<int:pk>/update/',        views.update_cuatro_por_mil,      name='update_cuatro_por_mil'),
    path('<int:pk>/delete/',        views.delete_cuatro_por_mil,      name='delete_cuatro_por_mil'),
    path('<int:pk>/restore/',       views.restore_cuatro_por_mil,     name='restore_cuatro_por_mil'),
    path('<int:pk>/hard-delete/',   views.hard_delete_cuatro_por_mil, name='hard_delete_cuatro_por_mil'),
    path('<int:pk>/history/',       views.cuatro_por_mil_history,     name='cuatro_por_mil_history'),
]
