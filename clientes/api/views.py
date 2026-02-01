import json
import ast

from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q, Count, Prefetch
from datetime import datetime

from clientes.models import Cliente, MedioComunicacion, PrecioCliente
from .permissions import RolePermission


def serialize_precio(precio):
    """Convierte un objeto PrecioCliente a diccionario"""
    return {
        'id': precio.id,
        'descripcion': precio.descripcion,
        'precio_lay': str(precio.precio_lay),
        'comision': str(precio.comision),
        'created_at': precio.created_at,
        'updated_at': precio.updated_at,
    }


def serialize_cliente(cliente, include_precios=True, include_precios_info=False, precios_prefetched=False):
    """Convierte un objeto Cliente a diccionario"""
    data = {
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
    if include_precios:
        # Si los precios ya están prefetcheados (filtrados), usar .all()
        if precios_prefetched:
            data['precios'] = [serialize_precio(p) for p in cliente.precios.all()]
        else:
            data['precios'] = [serialize_precio(p) for p in cliente.precios.filter(deleted_at__isnull=True)]
    if include_precios_info:
        # Usar la anotación si está disponible, sino calcular
        if hasattr(cliente, 'precios_count'):
            data['precios_count'] = cliente.precios_count
            data['tiene_precios'] = cliente.precios_count > 0
        else:
            count = cliente.precios.filter(deleted_at__isnull=True).count()
            data['precios_count'] = count
            data['tiene_precios'] = count > 0
    return data


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def create_client(request):
    """Crear un nuevo cliente con sus precios"""
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
        precios_data = request.data.get('precios', [])

        # Si precios_data viene como string (multipart/form-data), parsearlo
        if isinstance(precios_data, str):
            try:
                # Intentar primero con JSON estándar (comillas dobles)
                precios_data = json.loads(precios_data)
            except json.JSONDecodeError:
                try:
                    # Si falla, intentar con sintaxis Python (comillas simples)
                    precios_data = ast.literal_eval(precios_data)
                except (ValueError, SyntaxError):
                    return Response(
                        {"error": "El formato de precios es inválido."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

        # Validar medio_comunicacion
        if medio_comunicacion not in [c[0] for c in MedioComunicacion.choices]:
            return Response(
                {"error": f"Medio de comunicacion debe ser: {', '.join([c[0] for c in MedioComunicacion.choices])}"},
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

        # Crear precios asociados al cliente
        for precio_data in precios_data:
            descripcion = precio_data.get('descripcion')
            precio_lay = precio_data.get('precio_lay')
            comision = precio_data.get('comision')

            if descripcion and precio_lay is not None and comision is not None:
                PrecioCliente.objects.create(
                    cliente=cliente,
                    descripcion=descripcion,
                    precio_lay=precio_lay,
                    comision=comision
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
        clientes = Cliente.objects.select_related('usuario', 'created_by').prefetch_related(
            Prefetch('precios', queryset=PrecioCliente.objects.filter(deleted_at__isnull=True))
        ).annotate(
            precios_count=Count('precios', filter=Q(precios__deleted_at__isnull=True))
        )

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

        data = [serialize_cliente(c, include_precios=True, include_precios_info=True, precios_prefetched=True) for c in paginated_clientes]
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

        # Manejar precios si se envían
        precios_data = request.data.get('precios', None)
        if precios_data is not None:
            # Si precios_data viene como string (multipart/form-data), parsearlo
            if isinstance(precios_data, str):
                try:
                    precios_data = json.loads(precios_data)
                except json.JSONDecodeError:
                    try:
                        precios_data = ast.literal_eval(precios_data)
                    except (ValueError, SyntaxError):
                        return Response(
                            {"error": "El formato de precios es inválido."},
                            status=status.HTTP_400_BAD_REQUEST
                        )

            for precio_data in precios_data:
                precio_id = precio_data.get('id')
                descripcion = precio_data.get('descripcion')
                precio_lay = precio_data.get('precio_lay')
                comision = precio_data.get('comision')

                if precio_id:
                    # Actualizar precio existente
                    try:
                        precio = PrecioCliente.objects.get(pk=precio_id, cliente=cliente)
                        if descripcion:
                            precio.descripcion = descripcion
                        if precio_lay is not None:
                            precio.precio_lay = precio_lay
                        if comision is not None:
                            precio.comision = comision
                        precio.save()
                    except PrecioCliente.DoesNotExist:
                        pass
                else:
                    # Crear nuevo precio
                    if descripcion and precio_lay is not None and comision is not None:
                        PrecioCliente.objects.create(
                            cliente=cliente,
                            descripcion=descripcion,
                            precio_lay=precio_lay,
                            comision=comision
                        )

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


# ==================== PRECIOS CLIENTE ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def add_precio_cliente(request, pk):
    """Agregar un precio a un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)

        descripcion = request.data.get('descripcion')
        precio_lay = request.data.get('precio_lay')
        comision = request.data.get('comision')

        if not descripcion:
            return Response(
                {"error": "La descripcion es requerida."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if precio_lay is None or comision is None:
            return Response(
                {"error": "El precio de ley y la comision son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        precio = PrecioCliente.objects.create(
            cliente=cliente,
            descripcion=descripcion,
            precio_lay=precio_lay,
            comision=comision
        )

        return Response(serialize_precio(precio), status=status.HTTP_201_CREATED)

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
def list_precios_cliente(request, pk):
    """Listar precios de un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        precios = cliente.precios.filter(deleted_at__isnull=True)

        data = [serialize_precio(p) for p in precios]
        return Response(data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener precios: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def update_precio_cliente(request, pk, precio_pk):
    """Actualizar un precio de un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        precio = get_object_or_404(PrecioCliente.objects.filter(cliente=cliente), pk=precio_pk)

        precio.descripcion = request.data.get('descripcion', precio.descripcion)
        precio.precio_lay = request.data.get('precio_lay', precio.precio_lay)
        precio.comision = request.data.get('comision', precio.comision)

        precio.save()

        return Response(serialize_precio(precio), status=status.HTTP_200_OK)

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
def delete_precio_cliente(request, pk, precio_pk):
    """Eliminar un precio de un cliente (soft delete)"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        precio = get_object_or_404(PrecioCliente.objects.filter(cliente=cliente), pk=precio_pk)

        from django.utils import timezone
        precio.deleted_at = timezone.now()
        precio.save()

        return Response(
            {"message": "Precio eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar precio: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
