from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.db import DatabaseError, transaction
from django.db.models import Q, Count
from django.utils import timezone
from django.conf import settings
from django.core.files.base import ContentFile
from datetime import datetime, timedelta
import os
import urllib.request
import urllib.error

from ..models import TramiteFinalizado, TramiteFinalizadoPdf
from .permissions import RolePermission, ModulePermission

PDF_MAX_BYTES = 15 * 1024 * 1024  # 15 MB por archivo

# Host del scraper externo que entrega el PDF de Previsora.
EXTERNAL_SCRAPER_HOST = 'https://soat-scraper.qf4cjg.easypanel.host'

# Ventana (minutos) tras confirmar el pago durante la cual se puede descargar
# automáticamente el PDF de la aseguradora. Al expirar, el backend lo bloquea.
PDF_DESCARGA_VENTANA_MINUTOS = 5


def _pdf_descarga_deadline(finalizado):
    """Momento límite para la descarga automática del PDF (pago + ventana)."""
    base = finalizado.pago_confirmado_at or finalizado.created_at
    if not base:
        return None
    return base + timedelta(minutes=PDF_DESCARGA_VENTANA_MINUTOS)


def serialize_finalizado(t):
    """Convierte un objeto TramiteFinalizado a diccionario"""
    return {
        'id': t.id,
        'pasarela': t.pasarela_id,
        'tramite_origen_id_snapshot': t.tramite_origen_id_snapshot,
        'usuario': {
            'id': t.usuario.id,
            'name': f"{t.usuario.first_name} {t.usuario.last_name}".strip(),
        } if t.usuario else None,
        'usuario_que_confirma': {
            'id': t.usuario_que_confirma.id,
            'name': f"{t.usuario_que_confirma.first_name} {t.usuario_que_confirma.last_name}".strip(),
        } if t.usuario_que_confirma else None,
        'cliente': {
            'id': t.cliente.id,
            'nombre': t.cliente.nombre,
        } if t.cliente else None,
        'etiqueta': {
            'id': t.etiqueta.id,
            'nombre': t.etiqueta.nombre,
            'color': t.etiqueta.color,
        } if t.etiqueta else None,
        'precio_cliente': {
            'id': t.precio_cliente.id,
        } if t.precio_cliente else None,
        'tarifario_soat': {
            'id': t.tarifario_soat.id,
            'codigo_tarifa': t.tarifario_soat.codigo_tarifa,
            'descripcion': t.tarifario_soat.descripcion,
            'valor': str(t.tarifario_soat.valor),
        } if t.tarifario_soat else None,
        'tarjeta': {
            'id': t.tarjeta.id,
            'numero': t.tarjeta.numero,
            'titular': t.tarjeta.titular,
            'cuatro_por_mil': t.tarjeta.cuatro_por_mil,
        } if t.tarjeta else None,

        'tipo_tramite': t.tipo_tramite,
        'tipo_tramite_display': t.get_tipo_tramite_display(),
        'tipo_vehiculo': t.tipo_vehiculo,
        'tipo_vehiculo_display': t.get_tipo_vehiculo_display() if t.tipo_vehiculo else '',
        'entidad': t.entidad,
        'entidad_display': t.get_entidad_display() if t.entidad else '',

        'grupo_soat': t.grupo_soat,
        'grupo_soat_display': t.get_grupo_soat_display() if t.grupo_soat else '',
        'grupo_clase_runt': t.grupo_clase_runt,
        'grupo_subcriterio': t.grupo_subcriterio,
        'modulo_pregunta1': t.modulo_pregunta1,
        'modulo_pregunta2': t.modulo_pregunta2,
        'tarifa_codigo': t.tarifa_codigo,
        'tarifa_manual': t.tarifa_manual,

        'precio_lay': str(t.precio_lay) if t.precio_lay is not None else None,
        'comision': str(t.comision) if t.comision is not None else None,

        'placa': t.placa,
        'clase': t.clase,
        'tipo_servicio': t.tipo_servicio,
        'marca': t.marca,
        'linea': t.linea,
        'modelo': t.modelo,
        'color': t.color,
        'cilindraje': t.cilindraje,
        'pasajeros_sentados': t.pasajeros_sentados,
        'capacidad_carga': t.capacidad_carga,
        'peso_bruto': t.peso_bruto,
        'chasis': t.chasis,
        'vin': t.vin,

        'tipo_documento': t.tipo_documento,
        'tipo_documento_display': t.get_tipo_documento_display(),
        'numero_documento': t.numero_documento,
        'nombre_completo': t.nombre_completo,
        'telefono': t.telefono,
        'correo': t.correo,
        'direccion': t.direccion,

        'tramite_estado': t.tramite_estado,
        'confirmacion_estado': t.confirmacion_estado,
        'cargar_pdf_estado': t.cargar_pdf_estado,

        'observacion': t.observacion,
        'comprobante_pago': t.comprobante_pago or None,
        'link_pago': t.link_pago or None,
        'pago_confirmado_at': t.pago_confirmado_at,
        # Ventana de descarga automática del PDF (5 min desde el pago).
        'pdf_descarga_hasta': _pdf_descarga_deadline(t),
        'pdf_descarga_vencida': bool(_pdf_descarga_deadline(t) and timezone.now() > _pdf_descarga_deadline(t)),
        'cuatro_por_mil_valor': str(t.cuatro_por_mil_valor) if t.cuatro_por_mil_valor is not None else '0',
        'pdfs_count': getattr(t, 'pdfs_count', None) if hasattr(t, 'pdfs_count') else t.pdfs.filter(deleted_at__isnull=True).count(),

        'created_at': t.created_at,
        'updated_at': t.updated_at,
        'deleted_at': t.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'create')])
