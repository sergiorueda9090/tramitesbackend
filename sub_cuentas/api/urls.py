from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_sub_cuentas,        name='list_sub_cuentas'),
    path('create/',                 views.create_sub_cuenta,       name='create_sub_cuenta'),
    path('balance/',                views.balance_sub_cuentas,     name='balance_sub_cuentas'),
    path('balance/resumen/',        views.balance_resumen,         name='balance_resumen'),
    path('<int:pk>/',               views.get_sub_cuenta,          name='get_sub_cuenta'),
    path('<int:pk>/update/',        views.update_sub_cuenta,       name='update_sub_cuenta'),
    path('<int:pk>/delete/',        views.delete_sub_cuenta,       name='delete_sub_cuenta'),
    path('<int:pk>/restore/',       views.restore_sub_cuenta,      name='restore_sub_cuenta'),
    path('<int:pk>/hard-delete/',   views.hard_delete_sub_cuenta,  name='hard_delete_sub_cuenta'),
    path('<int:pk>/history/',       views.sub_cuenta_history,      name='sub_cuenta_history'),
    path('<int:pk>/saldo/',         views.saldo_sub_cuenta,        name='saldo_sub_cuenta'),
    path('<int:pk>/movimientos/',   views.movimientos_sub_cuenta,  name='movimientos_sub_cuenta'),
]
