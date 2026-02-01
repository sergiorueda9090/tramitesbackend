from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_utilidades_ocasionales,      name='list_utilidades_ocasionales'),
    path('create/',                 views.create_utilidad_ocasional,        name='create_utilidad_ocasional'),
    path('<int:pk>/',               views.get_utilidad_ocasional,           name='get_utilidad_ocasional'),
    path('<int:pk>/update/',        views.update_utilidad_ocasional,        name='update_utilidad_ocasional'),
    path('<int:pk>/delete/',        views.delete_utilidad_ocasional,        name='delete_utilidad_ocasional'),
    path('<int:pk>/restore/',       views.restore_utilidad_ocasional,       name='restore_utilidad_ocasional'),
    path('<int:pk>/hard-delete/',   views.hard_delete_utilidad_ocasional,   name='hard_delete_utilidad_ocasional'),
    path('<int:pk>/history/',       views.utilidad_ocasional_history,       name='utilidad_ocasional_history'),
]
