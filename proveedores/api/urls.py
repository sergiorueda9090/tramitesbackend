from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_proveedores,       name='list_proveedores'),
    path('create/',                 views.create_proveedor,       name='create_proveedor'),
    path('<int:pk>/',               views.get_proveedor,          name='get_proveedor'),
    path('<int:pk>/update/',        views.update_proveedor,       name='update_proveedor'),
    path('<int:pk>/delete/',        views.delete_proveedor,       name='delete_proveedor'),
    path('<int:pk>/restore/',       views.restore_proveedor,      name='restore_proveedor'),
    path('<int:pk>/hard-delete/',   views.hard_delete_proveedor,  name='hard_delete_proveedor'),
    path('<int:pk>/history/',       views.proveedor_history,      name='proveedor_history'),
]
