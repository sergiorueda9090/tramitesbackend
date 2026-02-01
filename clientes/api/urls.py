from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_clients,       name='list_clients'),
    path('create/',                 views.create_client,      name='create_client'),
    path('<int:pk>/',               views.get_client,         name='get_client'),
    path('<int:pk>/update/',        views.update_client,      name='update_client'),
    path('<int:pk>/delete/',        views.delete_client,      name='delete_client'),
    path('<int:pk>/restore/',       views.restore_client,     name='restore_client'),
    path('<int:pk>/hard-delete/',   views.hard_delete_client, name='hard_delete_client'),
    path('<int:pk>/history/',       views.client_history,     name='client_history'),
]
