from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from clientes.models import Cliente, MedioComunicacion
from .permissions import RolePermission


def serialize_cliente(cliente):
    """Convierte un objeto Cliente a diccionario"""
    return {
        'id': cliente.id,
        'color': cliente.color,
        'nombre': cliente.nombre,
        'telefono': cliente.telefono,
        'direccion': cliente.direccion,
        'usuario': cliente.usuario_id,
        'usuario_name': f"{cliente.usuario.first_name} {cliente.usuario.last_name}".strip() if cliente.usuario else None,
        'medio_comunicacion': cliente.medio_comunicacion,
        'medio_comunicacion_display': cliente.get_medio_comunicacion_display(),
        'created_by': cliente.created_by_id,
        'created_by_name': f"{cliente.created_by.first_name} {cliente.created_by.last_name}".strip() if cliente.created_by else None,
        'created_at': cliente.created_at,
        'updated_at': cliente.updated_at,
        'deleted_at': cliente.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def create_client(request):
    """Crear un nuevo cliente"""
    try:
        nombre = request.data.get('nombre')
        if not nombre:
            return Response(
                {"error": "El nombre es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        color = request.data.get('color', '#1976d2')
        telefono = request.data.get('telefono', '')
        direccion = request.data.get('direccion', '')
        medio_comunicacion = request.data.get('medio_comunicacion', MedioComunicacion.EMAIL)

        # Validar medio_comunicacion
        if medio_comunicacion not in [c[0] for c in MedioComunicacion.choices]:
            return Response(
                {"error": f"Medio de comunicación debe ser: {', '.join([c[0] for c in MedioComunicacion.choices])}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        cliente = Cliente.objects.create(
            color=color,
            nombre=nombre,
            telefono=telefono,
            direccion=direccion,
            usuario=request.user,
            medio_comunicacion=medio_comunicacion,
            created_by=request.user
        )

        return Response(serialize_cliente(cliente), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'auxiliar', 'vendedor'])])
def list_clients(request):
    """Listar clientes con filtros y paginación"""
    try:
        clientes = Cliente.objects.select_related('usuario', 'created_by').all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            clientes = clientes.filter(
                Q(nombre__icontains=search_query) |
                Q(telefono__icontains=search_query) |
                Q(direccion__icontains=search_query)
            )

        # Filtro por medio de comunicación
        medio_filter = request.query_params.get('medio_comunicacion', None)
        if medio_filter:
            clientes = clientes.filter(medio_comunicacion=medio_filter)

        # Filtro por usuario asignado
        usuario_filter = request.query_params.get('usuario', None)
        if usuario_filter:
            clientes = clientes.filter(usuario_id=usuario_filter)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                clientes = clientes.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                clientes = clientes.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            clientes = clientes.filter(deleted_at__isnull=True)

        # Ordenar
        clientes = clientes.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_clientes = paginator.paginate_queryset(clientes, request)

        data = [serialize_cliente(c) for c in paginated_clientes]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener clientes: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'auxiliar', 'vendedor'])])
def get_client(request, pk):
    """Obtener un cliente por ID"""
    try:
        cliente = get_object_or_404(Cliente.objects.select_related('usuario', 'created_by'), pk=pk)
        return Response(serialize_cliente(cliente), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener cliente: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def update_client(request, pk):
    """Actualizar un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)

        cliente.nombre = request.data.get('nombre', cliente.nombre)
        cliente.telefono = request.data.get('telefono', cliente.telefono)
        cliente.direccion = request.data.get('direccion', cliente.direccion)
        cliente.color = request.data.get('color', cliente.color)

        medio_comunicacion = request.data.get('medio_comunicacion', cliente.medio_comunicacion)
        if medio_comunicacion not in [c[0] for c in MedioComunicacion.choices]:
            return Response(
                {"error": f"Medio de comunicación debe ser: {', '.join([c[0] for c in MedioComunicacion.choices])}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        cliente.medio_comunicacion = medio_comunicacion

        cliente.save()

        return Response(serialize_cliente(cliente), status=status.HTTP_200_OK)

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
def delete_client(request, pk):
    """Eliminar un cliente (soft delete)"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        cliente.soft_delete()
        return Response(
            {"message": "Cliente eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cliente: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_client(request, pk):
    """Restaurar un cliente eliminado"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        if not cliente.is_deleted:
            return Response(
                {"error": "El cliente no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        cliente.restore()
        return Response(serialize_cliente(cliente), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar cliente: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_client(request, pk):
    """Eliminar permanentemente un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        cliente.delete()
        return Response(
            {"message": "Cliente eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cliente: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def client_history(request, pk):
    """Obtener el historial de cambios de un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        history = cliente.history.all()

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
                'telefono': h.telefono,
                'direccion': h.direccion,
                'color': h.color,
                'medio_comunicacion': h.medio_comunicacion,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
