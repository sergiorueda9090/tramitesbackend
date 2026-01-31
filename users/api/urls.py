from django.urls import path
from . import views

urlpatterns = [
    path('me/',                      views.me_view,     name='me'),
    path('<int:pk>/toggle-status/',  views.toggle_status, name='toggle_status'),
    path('list/',             views.list_users,  name='list_users'),
    path('create/',           views.create_user, name='create_user'),
    path('<int:pk>/',         views.get_user,    name='get_user'),
    path('<int:pk>/update/',  views.update_user, name='update_user'),
    path('<int:pk>/delete/',  views.delete_user, name='delete_user'),
]