from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_recepciones_pago,       name='list_recepciones_pago'),
    path('create/',                 views.create_recepcion_pago,       name='create_recepcion_pago'),
    path('<int:pk>/',               views.get_recepcion_pago,          name='get_recepcion_pago'),
    path('<int:pk>/update/',        views.update_recepcion_pago,       name='update_recepcion_pago'),
    path('<int:pk>/delete/',        views.delete_recepcion_pago,       name='delete_recepcion_pago'),
    path('<int:pk>/restore/',       views.restore_recepcion_pago,      name='restore_recepcion_pago'),
    path('<int:pk>/hard-delete/',   views.hard_delete_recepcion_pago,  name='hard_delete_recepcion_pago'),
    path('<int:pk>/history/',       views.recepcion_pago_history,      name='recepcion_pago_history'),
]
