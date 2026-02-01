from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from proveedores.models import Proveedor
from etiquetas.models import Etiqueta
from .permissions import RolePermission


def serialize_proveedor(proveedor):
    """Convierte un objeto Proveedor a diccionario"""
    return {
        'id': proveedor.id,
        'nombre': proveedor.nombre,
        'color': proveedor.color,
        'user': proveedor.user_id,
        'user_name': f"{proveedor.user.first_name} {proveedor.user.last_name}".strip() if proveedor.user else None,
        'etiqueta': proveedor.etiqueta_id,
        'etiqueta_nombre': proveedor.etiqueta.nombre if proveedor.etiqueta else None,
        'etiqueta_color': proveedor.etiqueta.color if proveedor.etiqueta else None,
        'created_at': proveedor.created_at,
        'updated_at': proveedor.updated_at,
        'deleted_at': proveedor.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def create_proveedor(request):
    """Crear un nuevo proveedor"""
    try:
        nombre = request.data.get('nombre')
        if not nombre:
            return Response(
                {"error": "El nombre es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        color = request.data.get('color', '#1976d2')
        etiqueta_id = request.data.get('etiqueta')

        etiqueta = None
        if etiqueta_id:
            etiqueta = get_object_or_404(Etiqueta, pk=etiqueta_id)

        proveedor = Proveedor.objects.create(
            nombre=nombre,
            color=color,
            user=request.user,
            etiqueta=etiqueta
        )

        return Response(serialize_proveedor(proveedor), status=status.HTTP_201_CREATED)

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
def list_proveedores(request):
    """Listar proveedores con filtros y paginacion"""
    try:
        proveedores = Proveedor.objects.select_related('user', 'etiqueta').all()

        # Filtro de busqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            proveedores = proveedores.filter(nombre__icontains=search_query)

        # Filtro por etiqueta
        etiqueta_id = request.query_params.get('etiqueta', None)
        if etiqueta_id:
            proveedores = proveedores.filter(etiqueta_id=etiqueta_id)

        # Filtro por fecha de creacion
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                proveedores = proveedores.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                proveedores = proveedores.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            proveedores = proveedores.filter(deleted_at__isnull=True)

        # Ordenar
        proveedores = proveedores.order_by('-created_at')

        # Paginacion
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_proveedores = paginator.paginate_queryset(proveedores, request)

        data = [serialize_proveedor(p) for p in paginated_proveedores]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener proveedores: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_proveedor(request, pk):
    """Obtener un proveedor por ID"""
    try:
        proveedor = get_object_or_404(Proveedor.objects.select_related('user', 'etiqueta'), pk=pk)
        return Response(serialize_proveedor(proveedor), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener proveedor: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def update_proveedor(request, pk):
    """Actualizar un proveedor"""
    try:
        proveedor = get_object_or_404(Proveedor.objects, pk=pk)

        proveedor.nombre = request.data.get('nombre', proveedor.nombre)
        proveedor.color = request.data.get('color', proveedor.color)

        etiqueta_id = request.data.get('etiqueta')
        if etiqueta_id is not None:
            if etiqueta_id:
                proveedor.etiqueta = get_object_or_404(Etiqueta, pk=etiqueta_id)
            else:
                proveedor.etiqueta = None

        proveedor.save()

        return Response(serialize_proveedor(proveedor), status=status.HTTP_200_OK)

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
def delete_proveedor(request, pk):
    """Eliminar un proveedor (soft delete)"""
    try:
        proveedor = get_object_or_404(Proveedor.objects, pk=pk)
        proveedor.soft_delete()
        return Response(
            {"message": "Proveedor eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar proveedor: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_proveedor(request, pk):
    """Restaurar un proveedor eliminado"""
    try:
        proveedor = get_object_or_404(Proveedor.objects, pk=pk)
        if not proveedor.is_deleted:
            return Response(
                {"error": "El proveedor no esta eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        proveedor.restore()
        return Response(serialize_proveedor(proveedor), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar proveedor: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_proveedor(request, pk):
    """Eliminar permanentemente un proveedor"""
    try:
        proveedor = get_object_or_404(Proveedor.objects, pk=pk)
        proveedor.delete()
        return Response(
            {"message": "Proveedor eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar proveedor: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def proveedor_history(request, pk):
    """Obtener el historial de cambios de un proveedor"""
    try:
        proveedor = get_object_or_404(Proveedor.objects, pk=pk)
        history = proveedor.history.all()

        # Paginacion
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
                'etiqueta': h.etiqueta_id,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
