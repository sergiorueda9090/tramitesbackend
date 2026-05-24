from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from utilidades.models import Utilidad
from .permissions import RolePermission, ModulePermission


def serialize_utilidad(utilidad):
    """Serialización pública: campos del reporte de utilidad + d/c/sub-cuenta."""
    return {
        'id':                 utilidad.id,
        'fecha':              utilidad.fecha,
        'placa':              utilidad.placa,
        'comision_proveedor': utilidad.comision_proveedor,
        'cilindraje':         utilidad.cilindraje,
        'modelo':             utilidad.modelo,
        'chasis':             utilidad.chasis,
        'debito':             str(utilidad.debito),
        'credito':            str(utilidad.credito),
        'sub_cuenta':         utilidad.sub_cuenta_id,
        'sub_cuenta_codigo':  utilidad.sub_cuenta.codigo if utilidad.sub_cuenta else None,
        'sub_cuenta_nombre':  utilidad.sub_cuenta.nombre_sub_cuenta if utilidad.sub_cuenta else None,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('utilidades', 'view')])
def list_utilidades(request):
    """Listar utilidades con filtros y paginación."""
    try:
        utilidades = Utilidad.objects.all()

        # Búsqueda libre sobre los campos del reporte
        search = request.query_params.get('search')
        if search:
            utilidades = utilidades.filter(
                Q(placa__icontains=search) |
                Q(cilindraje__icontains=search) |
                Q(modelo__icontains=search) |
                Q(chasis__icontains=search)
            )

        # Rango de fechas (sobre el campo `fecha`)
        start_date_str = request.query_params.get('start_date')
        end_date_str   = request.query_params.get('end_date')

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                utilidades = utilidades.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                utilidades = utilidades.filter(fecha__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Soft-delete: por defecto excluir borrados
        include_deleted = request.query_params.get('include_deleted')
        if include_deleted != '1':
            utilidades = utilidades.filter(deleted_at__isnull=True)

        utilidades = utilidades.order_by('-fecha', '-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(utilidades, request)

        data = [serialize_utilidad(u) for u in paginated]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener utilidades: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('utilidades', 'view')])
def get_utilidad(request, pk):
    """Obtener una utilidad por ID (solo los 6 campos del reporte)."""
    try:
        utilidad = get_object_or_404(Utilidad.objects, pk=pk)
        return Response(serialize_utilidad(utilidad), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener utilidad: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('utilidades', 'delete')])
def delete_utilidad(request, pk):
    """Eliminar una utilidad (soft delete)."""
    try:
        utilidad = get_object_or_404(Utilidad.objects, pk=pk)
        utilidad.soft_delete()
        return Response(
            {"message": "Utilidad eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar utilidad: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('utilidades', 'delete')])
def restore_utilidad(request, pk):
    """Restaurar una utilidad eliminada."""
    try:
        utilidad = get_object_or_404(Utilidad.objects, pk=pk)
        if not utilidad.is_deleted:
            return Response(
                {"error": "La utilidad no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )
        utilidad.restore()
        return Response(serialize_utilidad(utilidad), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar utilidad: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('utilidades', 'delete')])
def hard_delete_utilidad(request, pk):
    """Eliminar permanentemente una utilidad."""
    try:
        utilidad = get_object_or_404(Utilidad.objects, pk=pk)
        utilidad.delete()
        return Response(
            {"message": "Utilidad eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar utilidad: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('utilidades', 'view')])
def utilidad_history(request, pk):
    """Obtener el historial de cambios de una utilidad."""
    try:
        utilidad = get_object_or_404(Utilidad.objects, pk=pk)
        history = utilidad.history.all()

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
                'history_id':   h.history_id,
                'history_date': h.history_date,
                'history_type': h.history_type,
                'history_type_display': h.get_history_type_display(),
                'history_user': {
                    'id': h.history_user.id,
                    'username': h.history_user.username,
                    'name': f"{h.history_user.first_name} {h.history_user.last_name}".strip()
                } if h.history_user else None,
                'fecha':              h.fecha,
                'placa':              h.placa,
                'comision_proveedor': h.comision_proveedor,
                'cilindraje':         h.cilindraje,
                'modelo':             h.modelo,
                'chasis':             h.chasis,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