def crear_desde_pasarela(request):
    """Crea un TramiteFinalizado a partir de un registro de PasarelaPago.

    Disparado por el icono "Enviar a Trámites Finalizados" en el listado de
    Pasarela, solo cuando el operario marca "Pago exitoso" en el modal de
    timer. Hace tres cosas:
      1. Snapshot completo de la pasarela en TramiteFinalizado.
      2. Soft-delete de la pasarela (sale del listado de Pasarela).
      3. Broadcasts WS: finalizado_added (aparece en Finalizados) y
         pasarela_removed (desaparece de Pasarela) en tiempo real.

    Payload:
        pasarela_id: int (requerido)
        observacion: str (opcional, sobrescribe la de la pasarela)
        tarjeta:     int (opcional, sobrescribe la de la pasarela)
    """
    from pasarela_de_pago.models import PasarelaPago
    from tarjetas.models import Tarjeta
    from django.utils import timezone as _tz
    from decimal import Decimal

    pasarela_id = request.data.get('pasarela_id')
    if not pasarela_id:
        return Response({"error": "pasarela_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        pasarela = get_object_or_404(PasarelaPago.objects, pk=pasarela_id)
        if pasarela.is_deleted:
            return Response(
                {"error": "La pasarela ya fue eliminada o devuelta a trámites."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        observacion_override = request.data.get('observacion')
        tarjeta_override_id  = request.data.get('tarjeta')
        tarjeta_final = pasarela.tarjeta
        if tarjeta_override_id:
            try:
                tarjeta_final = Tarjeta.objects.get(pk=tarjeta_override_id)
            except Tarjeta.DoesNotExist:
                pass  # caemos a la tarjeta existente

        from ..services import crear_finalizado_desde_pasarela
        finalizado = crear_finalizado_desde_pasarela(
            pasarela,
            usuario_que_confirma=request.user,
            observacion_override=observacion_override,
            tarjeta_override=tarjeta_final,
        )

        # Broadcasts: best-effort, no rompen el flujo si fallan.
        try:
            from users.realtime import notify_view_sync
            notify_view_sync(
                view_id='finalizados_tramites_list',
                event_type='finalizado_added_event',
                payload={'finalizado_id': finalizado.id, 'reason': 'created_from_pasarela'},
            )
            notify_view_sync(
                view_id='pasarela_de_pago_list',
                event_type='pasarela_removed_event',
                payload={'pasarela_id': pasarela.id, 'reason': 'sent_to_finalizados'},
            )
        except Exception as e:
            print(f"WARNING: notify_view_sync fallo: {e}")

        return Response(serialize_finalizado(finalizado), status=status.HTTP_201_CREATED)

    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'view')])
def comprobante_url_finalizado(request, pk):
    """Devuelve una URL prefirmada (temporal, ~1h) para visualizar el comprobante
    de pago del finalizado, almacenado en S3 (bucket privado)."""
    finalizado = get_object_or_404(TramiteFinalizado.objects, pk=pk)
    if not finalizado.comprobante_pago:
        return Response({"error": "Este trámite finalizado no tiene comprobante de pago."}, status=status.HTTP_404_NOT_FOUND)

    from pasarela_de_pago.services import generar_url_presignada
    url, err = generar_url_presignada(finalizado.comprobante_pago)
    if err:
        return Response({"error": f"No se pudo generar la URL del comprobante: {err}"}, status=status.HTTP_502_BAD_GATEWAY)
    return Response({"url": url}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'view')])
