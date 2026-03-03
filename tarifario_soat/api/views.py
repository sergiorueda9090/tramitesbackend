from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from ..models import TarifarioSoat
from .permissions import RolePermission


def serialize_tarifario(tarifario):
    """Convierte un objeto TarifarioSoat a diccionario"""
    return {
        'id': tarifario.id,
        'user': {
            'id': tarifario.user.id,
            'name': f"{tarifario.user.first_name} {tarifario.user.last_name}".strip(),
        } if tarifario.user else None,
        'codigo_tarifa': tarifario.codigo_tarifa,
        'descripcion': tarifario.descripcion,
        'valor': str(tarifario.valor),
        'created_at': tarifario.created_at,
        'updated_at': tarifario.updated_at,
        'deleted_at': tarifario.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_tarifario(request):
    """Crear un nuevo tarifario SOAT"""
    try:
        required_fields = ['codigo_tarifa', 'descripcion', 'valor']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Usuario no autenticado."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        tarifario = TarifarioSoat.objects.create(
            user=request.user,
            codigo_tarifa=request.data.get('codigo_tarifa'),
            descripcion=request.data.get('descripcion'),
            valor=request.data.get('valor'),
        )

        return Response(serialize_tarifario(tarifario), status=status.HTTP_201_CREATED)

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
def list_tarifarios(request):
    """Listar tarifarios SOAT con filtros y paginación"""
    try:
        tarifarios = TarifarioSoat.objects.select_related('user').all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            tarifarios = tarifarios.filter(
                Q(codigo_tarifa__icontains=search_query) |
                Q(descripcion__icontains=search_query)
            )

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                tarifarios = tarifarios.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                tarifarios = tarifarios.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            tarifarios = tarifarios.filter(deleted_at__isnull=True)

        # Ordenar
        tarifarios = tarifarios.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_tarifarios = paginator.paginate_queryset(tarifarios, request)

        data = [serialize_tarifario(t) for t in paginated_tarifarios]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener tarifarios: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_tarifario(request, pk):
    """Obtener un tarifario SOAT por ID"""
    try:
        tarifario = get_object_or_404(
            TarifarioSoat.objects.select_related('user'),
            pk=pk
        )
        return Response(serialize_tarifario(tarifario), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener tarifario: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def update_tarifario(request, pk):
    """Actualizar un tarifario SOAT"""
    try:
        tarifario = get_object_or_404(TarifarioSoat.objects, pk=pk)

        tarifario.codigo_tarifa = request.data.get('codigo_tarifa', tarifario.codigo_tarifa)
        tarifario.descripcion = request.data.get('descripcion', tarifario.descripcion)
        tarifario.valor = request.data.get('valor', tarifario.valor)

        tarifario.save()

        return Response(serialize_tarifario(tarifario), status=status.HTTP_200_OK)

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
def delete_tarifario(request, pk):
    """Eliminar un tarifario SOAT (soft delete)"""
    try:
        tarifario = get_object_or_404(TarifarioSoat.objects, pk=pk)
        tarifario.soft_delete()
        return Response(
            {"message": "Tarifario SOAT eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar tarifario: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_tarifario(request, pk):
    """Restaurar un tarifario SOAT eliminado"""
    try:
        tarifario = get_object_or_404(TarifarioSoat.objects, pk=pk)
        if not tarifario.is_deleted:
            return Response(
                {"error": "El tarifario no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        tarifario.restore()
        return Response(serialize_tarifario(tarifario), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar tarifario: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_tarifario(request, pk):
    """Eliminar permanentemente un tarifario SOAT"""
    try:
        tarifario = get_object_or_404(TarifarioSoat.objects, pk=pk)
        tarifario.delete()
        return Response(
            {"message": "Tarifario SOAT eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar tarifario: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def tarifario_history(request, pk):
    """Obtener el historial de cambios de un tarifario SOAT"""
    try:
        tarifario = get_object_or_404(TarifarioSoat.objects, pk=pk)
        history = tarifario.history.all()

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
                'codigo_tarifa': h.codigo_tarifa,
                'descripcion': h.descripcion,
                'valor': str(h.valor),
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
