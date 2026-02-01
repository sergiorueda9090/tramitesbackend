from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from ..models import RecepcionPago
from .permissions import RolePermission


def serialize_recepcion_pago(recepcion):
    """Convierte un objeto RecepcionPago a diccionario"""
    return {
        'id': recepcion.id,
        'usuario': {
            'id': recepcion.usuario.id,
            'name': f"{recepcion.usuario.first_name} {recepcion.usuario.last_name}".strip(),
        } if recepcion.usuario else None,
        'cliente': {
            'id': recepcion.cliente.id,
            'nombre': recepcion.cliente.nombre,
        } if recepcion.cliente else None,
        'tarjeta': {
            'id': recepcion.tarjeta.id,
            'numero': recepcion.tarjeta.numero,
            'titular': recepcion.tarjeta.titular,
        } if recepcion.tarjeta else None,
        'valor': str(recepcion.valor),
        'observacion': recepcion.observacion,
        'fecha': recepcion.fecha,
        'created_at': recepcion.created_at,
        'updated_at': recepcion.updated_at,
        'deleted_at': recepcion.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_recepcion_pago(request):
    """Crear una nueva recepción de pago"""
    try:
        required_fields = ['cliente', 'tarjeta', 'valor', 'fecha']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        recepcion = RecepcionPago.objects.create(
            usuario=request.user,
            cliente_id=request.data.get('cliente'),
            tarjeta_id=request.data.get('tarjeta'),
            valor=request.data.get('valor'),
            observacion=request.data.get('observacion', ''),
            fecha=request.data.get('fecha'),
        )

        return Response(serialize_recepcion_pago(recepcion), status=status.HTTP_201_CREATED)

    except DatabaseError as e:
        return Response(
            {"error": f"Error de base de datos: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {"error": f"Error inesperado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_recepciones_pago(request):
    """Listar recepciones de pago con filtros y paginación"""
    try:
        recepciones = RecepcionPago.objects.select_related(
            'usuario', 'cliente', 'tarjeta'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            recepciones = recepciones.filter(
                Q(cliente__nombre__icontains=search_query) |
                Q(tarjeta__numero__icontains=search_query) |
                Q(tarjeta__titular__icontains=search_query) |
                Q(observacion__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            recepciones = recepciones.filter(cliente_id=cliente_id)

        # Filtro por tarjeta
        tarjeta_id = request.query_params.get('tarjeta', None)
        if tarjeta_id:
            recepciones = recepciones.filter(tarjeta_id=tarjeta_id)

        # Filtro por usuario
        usuario_id = request.query_params.get('usuario', None)
        if usuario_id:
            recepciones = recepciones.filter(usuario_id=usuario_id)

        # Filtro por fecha de recepción
        fecha_start = request.query_params.get('fecha_start', None)
        fecha_end = request.query_params.get('fecha_end', None)

        if fecha_start:
            try:
                start_date = datetime.strptime(fecha_start, '%Y-%m-%d').date()
                recepciones = recepciones.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de fecha_start debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if fecha_end:
            try:
                end_date = datetime.strptime(fecha_end, '%Y-%m-%d').date()
                recepciones = recepciones.filter(fecha__lte=end_date)
            except ValueError:
                return Response(
                    {"error": "El formato de fecha_end debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                recepciones = recepciones.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                recepciones = recepciones.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            recepciones = recepciones.filter(deleted_at__isnull=True)

        # Ordenar
        recepciones = recepciones.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_recepciones = paginator.paginate_queryset(recepciones, request)

        data = [serialize_recepcion_pago(r) for r in paginated_recepciones]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener recepciones de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recepcion_pago(request, pk):
    """Obtener una recepción de pago por ID"""
    try:
        recepcion = get_object_or_404(
            RecepcionPago.objects.select_related('usuario', 'cliente', 'tarjeta'),
            pk=pk
        )
        return Response(serialize_recepcion_pago(recepcion), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener recepción de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def update_recepcion_pago(request, pk):
    """Actualizar una recepción de pago"""
    try:
        recepcion = get_object_or_404(RecepcionPago.objects, pk=pk)

        # Actualizar FKs si se proporcionan
        if 'cliente' in request.data:
            recepcion.cliente_id = request.data.get('cliente')
        if 'tarjeta' in request.data:
            recepcion.tarjeta_id = request.data.get('tarjeta')

        # Actualizar otros campos
        recepcion.valor = request.data.get('valor', recepcion.valor)
        recepcion.observacion = request.data.get('observacion', recepcion.observacion)
        recepcion.fecha = request.data.get('fecha', recepcion.fecha)

        recepcion.save()

        return Response(serialize_recepcion_pago(recepcion), status=status.HTTP_200_OK)

    except DatabaseError as e:
        return Response(
            {"error": f"Error de base de datos: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {"error": f"Error inesperado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def delete_recepcion_pago(request, pk):
    """Eliminar una recepción de pago (soft delete)"""
    try:
        recepcion = get_object_or_404(RecepcionPago.objects, pk=pk)
        recepcion.soft_delete()
        return Response(
            {"message": "Recepción de pago eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar recepción de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_recepcion_pago(request, pk):
    """Restaurar una recepción de pago eliminada"""
    try:
        recepcion = get_object_or_404(RecepcionPago.objects, pk=pk)
        if not recepcion.is_deleted:
            return Response(
                {"error": "La recepción de pago no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )
        recepcion.restore()
        return Response(serialize_recepcion_pago(recepcion), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar recepción de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_recepcion_pago(request, pk):
    """Eliminar permanentemente una recepción de pago"""
    try:
        recepcion = get_object_or_404(RecepcionPago.objects, pk=pk)
        recepcion.delete()
        return Response(
            {"message": "Recepción de pago eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar recepción de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def recepcion_pago_history(request, pk):
    """Obtener el historial de cambios de una recepción de pago"""
    try:
        recepcion = get_object_or_404(RecepcionPago.objects, pk=pk)
        history = recepcion.history.all()

        # Paginación
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
                'cliente_id': h.cliente_id,
                'tarjeta_id': h.tarjeta_id,
                'valor': str(h.valor),
                'observacion': h.observacion,
                'fecha': h.fecha,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
