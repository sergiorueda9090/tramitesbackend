from django.urls import path
from . import views

urlpatterns = [
    path('list/',                   views.list_finalizados,       name='list_finalizados'),
    path('<int:pk>/',               views.get_finalizado,         name='get_finalizado'),
    path('<int:pk>/update/',        views.update_finalizado,      name='update_finalizado'),
    path('<int:pk>/delete/',        views.delete_finalizado,      name='delete_finalizado'),
    path('<int:pk>/restore/',       views.restore_finalizado,     name='restore_finalizado'),
    path('<int:pk>/hard-delete/',   views.hard_delete_finalizado, name='hard_delete_finalizado'),
    path('<int:pk>/history/',       views.finalizado_history,     name='finalizado_history'),

    # PDFs adjuntos (uno o varios por finalizado)
    path('<int:pk>/pdfs/',                       views.list_pdfs,    name='list_pdfs_finalizado'),
    path('<int:pk>/pdfs/upload/',                views.upload_pdfs,  name='upload_pdfs_finalizado'),
    path('<int:pk>/pdfs/<int:pdf_pk>/update/',   views.update_pdf,   name='update_pdf_finalizado'),
    path('<int:pk>/pdfs/<int:pdf_pk>/delete/',   views.delete_pdf,   name='delete_pdf_finalizado'),
    path('<int:pk>/pdfs/<int:pdf_pk>/download/', views.download_pdf, name='download_pdf_finalizado'),
]
