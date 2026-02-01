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

from ..models import UtilidadOcasional
from tarjetas.models import Tarjeta
from .permissions import RolePermission


def calcular_cuatro_por_mil(valor, tarjeta):
    """Calcula el cuatro por mil si la tarjeta lo tiene activo"""
    if tarjeta.cuatro_por_mil == '1':
        return (Decimal(valor) * Decimal('4')) / Decimal('1000')
    return Decimal('0')


def serialize_utilidad_ocasional(utilidad):
    """Convierte un objeto UtilidadOcasional a diccionario"""
    return {
        'id': utilidad.id,
        'usuario': {
            'id': utilidad.usuario.id,
            'name': f"{utilidad.usuario.first_name} {utilidad.usuario.last_name}".strip(),
        } if utilidad.usuario else None,
        'tarjeta': {
            'id': utilidad.tarjeta.id,
            'numero': utilidad.tarjeta.numero,
            'titular': utilidad.tarjeta.titular,
            'cuatro_por_mil': utilidad.tarjeta.cuatro_por_mil,
        } if utilidad.tarjeta else None,
        'valor': str(utilidad.valor),
        'cuatro_por_mil': str(utilidad.cuatro_por_mil),
        'total': str(utilidad.total),
        'observacion': utilidad.observacion,
        'fecha': utilidad.fecha,
        'created_at': utilidad.created_at,
        'updated_at': utilidad.updated_at,
        'deleted_at': utilidad.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_utilidad_ocasional(request):
    """Crear una nueva utilidad ocasional"""
    try:
        required_fields = ['tarjeta', 'valor', 'fecha']
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

        utilidad = UtilidadOcasional.objects.create(
            usuario=request.user,
            tarjeta=tarjeta,
            valor=valor,
            cuatro_por_mil=cuatro_por_mil,
            total=total,
            observacion=request.data.get('observacion', ''),
            fecha=request.data.get('fecha'),
        )

        return Response(serialize_utilidad_ocasional(utilidad), status=status.HTTP_201_CREATED)

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
def list_utilidades_ocasionales(request):
    """Listar utilidades ocasionales con filtros y paginación"""
    try:
        utilidades = UtilidadOcasional.objects.select_related(
            'usuario', 'tarjeta'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            utilidades = utilidades.filter(
                Q(tarjeta__numero__icontains=search_query) |
                Q(tarjeta__titular__icontains=search_query) |
                Q(observacion__icontains=search_query)
            )

        # Filtro por tarjeta
        tarjeta_id = request.query_params.get('tarjeta', None)
        if tarjeta_id:
            utilidades = utilidades.filter(tarjeta_id=tarjeta_id)

        # Filtro por usuario
        usuario_id = request.query_params.get('usuario', None)
        if usuario_id:
            utilidades = utilidades.filter(usuario_id=usuario_id)

        # Filtro por fecha
        fecha_start = request.query_params.get('fecha_start', None)
        fecha_end = request.query_params.get('fecha_end', None)

        if fecha_start:
            try:
                start_date = datetime.strptime(fecha_start, '%Y-%m-%d').date()
                utilidades = utilidades.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de fecha_start debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if fecha_end:
            try:
                end_date = datetime.strptime(fecha_end, '%Y-%m-%d').date()
                utilidades = utilidades.filter(fecha__lte=end_date)
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
                utilidades = utilidades.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                utilidades = utilidades.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            utilidades = utilidades.filter(deleted_at__isnull=True)

        # Ordenar
        utilidades = utilidades.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_utilidades = paginator.paginate_queryset(utilidades, request)

        data = [serialize_utilidad_ocasional(u) for u in paginated_utilidades]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener utilidades ocasionales: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_utilidad_ocasional(request, pk):
    """Obtener una utilidad ocasional por ID"""
    try:
        utilidad = get_object_or_404(
            UtilidadOcasional.objects.select_related('usuario', 'tarjeta'),
            pk=pk
        )
        return Response(serialize_utilidad_ocasional(utilidad), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener utilidad ocasional: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def update_utilidad_ocasional(request, pk):
    """Actualizar una utilidad ocasional"""
    try:
        utilidad = get_object_or_404(UtilidadOcasional.objects.select_related('tarjeta'), pk=pk)

        # Validar que la tarjeta exista si se proporciona
        tarjeta = utilidad.tarjeta
        if 'tarjeta' in request.data:
            tarjeta_id = request.data.get('tarjeta')
            try:
                tarjeta = Tarjeta.objects.get(pk=tarjeta_id)
                if tarjeta.deleted_at is not None:
                    return Response(
                        {"error": "La tarjeta especificada está eliminada."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                utilidad.tarjeta = tarjeta
            except Tarjeta.DoesNotExist:
                return Response(
                    {"error": "La tarjeta especificada no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Actualizar otros campos
        utilidad.valor = request.data.get('valor', utilidad.valor)
        utilidad.observacion = request.data.get('observacion', utilidad.observacion)
        utilidad.fecha = request.data.get('fecha', utilidad.fecha)

        # Recalcular cuatro_por_mil y total si cambió valor o tarjeta
        if 'valor' in request.data or 'tarjeta' in request.data:
            valor = Decimal(utilidad.valor)
            utilidad.cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
            utilidad.total = valor + utilidad.cuatro_por_mil

        utilidad.save()

        return Response(serialize_utilidad_ocasional(utilidad), status=status.HTTP_200_OK)

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
def delete_utilidad_ocasional(request, pk):
    """Eliminar una utilidad ocasional (soft delete)"""
    try:
        utilidad = get_object_or_404(UtilidadOcasional.objects, pk=pk)
        utilidad.soft_delete()
        return Response(
            {"message": "Utilidad ocasional eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar utilidad ocasional: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_utilidad_ocasional(request, pk):
    """Restaurar una utilidad ocasional eliminada"""
    try:
        utilidad = get_object_or_404(UtilidadOcasional.objects, pk=pk)
        if not utilidad.is_deleted:
            return Response(
                {"error": "La utilidad ocasional no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )
        utilidad.restore()
        return Response(serialize_utilidad_ocasional(utilidad), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar utilidad ocasional: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_utilidad_ocasional(request, pk):
    """Eliminar permanentemente una utilidad ocasional"""
    try:
        utilidad = get_object_or_404(UtilidadOcasional.objects, pk=pk)
        utilidad.delete()
        return Response(
            {"message": "Utilidad ocasional eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar utilidad ocasional: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def utilidad_ocasional_history(request, pk):
    """Obtener el historial de cambios de una utilidad ocasional"""
    try:
        utilidad = get_object_or_404(UtilidadOcasional.objects, pk=pk)
        history = utilidad.history.all()

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
