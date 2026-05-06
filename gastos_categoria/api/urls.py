from django.urls import path
from . import views

urlpatterns = [
    path('list/',                 views.list_categorias,       name='list_categorias'),
    path('create/',               views.create_categoria,      name='create_categoria'),
    path('<int:pk>/',             views.get_categoria,         name='get_categoria'),
    path('<int:pk>/update/',      views.update_categoria,      name='update_categoria'),
    path('<int:pk>/delete/',      views.delete_categoria,      name='delete_categoria'),
    path('<int:pk>/restore/',     views.restore_categoria,     name='restore_categoria'),
    path('<int:pk>/hard-delete/', views.hard_delete_categoria, name='hard_delete_categoria'),
    path('<int:pk>/history/',     views.categoria_history,     name='categoria_history'),
]
