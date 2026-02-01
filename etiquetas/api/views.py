from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from etiquetas.models import Etiqueta
from .permissions import RolePermission


def serialize_etiqueta(etiqueta):
    """Convierte un objeto Etiqueta a diccionario"""
    return {
        'id': etiqueta.id,
        'nombre': etiqueta.nombre,
        'color': etiqueta.color,
        'user': etiqueta.user_id,
        'user_name': f"{etiqueta.user.first_name} {etiqueta.user.last_name}".strip() if etiqueta.user else None,
        'created_at': etiqueta.created_at,
        'updated_at': etiqueta.updated_at,
        'deleted_at': etiqueta.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def create_etiqueta(request):
    """Crear una nueva etiqueta"""
    try:
        nombre = request.data.get('nombre')
        if not nombre:
            return Response(
                {"error": "El nombre es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        color = request.data.get('color', '#1976d2')

        etiqueta = Etiqueta.objects.create(
            nombre=nombre,
            color=color,
            user=request.user
        )

        return Response(serialize_etiqueta(etiqueta), status=status.HTTP_201_CREATED)

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
def list_etiquetas(request):
    """Listar etiquetas con filtros y paginación"""
    try:
        etiquetas = Etiqueta.objects.select_related('user').all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            etiquetas = etiquetas.filter(nombre__icontains=search_query)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                etiquetas = etiquetas.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                etiquetas = etiquetas.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            etiquetas = etiquetas.filter(deleted_at__isnull=True)

        # Ordenar
        etiquetas = etiquetas.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_etiquetas = paginator.paginate_queryset(etiquetas, request)

        data = [serialize_etiqueta(e) for e in paginated_etiquetas]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener etiquetas: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_etiqueta(request, pk):
    """Obtener una etiqueta por ID"""
    try:
        etiqueta = get_object_or_404(Etiqueta.objects.select_related('user'), pk=pk)
        return Response(serialize_etiqueta(etiqueta), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener etiqueta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def update_etiqueta(request, pk):
    """Actualizar una etiqueta"""
    try:
        etiqueta = get_object_or_404(Etiqueta.objects, pk=pk)

        etiqueta.nombre = request.data.get('nombre', etiqueta.nombre)
        etiqueta.color = request.data.get('color', etiqueta.color)

        etiqueta.save()

        return Response(serialize_etiqueta(etiqueta), status=status.HTTP_200_OK)

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
def delete_etiqueta(request, pk):
    """Eliminar una etiqueta (soft delete)"""
    try:
        etiqueta = get_object_or_404(Etiqueta.objects, pk=pk)
        etiqueta.soft_delete()
        return Response(
            {"message": "Etiqueta eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar etiqueta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_etiqueta(request, pk):
    """Restaurar una etiqueta eliminada"""
    try:
        etiqueta = get_object_or_404(Etiqueta.objects, pk=pk)
        if not etiqueta.is_deleted:
            return Response(
                {"error": "La etiqueta no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )
        etiqueta.restore()
        return Response(serialize_etiqueta(etiqueta), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar etiqueta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_etiqueta(request, pk):
    """Eliminar permanentemente una etiqueta"""
    try:
        etiqueta = get_object_or_404(Etiqueta.objects, pk=pk)
        etiqueta.delete()
        return Response(
            {"message": "Etiqueta eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar etiqueta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def etiqueta_history(request, pk):
    """Obtener el historial de cambios de una etiqueta"""
    try:
        etiqueta = get_object_or_404(Etiqueta.objects, pk=pk)
        history = etiqueta.history.all()

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
                    'username': h.history_user.username,
                    'name': f"{h.history_user.first_name} {h.history_user.last_name}".strip()
                } if h.history_user else None,
                'nombre': h.nombre,
                'color': h.color,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
