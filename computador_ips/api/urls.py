from django.urls import path
from . import views


urlpatterns = [
    path('list/',                 views.list_computador_ips,        name='list_computador_ips'),
    path('create/',               views.create_computador_ip,       name='create_computador_ip'),
    path('<int:pk>/',             views.get_computador_ip,          name='get_computador_ip'),
    path('<int:pk>/update/',      views.update_computador_ip,       name='update_computador_ip'),
    path('<int:pk>/delete/',      views.delete_computador_ip,       name='delete_computador_ip'),
    path('<int:pk>/restore/',     views.restore_computador_ip,      name='restore_computador_ip'),
    path('<int:pk>/hard-delete/', views.hard_delete_computador_ip,  name='hard_delete_computador_ip'),
    path('<int:pk>/history/',     views.computador_ip_history,      name='computador_ip_history'),
]
