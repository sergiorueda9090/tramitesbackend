from django.urls import path
from . import views

urlpatterns = [
    path('crear-desde-pasarela/',   views.crear_desde_pasarela,   name='crear_desde_pasarela'),
    path('list/',                   views.list_finalizados,       name='list_finalizados'),
    path('<int:pk>/',               views.get_finalizado,         name='get_finalizado'),
    path('<int:pk>/update/',        views.update_finalizado,      name='update_finalizado'),
    path('<int:pk>/delete/',        views.delete_finalizado,      name='delete_finalizado'),
    path('<int:pk>/restore/',       views.restore_finalizado,     name='restore_finalizado'),
    path('<int:pk>/hard-delete/',   views.hard_delete_finalizado, name='hard_delete_finalizado'),
    path('<int:pk>/history/',       views.finalizado_history,     name='finalizado_history'),

    # URL prefirmada (temporal) para visualizar el comprobante de pago en S3
    path('<int:pk>/comprobante-url/', views.comprobante_url_finalizado, name='comprobante_url_finalizado'),

    # Proxy: el backend hace streaming de la imagen sin exponer credenciales ni la URL de S3
    path('<int:pk>/comprobante/', views.comprobante_finalizado, name='comprobante_finalizado'),

    # PDFs adjuntos (uno o varios por finalizado)
    path('<int:pk>/pdfs/',                       views.list_pdfs,    name='list_pdfs_finalizado'),
    path('<int:pk>/pdfs/upload/',                views.upload_pdfs,  name='upload_pdfs_finalizado'),
    path('<int:pk>/pdfs/<int:pdf_pk>/update/',   views.update_pdf,   name='update_pdf_finalizado'),
    path('<int:pk>/pdfs/<int:pdf_pk>/delete/',   views.delete_pdf,   name='delete_pdf_finalizado'),
    path('<int:pk>/pdfs/<int:pdf_pk>/download/', views.download_pdf, name='download_pdf_finalizado'),

    # Descarga automática del PDF por aseguradora (ventana de 5 min)
    path('<int:pk>/pdfs/descargar/previsora/', views.descargar_pdf_previsora, name='descargar_pdf_previsora'),
    path('<int:pk>/pdfs/descargar/mundial/',   views.descargar_pdf_mundial,   name='descargar_pdf_mundial'),
]
