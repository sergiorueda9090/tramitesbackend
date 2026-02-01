from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from ..models import AjusteDeSaldo
from .permissions import RolePermission


def serialize_ajuste_de_saldo(ajuste):
    """Convierte un objeto AjusteDeSaldo a diccionario"""
    return {
        'id': ajuste.id,
        'usuario': {
            'id': ajuste.usuario.id,
            'name': f"{ajuste.usuario.first_name} {ajuste.usuario.last_name}".strip(),
        } if ajuste.usuario else None,
        'cliente': {
            'id': ajuste.cliente.id,
            'nombre': ajuste.cliente.nombre,
        } if ajuste.cliente else None,
        'valor': str(ajuste.valor),
        'observacion': ajuste.observacion,
        'fecha': ajuste.fecha,
        'created_at': ajuste.created_at,
        'updated_at': ajuste.updated_at,
        'deleted_at': ajuste.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_ajuste_de_saldo(request):
    """Crear un nuevo ajuste de saldo"""
    try:
        required_fields = ['cliente', 'valor', 'fecha']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        ajuste = AjusteDeSaldo.objects.create(
            usuario=request.user,
            cliente_id=request.data.get('cliente'),
            valor=request.data.get('valor'),
            observacion=request.data.get('observacion', ''),
            fecha=request.data.get('fecha'),
        )

        return Response(serialize_ajuste_de_saldo(ajuste), status=status.HTTP_201_CREATED)

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
def list_ajustes_de_saldo(request):
    """Listar ajustes de saldo con filtros y paginación"""
    try:
        ajustes = AjusteDeSaldo.objects.select_related(
            'usuario', 'cliente'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            ajustes = ajustes.filter(
                Q(cliente__nombre__icontains=search_query) |
                Q(observacion__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            ajustes = ajustes.filter(cliente_id=cliente_id)

        # Filtro por usuario
        usuario_id = request.query_params.get('usuario', None)
        if usuario_id:
            ajustes = ajustes.filter(usuario_id=usuario_id)

        # Filtro por fecha
        fecha_start = request.query_params.get('fecha_start', None)
        fecha_end = request.query_params.get('fecha_end', None)

        if fecha_start:
            try:
                start_date = datetime.strptime(fecha_start, '%Y-%m-%d').date()
                ajustes = ajustes.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de fecha_start debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if fecha_end:
            try:
                end_date = datetime.strptime(fecha_end, '%Y-%m-%d').date()
                ajustes = ajustes.filter(fecha__lte=end_date)
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
                ajustes = ajustes.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                ajustes = ajustes.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            ajustes = ajustes.filter(deleted_at__isnull=True)

        # Ordenar
        ajustes = ajustes.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_ajustes = paginator.paginate_queryset(ajustes, request)

        data = [serialize_ajuste_de_saldo(a) for a in paginated_ajustes]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener ajustes de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_ajuste_de_saldo(request, pk):
    """Obtener un ajuste de saldo por ID"""
    try:
        ajuste = get_object_or_404(
            AjusteDeSaldo.objects.select_related('usuario', 'cliente'),
            pk=pk
        )
        return Response(serialize_ajuste_de_saldo(ajuste), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener ajuste de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def update_ajuste_de_saldo(request, pk):
    """Actualizar un ajuste de saldo"""
    try:
        ajuste = get_object_or_404(AjusteDeSaldo.objects, pk=pk)

        # Actualizar FK si se proporciona
        if 'cliente' in request.data:
            ajuste.cliente_id = request.data.get('cliente')

        # Actualizar otros campos
        ajuste.valor = request.data.get('valor', ajuste.valor)
        ajuste.observacion = request.data.get('observacion', ajuste.observacion)
        ajuste.fecha = request.data.get('fecha', ajuste.fecha)

        ajuste.save()

        return Response(serialize_ajuste_de_saldo(ajuste), status=status.HTTP_200_OK)

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
def delete_ajuste_de_saldo(request, pk):
    """Eliminar un ajuste de saldo (soft delete)"""
    try:
        ajuste = get_object_or_404(AjusteDeSaldo.objects, pk=pk)
        ajuste.soft_delete()
        return Response(
            {"message": "Ajuste de saldo eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar ajuste de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_ajuste_de_saldo(request, pk):
    """Restaurar un ajuste de saldo eliminado"""
    try:
        ajuste = get_object_or_404(AjusteDeSaldo.objects, pk=pk)
        if not ajuste.is_deleted:
            return Response(
                {"error": "El ajuste de saldo no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        ajuste.restore()
        return Response(serialize_ajuste_de_saldo(ajuste), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar ajuste de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_ajuste_de_saldo(request, pk):
    """Eliminar permanentemente un ajuste de saldo"""
    try:
        ajuste = get_object_or_404(AjusteDeSaldo.objects, pk=pk)
        ajuste.delete()
        return Response(
            {"message": "Ajuste de saldo eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar ajuste de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def ajuste_de_saldo_history(request, pk):
    """Obtener el historial de cambios de un ajuste de saldo"""
    try:
        ajuste = get_object_or_404(AjusteDeSaldo.objects, pk=pk)
        history = ajuste.history.all()

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
