from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_plan_de_cuentas,        name='list_plan_de_cuentas'),
    path('create/',                 views.create_plan_de_cuentas,      name='create_plan_de_cuentas'),
    path('<int:pk>/',               views.get_plan_de_cuentas,         name='get_plan_de_cuentas'),
    path('<int:pk>/update/',        views.update_plan_de_cuentas,      name='update_plan_de_cuentas'),
    path('<int:pk>/delete/',        views.delete_plan_de_cuentas,      name='delete_plan_de_cuentas'),
    path('<int:pk>/restore/',       views.restore_plan_de_cuentas,     name='restore_plan_de_cuentas'),
    path('<int:pk>/hard-delete/',   views.hard_delete_plan_de_cuentas, name='hard_delete_plan_de_cuentas'),
    path('<int:pk>/history/',       views.plan_de_cuentas_history,     name='plan_de_cuentas_history'),
]
