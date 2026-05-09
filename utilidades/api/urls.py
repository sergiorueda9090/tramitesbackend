from django.urls import path
from . import views


urlpatterns = [
    path('list/',                 views.list_utilidades,       name='list_utilidades'),
    path('<int:pk>/',             views.get_utilidad,          name='get_utilidad'),
    path('<int:pk>/delete/',      views.delete_utilidad,       name='delete_utilidad'),
    path('<int:pk>/restore/',     views.restore_utilidad,      name='restore_utilidad'),
    path('<int:pk>/hard-delete/', views.hard_delete_utilidad,  name='hard_delete_utilidad'),
    path('<int:pk>/history/',     views.utilidad_history,      name='utilidad_history'),
]
