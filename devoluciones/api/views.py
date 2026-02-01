from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime
from decimal import Decimal

from ..models import Devolucion
from tarjetas.models import Tarjeta
from clientes.models import Cliente
from .permissions import RolePermission


def calcular_cuatro_por_mil(valor, tarjeta):
    """Calcula el cuatro por mil si la tarjeta lo tiene activo"""
    if tarjeta.cuatro_por_mil == '1':
        return (Decimal(valor) * Decimal('4')) / Decimal('1000')
    return Decimal('0')


def serialize_devolucion(devolucion):
    """Convierte un objeto Devolucion a diccionario"""
    return {
        'id': devolucion.id,
        'usuario': {
            'id': devolucion.usuario.id,
            'name': f"{devolucion.usuario.first_name} {devolucion.usuario.last_name}".strip(),
        } if devolucion.usuario else None,
        'cliente': {
            'id': devolucion.cliente.id,
            'nombre': devolucion.cliente.nombre,
        } if devolucion.cliente else None,
        'tarjeta': {
            'id': devolucion.tarjeta.id,
            'numero': devolucion.tarjeta.numero,
            'titular': devolucion.tarjeta.titular,
            'cuatro_por_mil': devolucion.tarjeta.cuatro_por_mil,
        } if devolucion.tarjeta else None,
        'valor': str(devolucion.valor),
        'cuatro_por_mil': str(devolucion.cuatro_por_mil),
        'total': str(devolucion.total),
        'observacion': devolucion.observacion,
        'fecha': devolucion.fecha,
        'created_at': devolucion.created_at,
        'updated_at': devolucion.updated_at,
        'deleted_at': devolucion.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_devolucion(request):
    """Crear una nueva devolución"""
    try:
        required_fields = ['cliente', 'tarjeta', 'valor', 'fecha']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Validar que el usuario exista
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Usuario no autenticado."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Validar que el cliente exista
        cliente_id = request.data.get('cliente')
        try:
            cliente = Cliente.objects.get(pk=cliente_id)
            if cliente.deleted_at is not None:
                return Response(
                    {"error": "El cliente especificado está eliminado."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Cliente.DoesNotExist:
            return Response(
                {"error": "El cliente especificado no existe."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Validar que la tarjeta exista
        tarjeta_id = request.data.get('tarjeta')
        try:
            tarjeta = Tarjeta.objects.get(pk=tarjeta_id)
            if tarjeta.deleted_at is not None:
                return Response(
                    {"error": "La tarjeta especificada está eliminada."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Tarjeta.DoesNotExist:
            return Response(
                {"error": "La tarjeta especificada no existe."},
                status=status.HTTP_404_NOT_FOUND
            )

        valor = Decimal(request.data.get('valor'))
        cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
        total = valor + cuatro_por_mil

        devolucion = Devolucion.objects.create(
            usuario=request.user,
            cliente=cliente,
            tarjeta=tarjeta,
            valor=valor,
            cuatro_por_mil=cuatro_por_mil,
            total=total,
            observacion=request.data.get('observacion', ''),
            fecha=request.data.get('fecha'),
        )

        return Response(serialize_devolucion(devolucion), status=status.HTTP_201_CREATED)

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
def list_devoluciones(request):
    """Listar devoluciones con filtros y paginación"""
    try:
        devoluciones = Devolucion.objects.select_related(
            'usuario', 'cliente', 'tarjeta'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            devoluciones = devoluciones.filter(
                Q(cliente__nombre__icontains=search_query) |
                Q(tarjeta__numero__icontains=search_query) |
                Q(tarjeta__titular__icontains=search_query) |
                Q(observacion__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            devoluciones = devoluciones.filter(cliente_id=cliente_id)

        # Filtro por tarjeta
        tarjeta_id = request.query_params.get('tarjeta', None)
        if tarjeta_id:
            devoluciones = devoluciones.filter(tarjeta_id=tarjeta_id)

        # Filtro por usuario
        usuario_id = request.query_params.get('usuario', None)
        if usuario_id:
            devoluciones = devoluciones.filter(usuario_id=usuario_id)

        # Filtro por fecha
        fecha_start = request.query_params.get('fecha_start', None)
        fecha_end = request.query_params.get('fecha_end', None)

        if fecha_start:
            try:
                start_date = datetime.strptime(fecha_start, '%Y-%m-%d').date()
                devoluciones = devoluciones.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de fecha_start debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if fecha_end:
            try:
                end_date = datetime.strptime(fecha_end, '%Y-%m-%d').date()
                devoluciones = devoluciones.filter(fecha__lte=end_date)
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
                devoluciones = devoluciones.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                devoluciones = devoluciones.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            devoluciones = devoluciones.filter(deleted_at__isnull=True)

        # Ordenar
        devoluciones = devoluciones.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_devoluciones = paginator.paginate_queryset(devoluciones, request)

        data = [serialize_devolucion(d) for d in paginated_devoluciones]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener devoluciones: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_devolucion(request, pk):
    """Obtener una devolución por ID"""
    try:
        devolucion = get_object_or_404(
            Devolucion.objects.select_related('usuario', 'cliente', 'tarjeta'),
            pk=pk
        )
        return Response(serialize_devolucion(devolucion), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener devolución: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def update_devolucion(request, pk):
    """Actualizar una devolución"""
    try:
        devolucion = get_object_or_404(Devolucion.objects.select_related('tarjeta'), pk=pk)

        # Validar que el cliente exista si se proporciona
        if 'cliente' in request.data:
            cliente_id = request.data.get('cliente')
            try:
                cliente = Cliente.objects.get(pk=cliente_id)
                if cliente.deleted_at is not None:
                    return Response(
                        {"error": "El cliente especificado está eliminado."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                devolucion.cliente = cliente
            except Cliente.DoesNotExist:
                return Response(
                    {"error": "El cliente especificado no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Validar que la tarjeta exista si se proporciona
        tarjeta = devolucion.tarjeta
        if 'tarjeta' in request.data:
            tarjeta_id = request.data.get('tarjeta')
            try:
                tarjeta = Tarjeta.objects.get(pk=tarjeta_id)
                if tarjeta.deleted_at is not None:
                    return Response(
                        {"error": "La tarjeta especificada está eliminada."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                devolucion.tarjeta = tarjeta
            except Tarjeta.DoesNotExist:
                return Response(
                    {"error": "La tarjeta especificada no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Actualizar otros campos
        devolucion.valor = request.data.get('valor', devolucion.valor)
        devolucion.observacion = request.data.get('observacion', devolucion.observacion)
        devolucion.fecha = request.data.get('fecha', devolucion.fecha)

        # Recalcular cuatro_por_mil y total si cambió valor o tarjeta
        if 'valor' in request.data or 'tarjeta' in request.data:
            valor = Decimal(devolucion.valor)
            devolucion.cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
            devolucion.total = valor + devolucion.cuatro_por_mil

        devolucion.save()

        return Response(serialize_devolucion(devolucion), status=status.HTTP_200_OK)

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
def delete_devolucion(request, pk):
    """Eliminar una devolución (soft delete)"""
    try:
        devolucion = get_object_or_404(Devolucion.objects, pk=pk)
        devolucion.soft_delete()
        return Response(
            {"message": "Devolución eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar devolución: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_devolucion(request, pk):
    """Restaurar una devolución eliminada"""
    try:
        devolucion = get_object_or_404(Devolucion.objects, pk=pk)
        if not devolucion.is_deleted:
            return Response(
                {"error": "La devolución no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )
        devolucion.restore()
        return Response(serialize_devolucion(devolucion), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar devolución: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_devolucion(request, pk):
    """Eliminar permanentemente una devolución"""
    try:
        devolucion = get_object_or_404(Devolucion.objects, pk=pk)
        devolucion.delete()
        return Response(
            {"message": "Devolución eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar devolución: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def devolucion_history(request, pk):
    """Obtener el historial de cambios de una devolución"""
    try:
        devolucion = get_object_or_404(Devolucion.objects, pk=pk)
        history = devolucion.history.all()

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
                'cuatro_por_mil': str(h.cuatro_por_mil),
                'total': str(h.total),
                'observacion': h.observacion,
                'fecha': h.fecha,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