def comprobante_finalizado(request, pk):
    """Proxy que entrega el comprobante de pago (imagen en S3 privado) haciendo
    streaming desde el backend. El cliente no recibe ninguna credencial ni la
    URL de S3: solo consume esta ruta autenticada con su JWT."""
    finalizado = get_object_or_404(TramiteFinalizado.objects, pk=pk)
    if not finalizado.comprobante_pago:
        return Response({"error": "Este trámite finalizado no tiene comprobante de pago."}, status=status.HTTP_404_NOT_FOUND)

    from pasarela_de_pago.services import obtener_objeto_s3
    body, content_type, err = obtener_objeto_s3(finalizado.comprobante_pago)
    if err:
        return Response({"error": f"No se pudo obtener el comprobante: {err}"}, status=status.HTTP_502_BAD_GATEWAY)

    resp = FileResponse(body, content_type=content_type)
    resp['Content-Disposition'] = 'inline'
    return resp


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'view')])
def list_finalizados(request):
    """Listar trámites finalizados con filtros y paginación"""
    try:
        finalizados = TramiteFinalizado.objects.select_related(
            'usuario', 'usuario_que_confirma', 'cliente', 'etiqueta',
            'precio_cliente', 'tarifario_soat', 'tarjeta', 'pasarela',
        ).annotate(
            pdfs_count=Count('pdfs', filter=Q(pdfs__deleted_at__isnull=True))
        ).all()

        # Búsqueda libre
        search_query = request.query_params.get('search', None)
        if search_query:
            finalizados = finalizados.filter(
                Q(placa__icontains=search_query) |
                Q(nombre_completo__icontains=search_query) |
                Q(numero_documento__icontains=search_query) |
                Q(chasis__icontains=search_query) |
                Q(vin__icontains=search_query) |
                Q(observacion__icontains=search_query)
            )

        # Filtros directos
        for param, field in [
            ('cliente', 'cliente_id'),
            ('etiqueta', 'etiqueta_id'),
            ('pasarela', 'pasarela_id'),
            ('tarjeta', 'tarjeta_id'),
            ('tipo_tramite', 'tipo_tramite'),
            ('grupo_soat', 'grupo_soat'),
            ('tarifa_codigo', 'tarifa_codigo'),
        ]:
            value = request.query_params.get(param, None)
            if value:
                finalizados = finalizados.filter(**{field: value})

        # Filtro por fecha de creación (created_at)
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                finalizados = finalizados.filter(created_at__gte=start_date)
            except ValueError:
                return Response({"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                finalizados = finalizados.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response({"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        # Filtro por fecha de pago confirmado
        pago_desde_str = request.query_params.get('pago_confirmado_desde', None)
        pago_hasta_str = request.query_params.get('pago_confirmado_hasta', None)
        if pago_desde_str:
            try:
                pago_desde = datetime.strptime(pago_desde_str, '%Y-%m-%d').date()
                finalizados = finalizados.filter(pago_confirmado_at__gte=pago_desde)
            except ValueError:
                return Response({"error": "El formato de pago_confirmado_desde debe ser YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        if pago_hasta_str:
            try:
                pago_hasta = datetime.strptime(pago_hasta_str, '%Y-%m-%d').date()
                pago_hasta_inclusive = datetime.combine(pago_hasta, datetime.max.time())
                finalizados = finalizados.filter(pago_confirmado_at__lte=pago_hasta_inclusive)
            except ValueError:
                return Response({"error": "El formato de pago_confirmado_hasta debe ser YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        # Soft-delete
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            finalizados = finalizados.filter(deleted_at__isnull=True)

        finalizados = finalizados.order_by('-pago_confirmado_at', '-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(finalizados, request)

        data = [serialize_finalizado(t) for t in paginated]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response({"error": f"Error al obtener finalizados: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'view')])
def get_finalizado(request, pk):
    """Obtener un finalizado por ID"""
    try:
        t = get_object_or_404(
            TramiteFinalizado.objects.select_related(
                'usuario', 'usuario_que_confirma', 'cliente', 'etiqueta',
                'precio_cliente', 'tarifario_soat', 'tarjeta', 'pasarela',
            ),
            pk=pk
        )
        return Response(serialize_finalizado(t), status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al obtener finalizado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('finalizados_tramites', 'edit')])
def update_finalizado(request, pk):
    """Actualizar un finalizado.

    Pensado solo para correcciones puntuales (observación, datos del titular,
    estados snapshot). El snapshot original NO debería modificarse en el flujo normal.
    """
    try:
        t = get_object_or_404(TramiteFinalizado.objects, pk=pk)

        # Campos editables (los que tiene sentido corregir)
        editable_fields = [
            'tarjeta_id',
            'observacion',
            'tramite_estado', 'confirmacion_estado', 'cargar_pdf_estado',
            'placa', 'clase', 'tipo_servicio', 'marca', 'linea', 'modelo',
            'color', 'cilindraje', 'pasajeros_sentados', 'capacidad_carga',
            'peso_bruto', 'chasis', 'vin',
            'tipo_documento', 'numero_documento', 'nombre_completo',
            'telefono', 'correo', 'direccion',
        ]

        if 'tarjeta' in request.data:
            t.tarjeta_id = request.data.get('tarjeta') or None

        for field in editable_fields:
            if field == 'tarjeta_id':
                continue  # ya manejado
            if field in request.data:
                setattr(t, field, request.data.get(field))

        t.save()

        return Response(serialize_finalizado(t), status=status.HTTP_200_OK)

    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('finalizados_tramites', 'delete')])
def delete_finalizado(request, pk):
    """Eliminar un finalizado (soft delete) y revertir sus asientos contables."""
    try:
        from movimiento_contable.services import revertir_asiento
        t = get_object_or_404(TramiteFinalizado.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(t.asiento_emision_id)
            revertir_asiento(t.asiento_comision_id)
            TramiteFinalizado.objects.filter(pk=t.pk).update(
                asiento_emision_id=None, asiento_comision_id=None
            )
            t.refresh_from_db(fields=['asiento_emision_id', 'asiento_comision_id'])
            t.soft_delete()
        return Response({"message": "Finalizado eliminado correctamente"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al eliminar finalizado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('finalizados_tramites', 'delete')])
def restore_finalizado(request, pk):
    """Restaurar un finalizado eliminado y volver a postear sus asientos contables."""
    try:
        from ..services import _registrar_asientos_soat
        t = get_object_or_404(
            TramiteFinalizado.objects.select_related('cliente__sub_cuenta'), pk=pk
        )
        if not t.is_deleted:
            return Response({"error": "El finalizado no está eliminado"}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            t.restore()
            # Re-postear los asientos (best-effort, mismos criterios que al crear).
            _registrar_asientos_soat(t, t.usuario_que_confirma)
        return Response(serialize_finalizado(t), status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al restaurar finalizado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('finalizados_tramites', 'delete')])
def hard_delete_finalizado(request, pk):
    """Eliminar permanentemente un finalizado (revierte sus asientos si seguían activos)."""
    try:
        from movimiento_contable.services import revertir_asiento
        t = get_object_or_404(TramiteFinalizado.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(t.asiento_emision_id)
            revertir_asiento(t.asiento_comision_id)
            t.delete()
        return Response({"message": "Finalizado eliminado permanentemente"}, status=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        return Response({"error": f"Error al eliminar finalizado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('finalizados_tramites', 'view')])
def finalizado_history(request, pk):
    """Obtener el historial de cambios de un finalizado"""
    try:
        t = get_object_or_404(TramiteFinalizado.objects, pk=pk)
        history = t.history.all()

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_history = paginator.paginate_queryset(history, request)

        data = []
        for h in paginated_history:
            data.append({
                'history_id': h.history_id,
                'history_date': h.history_date,
                'history_type': h.history_type,
                'history_type_display': h.get_history_type_display(),
                'history_user': {
                    'id': h.history_user.id,
                    'name': f"{h.history_user.first_name} {h.history_user.last_name}".strip()
                } if h.history_user else None,
                'placa': h.placa,
                'nombre_completo': h.nombre_completo,
                'grupo_soat': h.grupo_soat,
                'tarifa_codigo': h.tarifa_codigo,
                'observacion': h.observacion,
                'pago_confirmado_at': h.pago_confirmado_at,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response({"error": f"Error al obtener historial: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== PDFs adjuntos ====================

def serialize_pdf(pdf, request=None):
    url = pdf.archivo.url if pdf.archivo else None
    if url and request is not None:
        url = request.build_absolute_uri(url)
    return {
        'id': pdf.id,
        'finalizado_id': pdf.finalizado_id,
        'nombre_original': pdf.nombre_original,
        'descripcion': pdf.descripcion,
        'tamano_bytes': pdf.tamano_bytes,
        'content_type': pdf.content_type,
        'url': url,
        'download_url': request.build_absolute_uri(
            f'/api/finalizados_tramites/{pdf.finalizado_id}/pdfs/{pdf.id}/download/'
        ) if request else None,
        'uploaded_by': {
            'id': pdf.uploaded_by.id,
            'name': f"{pdf.uploaded_by.first_name} {pdf.uploaded_by.last_name}".strip(),
        } if pdf.uploaded_by else None,
        'created_at': pdf.created_at,
        'updated_at': pdf.updated_at,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'view')])
def list_pdfs(request, pk):
    """Listar PDFs adjuntos a un finalizado."""
    try:
        finalizado = get_object_or_404(TramiteFinalizado.objects, pk=pk)
        pdfs = finalizado.pdfs.filter(deleted_at__isnull=True).select_related('uploaded_by').order_by('-created_at')
        data = [serialize_pdf(p, request) for p in pdfs]
        return Response(data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al listar PDFs: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'create')])
@parser_classes([MultiPartParser, FormParser])
def upload_pdfs(request, pk):
    """Subir uno o varios PDFs a un finalizado.

    Body multipart/form-data:
      - archivos: uno o varios files (campo repetido)
      - descripciones: JSON array opcional con descripciones por archivo en el mismo orden
    """
    try:
        finalizado = get_object_or_404(TramiteFinalizado.objects, pk=pk)

        archivos = request.FILES.getlist('archivos')
        if not archivos:
            return Response({"error": "No se recibieron archivos."}, status=status.HTTP_400_BAD_REQUEST)

        # Descripciones opcionales (paralelas a archivos)
        import json
        descripciones_raw = request.data.get('descripciones', '[]')
        try:
            descripciones = json.loads(descripciones_raw) if isinstance(descripciones_raw, str) else list(descripciones_raw)
        except Exception:
            descripciones = []

        # Validaciones
        for f in archivos:
            ext = os.path.splitext(f.name)[1].lower()
            if ext != '.pdf' and (f.content_type or '') != 'application/pdf':
                return Response(
                    {"error": f"El archivo '{f.name}' no es un PDF válido."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if f.size > PDF_MAX_BYTES:
                return Response(
                    {"error": f"El archivo '{f.name}' supera el tamaño máximo de 15 MB."},
                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                )

        creados = []
        with transaction.atomic():
            for idx, f in enumerate(archivos):
                desc = descripciones[idx] if idx < len(descripciones) else ''
                pdf = TramiteFinalizadoPdf.objects.create(
                    finalizado=finalizado,
                    archivo=f,
                    nombre_original=f.name,
                    descripcion=desc or '',
                    tamano_bytes=f.size or 0,
                    content_type=f.content_type or 'application/pdf',
                    uploaded_by=request.user,
                )
                creados.append(pdf)

        data = [serialize_pdf(p, request) for p in creados]
        return Response(data, status=status.HTTP_201_CREATED)

    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error al subir PDFs: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'edit')])
def update_pdf(request, pk, pdf_pk):
    """Actualizar metadata (nombre_original, descripcion) de un PDF."""
    try:
        pdf = get_object_or_404(
            TramiteFinalizadoPdf.objects.filter(finalizado_id=pk, deleted_at__isnull=True),
            pk=pdf_pk
        )
        if 'descripcion' in request.data:
            pdf.descripcion = request.data.get('descripcion') or ''
        if 'nombre_original' in request.data:
            nombre = (request.data.get('nombre_original') or '').strip()
            if nombre:
                pdf.nombre_original = nombre
        pdf.save()
        return Response(serialize_pdf(pdf, request), status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al actualizar PDF: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'delete')])
def delete_pdf(request, pk, pdf_pk):
    """Soft-delete de un PDF."""
    try:
        pdf = get_object_or_404(
            TramiteFinalizadoPdf.objects.filter(finalizado_id=pk),
            pk=pdf_pk
        )
        pdf.soft_delete()
        return Response({"message": "PDF eliminado correctamente"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al eliminar PDF: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('finalizados_tramites', 'view')])
def download_pdf(request, pk, pdf_pk):
    """Descargar un PDF (stream con Content-Disposition)."""
    try:
        pdf = get_object_or_404(
            TramiteFinalizadoPdf.objects.filter(finalizado_id=pk, deleted_at__isnull=True),
            pk=pdf_pk
        )
        if not pdf.archivo or not os.path.exists(pdf.archivo.path):
            raise Http404('Archivo no encontrado en disco.')
        response = FileResponse(
            open(pdf.archivo.path, 'rb'),
            content_type=pdf.content_type or 'application/pdf',
        )
        response['Content-Disposition'] = f'attachment; filename="{pdf.nombre_original}"'
        return response
    except Http404:
        return Response({"error": "Archivo no encontrado."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": f"Error al descargar PDF: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== DESCARGA AUTOMÁTICA DE PDF (por aseguradora) ====================

# El scraper de Previsora exige el tipo de documento como CC/CE/NIT/PA/TI.
# Los datos pueden venir como código de una letra (C/E/T/P del cotizador) o como
# el código del modelo (CC/CE/NIT/PAS). Se normaliza a lo que espera Previsora.
_TIPO_DOC_PREVISORA = {
    'C': 'CC', 'CC': 'CC',
    'E': 'CE', 'CE': 'CE',
    'T': 'TI', 'TI': 'TI',
    'P': 'PA', 'PA': 'PA', 'PAS': 'PA',
    'NIT': 'NIT',
}


def _tipo_doc_previsora(valor):
    """Normaliza el tipo de documento al formato de Previsora; None si no aplica."""
    return _TIPO_DOC_PREVISORA.get((valor or '').strip().upper())


def _ventana_descarga_error(finalizado):
    """Devuelve un Response de error si la ventana de 5 min ya expiró, o None."""
    deadline = _pdf_descarga_deadline(finalizado)
    if deadline and timezone.now() > deadline:
        return Response(
            {"error": f"La ventana de {PDF_DESCARGA_VENTANA_MINUTOS} minutos para descargar el PDF ya expiró."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _guardar_pdf_descargado(finalizado, content, filename, descripcion, user):
    """Persiste el PDF descargado como TramiteFinalizadoPdf (storage local)."""
    pdf = TramiteFinalizadoPdf(
        finalizado=finalizado,
        nombre_original=filename,
        descripcion=descripcion,
        tamano_bytes=len(content),
        content_type='application/pdf',
        uploaded_by=user,
    )
    pdf.archivo.save(filename, ContentFile(content), save=True)
    return pdf


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('finalizados_tramites', 'create')])
def descargar_pdf_previsora(request, pk):
    """
    Descarga el PDF del SOAT desde el portal Previsora y lo adjunta al finalizado.
    Usa el scraper: GET /api/previsora_pdf/<placa>/<tipo_documento>/<numero_documento>.
    Solo permitido dentro de la ventana de 5 min tras confirmar el pago.
    """
    finalizado = get_object_or_404(TramiteFinalizado.objects, pk=pk)

    err = _ventana_descarga_error(finalizado)
    if err:
        return err

    placa = (finalizado.placa or '').strip()
    num_doc = (finalizado.numero_documento or '').strip()
    if not placa or not num_doc:
        return Response({"error": "El finalizado no tiene placa o documento para consultar el PDF."}, status=status.HTTP_400_BAD_REQUEST)

    tipo_doc = _tipo_doc_previsora(finalizado.tipo_documento)
    if not tipo_doc:
        return Response(
            {"error": f"El tipo de documento '{finalizado.tipo_documento or ''}' no es soportado por Previsora (debe ser CC, CE, NIT, PA o TI)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    url = f"{EXTERNAL_SCRAPER_HOST}/api/previsora_pdf/{placa}/{tipo_doc}/{num_doc}"
    try:
        req = urllib.request.Request(url, method='GET')
        req.add_header('Accept', 'application/pdf')
        with urllib.request.urlopen(req, timeout=120) as response:
            content = response.read()
            ctype = response.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        detalle = e.read().decode('utf-8', errors='replace')
        return Response(
            {"error": f"Error del servicio de Previsora: {e.code}", "detalle": detalle},
            status=e.code if 400 <= e.code < 600 else status.HTTP_502_BAD_GATEWAY,
        )
    except urllib.error.URLError as e:
        return Response({"error": f"No se pudo conectar al servicio de Previsora: {str(e.reason)}"}, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        return Response({"error": f"Error inesperado al descargar el PDF de Previsora: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Si el scraper devolvió JSON (no un PDF), es un error de negocio: lo reenviamos.
    if not content or b'%PDF' not in content[:1024]:
        cuerpo = content.decode('utf-8', errors='replace') if content else ''
        return Response(
            {"error": "El portal de Previsora no devolvió un PDF.", "detalle": cuerpo[:2000]},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    filename = f"previsora_{placa}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf = _guardar_pdf_descargado(finalizado, content, filename, 'PDF Previsora (descarga automática)', request.user)
    return Response(serialize_pdf(pdf, request), status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('finalizados_tramites', 'create')])
def descargar_pdf_mundial(request, pk):
    """
    Descarga el PDF de Mundial desde S3 (donde lo deja el proceso de correo
    automático) y lo adjunta al finalizado. Busca por placa dentro del prefijo
    configurado y toma el objeto más reciente.
    Solo permitido dentro de la ventana de 5 min tras confirmar el pago.
    """
    finalizado = get_object_or_404(TramiteFinalizado.objects, pk=pk)

    err = _ventana_descarga_error(finalizado)
    if err:
        return err

    placa = (finalizado.placa or '').strip()
    if not placa:
        return Response({"error": "El finalizado no tiene placa para buscar el PDF en S3."}, status=status.HTTP_400_BAD_REQUEST)

    bucket = getattr(settings, 'AWS_S3_BUCKET', '')
    if not bucket:
        return Response({"error": "El almacenamiento S3 no está configurado (AWS_S3_BUCKET)."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        import boto3
    except ImportError:
        return Response({"error": "Falta la dependencia 'boto3' en el backend para acceder a S3."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    prefijo = getattr(settings, 'AWS_S3_MUNDIAL_PREFIX', '') or ''
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', '') or None,
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', '') or None,
            region_name=getattr(settings, 'AWS_S3_REGION', 'us-east-1'),
        )

        # Buscar el objeto más reciente cuya key contenga la placa (case-insensitive).
        placa_low = placa.lower()
        mejor = None  # (LastModified, Key)
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=prefijo):
            for obj in page.get('Contents', []):
                if placa_low in obj['Key'].lower():
                    if mejor is None or obj['LastModified'] > mejor[0]:
                        mejor = (obj['LastModified'], obj['Key'])

        if not mejor:
            return Response(
                {"error": f"No se encontró el PDF de Mundial en S3 para la placa {placa}. Verifica que el correo automático ya lo haya almacenado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        key = mejor[1]
        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj['Body'].read()
    except Exception as e:
        return Response({"error": f"Error al obtener el PDF de Mundial desde S3: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    if not content:
        return Response({"error": "El objeto en S3 está vacío."}, status=status.HTTP_502_BAD_GATEWAY)

    filename = f"mundial_{placa}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf = _guardar_pdf_descargado(finalizado, content, filename, 'PDF Mundial (descarga automática desde S3)', request.user)
    return Response(serialize_pdf(pdf, request), status=status.HTTP_201_CREATED)
