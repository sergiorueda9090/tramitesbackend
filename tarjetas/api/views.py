from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from django.utils import timezone
from datetime import datetime

from ..models import Tarjeta
from .permissions import RolePermission


def serialize_tarjeta(tarjeta):
    """Convierte un objeto Tarjeta a diccionario"""
    return {
        'id': tarjeta.id,
        'usuario': {
            'id': tarjeta.usuario.id,
            'name': f"{tarjeta.usuario.first_name} {tarjeta.usuario.last_name}".strip(),
        } if tarjeta.usuario else None,
        'numero': tarjeta.numero,
        'titular': tarjeta.titular,
        'descripcion': tarjeta.descripcion,
        'cuatro_por_mil': tarjeta.cuatro_por_mil,
        'cuatro_por_mil_display': tarjeta.get_cuatro_por_mil_display(),
        'created_at': tarjeta.created_at,
        'updated_at': tarjeta.updated_at,
        'deleted_at': tarjeta.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_tarjeta(request):
    """Crear una nueva tarjeta"""
    try:
        required_fields = ['numero', 'titular', 'descripcion']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Verificar si el número ya existe
        numero = request.data.get('numero')
        if Tarjeta.objects.filter(numero=numero).exists():
            return Response(
                {"error": "Ya existe una tarjeta con este número."},
                status=status.HTTP_400_BAD_REQUEST
            )

        tarjeta = Tarjeta.objects.create(
            usuario=request.user,
            numero=numero,
            titular=request.data.get('titular'),
            descripcion=request.data.get('descripcion'),
            cuatro_por_mil=request.data.get('cuatro_por_mil', '0'),
        )

        return Response(serialize_tarjeta(tarjeta), status=status.HTTP_201_CREATED)

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
def list_tarjetas(request):
    """Listar tarjetas con filtros y paginación"""
    try:
        tarjetas = Tarjeta.objects.select_related('usuario').all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            tarjetas = tarjetas.filter(
                Q(numero__icontains=search_query) |
                Q(titular__icontains=search_query) |
                Q(descripcion__icontains=search_query)
            )

        # Filtro por cuatro por mil
        cuatro_por_mil = request.query_params.get('cuatro_por_mil', None)
        if cuatro_por_mil:
            tarjetas = tarjetas.filter(cuatro_por_mil=cuatro_por_mil)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                tarjetas = tarjetas.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                tarjetas = tarjetas.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            tarjetas = tarjetas.filter(deleted_at__isnull=True)

        # Ordenar
        tarjetas = tarjetas.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_tarjetas = paginator.paginate_queryset(tarjetas, request)

        data = [serialize_tarjeta(t) for t in paginated_tarjetas]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener tarjetas: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_tarjeta(request, pk):
    """Obtener una tarjeta por ID"""
    try:
        tarjeta = get_object_or_404(
            Tarjeta.objects.select_related('usuario'),
            pk=pk
        )
        return Response(serialize_tarjeta(tarjeta), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener tarjeta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def update_tarjeta(request, pk):
    """Actualizar una tarjeta"""
    try:
        tarjeta = get_object_or_404(Tarjeta.objects, pk=pk)

        # Verificar si el nuevo número ya existe (si se está cambiando)
        nuevo_numero = request.data.get('numero')
        if nuevo_numero and nuevo_numero != tarjeta.numero:
            if Tarjeta.objects.filter(numero=nuevo_numero).exists():
                return Response(
                    {"error": "Ya existe una tarjeta con este número."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            tarjeta.numero = nuevo_numero

        tarjeta.titular = request.data.get('titular', tarjeta.titular)
        tarjeta.descripcion = request.data.get('descripcion', tarjeta.descripcion)
        tarjeta.cuatro_por_mil = request.data.get('cuatro_por_mil', tarjeta.cuatro_por_mil)

        tarjeta.save()

        return Response(serialize_tarjeta(tarjeta), status=status.HTTP_200_OK)

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
def delete_tarjeta(request, pk):
    """Eliminar una tarjeta (soft delete)"""
    try:
        tarjeta = get_object_or_404(Tarjeta.objects, pk=pk)
        tarjeta.deleted_at = timezone.now()
        tarjeta.save()
        return Response(
            {"message": "Tarjeta eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar tarjeta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_tarjeta(request, pk):
    """Restaurar una tarjeta eliminada"""
    try:
        tarjeta = get_object_or_404(Tarjeta.objects, pk=pk)
        if tarjeta.deleted_at is None:
            return Response(
                {"error": "La tarjeta no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )
        tarjeta.deleted_at = None
        tarjeta.save()
        return Response(serialize_tarjeta(tarjeta), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar tarjeta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_tarjeta(request, pk):
    """Eliminar permanentemente una tarjeta"""
    try:
        tarjeta = get_object_or_404(Tarjeta.objects, pk=pk)
        tarjeta.delete()
        return Response(
            {"message": "Tarjeta eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar tarjeta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def tarjeta_history(request, pk):
    """Obtener el historial de cambios de una tarjeta"""
    try:
        tarjeta = get_object_or_404(Tarjeta.objects, pk=pk)
        history = tarjeta.history.all()

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
                'numero': h.numero,
                'titular': h.titular,
                'descripcion': h.descripcion,
                'cuatro_por_mil': h.cuatro_por_mil,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
