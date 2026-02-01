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

from ..models import CargoNoRegistrado
from tarjetas.models import Tarjeta
from clientes.models import Cliente
from .permissions import RolePermission


def calcular_cuatro_por_mil(valor, tarjeta):
    """Calcula el cuatro por mil si la tarjeta lo tiene activo"""
    if tarjeta.cuatro_por_mil == '1':
        return (Decimal(valor) * Decimal('4')) / Decimal('1000')
    return Decimal('0')


def serialize_cargo_no_registrado(cargo):
    """Convierte un objeto CargoNoRegistrado a diccionario"""
    return {
        'id': cargo.id,
        'usuario': {
            'id': cargo.usuario.id,
            'name': f"{cargo.usuario.first_name} {cargo.usuario.last_name}".strip(),
        } if cargo.usuario else None,
        'cliente': {
            'id': cargo.cliente.id,
            'nombre': cargo.cliente.nombre,
        } if cargo.cliente else None,
        'tarjeta': {
            'id': cargo.tarjeta.id,
            'numero': cargo.tarjeta.numero,
            'titular': cargo.tarjeta.titular,
            'cuatro_por_mil': cargo.tarjeta.cuatro_por_mil,
        } if cargo.tarjeta else None,
        'valor': str(cargo.valor),
        'cuatro_por_mil': str(cargo.cuatro_por_mil),
        'total': str(cargo.total),
        'observacion': cargo.observacion,
        'fecha': cargo.fecha,
        'created_at': cargo.created_at,
        'updated_at': cargo.updated_at,
        'deleted_at': cargo.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_cargo_no_registrado(request):
    """Crear un nuevo cargo no registrado"""
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

        cargo = CargoNoRegistrado.objects.create(
            usuario=request.user,
            cliente=cliente,
            tarjeta=tarjeta,
            valor=valor,
            cuatro_por_mil=cuatro_por_mil,
            total=total,
            observacion=request.data.get('observacion', ''),
            fecha=request.data.get('fecha'),
        )

        return Response(serialize_cargo_no_registrado(cargo), status=status.HTTP_201_CREATED)

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
def list_cargos_no_registrados(request):
    """Listar cargos no registrados con filtros y paginación"""
    try:
        cargos = CargoNoRegistrado.objects.select_related(
            'usuario', 'cliente', 'tarjeta'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            cargos = cargos.filter(
                Q(cliente__nombre__icontains=search_query) |
                Q(tarjeta__numero__icontains=search_query) |
                Q(tarjeta__titular__icontains=search_query) |
                Q(observacion__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            cargos = cargos.filter(cliente_id=cliente_id)

        # Filtro por tarjeta
        tarjeta_id = request.query_params.get('tarjeta', None)
        if tarjeta_id:
            cargos = cargos.filter(tarjeta_id=tarjeta_id)

        # Filtro por usuario
        usuario_id = request.query_params.get('usuario', None)
        if usuario_id:
            cargos = cargos.filter(usuario_id=usuario_id)

        # Filtro por fecha
        fecha_start = request.query_params.get('fecha_start', None)
        fecha_end = request.query_params.get('fecha_end', None)

        if fecha_start:
            try:
                start_date = datetime.strptime(fecha_start, '%Y-%m-%d').date()
                cargos = cargos.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de fecha_start debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if fecha_end:
            try:
                end_date = datetime.strptime(fecha_end, '%Y-%m-%d').date()
                cargos = cargos.filter(fecha__lte=end_date)
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
                cargos = cargos.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                cargos = cargos.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            cargos = cargos.filter(deleted_at__isnull=True)

        # Ordenar
        cargos = cargos.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_cargos = paginator.paginate_queryset(cargos, request)

        data = [serialize_cargo_no_registrado(c) for c in paginated_cargos]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener cargos no registrados: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_cargo_no_registrado(request, pk):
    """Obtener un cargo no registrado por ID"""
    try:
        cargo = get_object_or_404(
            CargoNoRegistrado.objects.select_related('usuario', 'cliente', 'tarjeta'),
            pk=pk
        )
        return Response(serialize_cargo_no_registrado(cargo), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener cargo no registrado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def update_cargo_no_registrado(request, pk):
    """Actualizar un cargo no registrado"""
    try:
        cargo = get_object_or_404(CargoNoRegistrado.objects.select_related('tarjeta'), pk=pk)

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
                cargo.cliente = cliente
            except Cliente.DoesNotExist:
                return Response(
                    {"error": "El cliente especificado no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Validar que la tarjeta exista si se proporciona
        tarjeta = cargo.tarjeta
        if 'tarjeta' in request.data:
            tarjeta_id = request.data.get('tarjeta')
            try:
                tarjeta = Tarjeta.objects.get(pk=tarjeta_id)
                if tarjeta.deleted_at is not None:
                    return Response(
                        {"error": "La tarjeta especificada está eliminada."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                cargo.tarjeta = tarjeta
            except Tarjeta.DoesNotExist:
                return Response(
                    {"error": "La tarjeta especificada no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Actualizar otros campos
        cargo.valor = request.data.get('valor', cargo.valor)
        cargo.observacion = request.data.get('observacion', cargo.observacion)
        cargo.fecha = request.data.get('fecha', cargo.fecha)

        # Recalcular cuatro_por_mil y total si cambió valor o tarjeta
        if 'valor' in request.data or 'tarjeta' in request.data:
            valor = Decimal(cargo.valor)
            cargo.cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
            cargo.total = valor + cargo.cuatro_por_mil

        cargo.save()

        return Response(serialize_cargo_no_registrado(cargo), status=status.HTTP_200_OK)

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
def delete_cargo_no_registrado(request, pk):
    """Eliminar un cargo no registrado (soft delete)"""
    try:
        cargo = get_object_or_404(CargoNoRegistrado.objects, pk=pk)
        cargo.soft_delete()
        return Response(
            {"message": "Cargo no registrado eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cargo no registrado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_cargo_no_registrado(request, pk):
    """Restaurar un cargo no registrado eliminado"""
    try:
        cargo = get_object_or_404(CargoNoRegistrado.objects, pk=pk)
        if not cargo.is_deleted:
            return Response(
                {"error": "El cargo no registrado no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        cargo.restore()
        return Response(serialize_cargo_no_registrado(cargo), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar cargo no registrado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_cargo_no_registrado(request, pk):
    """Eliminar permanentemente un cargo no registrado"""
    try:
        cargo = get_object_or_404(CargoNoRegistrado.objects, pk=pk)
        cargo.delete()
        return Response(
            {"message": "Cargo no registrado eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cargo no registrado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def cargo_no_registrado_history(request, pk):
    """Obtener el historial de cambios de un cargo no registrado"""
    try:
        cargo = get_object_or_404(CargoNoRegistrado.objects, pk=pk)
        history = cargo.history.all()

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
