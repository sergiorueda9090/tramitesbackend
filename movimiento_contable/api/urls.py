from django.urls import path
from . import views

urlpatterns = [
    path('list/',                       views.list_movimientos,           name='list_movimientos'),
    path('<int:pk>/',                   views.get_movimiento,             name='get_movimiento'),
    path('asiento/<uuid:asiento_id>/',  views.get_asiento,                name='get_asiento'),
    path('<int:pk>/history/',           views.movimiento_history,         name='movimiento_history'),
]
