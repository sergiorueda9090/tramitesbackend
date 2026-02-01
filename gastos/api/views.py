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

from ..models import Gasto, GastoRelacion
from tarjetas.models import Tarjeta
from .permissions import RolePermission


def calcular_cuatro_por_mil(valor, tarjeta):
    """Calcula el cuatro por mil si la tarjeta lo tiene activo"""
    if tarjeta.cuatro_por_mil == '1':
        return (Decimal(valor) * Decimal('4')) / Decimal('1000')
    return Decimal('0')


# ==================== GASTO ====================

def serialize_gasto(gasto):
    """Convierte un objeto Gasto a diccionario"""
    return {
        'id': gasto.id,
        'user': {
            'id': gasto.user.id,
            'name': f"{gasto.user.first_name} {gasto.user.last_name}".strip(),
        } if gasto.user else None,
        'nombre': gasto.nombre,
        'descripcion': gasto.descripcion,
        'created_at': gasto.created_at,
        'updated_at': gasto.updated_at,
        'deleted_at': gasto.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_gasto(request):
    """Crear un nuevo gasto"""
    try:
        required_fields = ['nombre', 'descripcion']
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

        gasto = Gasto.objects.create(
            user=request.user,
            nombre=request.data.get('nombre'),
            descripcion=request.data.get('descripcion'),
        )

        return Response(serialize_gasto(gasto), status=status.HTTP_201_CREATED)

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
def list_gastos(request):
    """Listar gastos con filtros y paginación"""
    try:
        gastos = Gasto.objects.select_related('user').all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            gastos = gastos.filter(
                Q(nombre__icontains=search_query) |
                Q(descripcion__icontains=search_query)
            )

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                gastos = gastos.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                gastos = gastos.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            gastos = gastos.filter(deleted_at__isnull=True)

        # Ordenar
        gastos = gastos.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_gastos = paginator.paginate_queryset(gastos, request)

        data = [serialize_gasto(g) for g in paginated_gastos]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener gastos: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gasto(request, pk):
    """Obtener un gasto por ID"""
    try:
        gasto = get_object_or_404(
            Gasto.objects.select_related('user'),
            pk=pk
        )
        return Response(serialize_gasto(gasto), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def update_gasto(request, pk):
    """Actualizar un gasto"""
    try:
        gasto = get_object_or_404(Gasto.objects, pk=pk)

        gasto.nombre = request.data.get('nombre', gasto.nombre)
        gasto.descripcion = request.data.get('descripcion', gasto.descripcion)

        gasto.save()

        return Response(serialize_gasto(gasto), status=status.HTTP_200_OK)

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
def delete_gasto(request, pk):
    """Eliminar un gasto (soft delete)"""
    try:
        gasto = get_object_or_404(Gasto.objects, pk=pk)
        gasto.soft_delete()
        return Response(
            {"message": "Gasto eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_gasto(request, pk):
    """Restaurar un gasto eliminado"""
    try:
        gasto = get_object_or_404(Gasto.objects, pk=pk)
        if not gasto.is_deleted:
            return Response(
                {"error": "El gasto no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        gasto.restore()
        return Response(serialize_gasto(gasto), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_gasto(request, pk):
    """Eliminar permanentemente un gasto"""
    try:
        gasto = get_object_or_404(Gasto.objects, pk=pk)
        gasto.delete()
        return Response(
            {"message": "Gasto eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def gasto_history(request, pk):
    """Obtener el historial de cambios de un gasto"""
    try:
        gasto = get_object_or_404(Gasto.objects, pk=pk)
        history = gasto.history.all()

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
                'nombre': h.nombre,
                'descripcion': h.descripcion,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== GASTO RELACION ====================

def serialize_gasto_relacion(relacion):
    """Convierte un objeto GastoRelacion a diccionario"""
    return {
        'id': relacion.id,
        'usuario': {
            'id': relacion.usuario.id,
            'name': f"{relacion.usuario.first_name} {relacion.usuario.last_name}".strip(),
        } if relacion.usuario else None,
        'gasto': {
            'id': relacion.gasto.id,
            'nombre': relacion.gasto.nombre,
        } if relacion.gasto else None,
        'tarjeta': {
            'id': relacion.tarjeta.id,
            'numero': relacion.tarjeta.numero,
            'titular': relacion.tarjeta.titular,
            'cuatro_por_mil': relacion.tarjeta.cuatro_por_mil,
        } if relacion.tarjeta else None,
        'valor': str(relacion.valor),
        'cuatro_por_mil': str(relacion.cuatro_por_mil),
        'total': str(relacion.total),
        'observacion': relacion.observacion,
        'fecha': relacion.fecha,
        'created_at': relacion.created_at,
        'updated_at': relacion.updated_at,
        'deleted_at': relacion.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_gasto_relacion(request):
    """Crear una nueva relación de gasto"""
    try:
        required_fields = ['gasto', 'tarjeta', 'valor', 'fecha']
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

        # Validar que el gasto exista
        gasto_id = request.data.get('gasto')
        try:
            gasto = Gasto.objects.get(pk=gasto_id)
            if gasto.deleted_at is not None:
                return Response(
                    {"error": "El gasto especificado está eliminado."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Gasto.DoesNotExist:
            return Response(
                {"error": "El gasto especificado no existe."},
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

        relacion = GastoRelacion.objects.create(
            usuario=request.user,
            gasto=gasto,
            tarjeta=tarjeta,
            valor=valor,
            cuatro_por_mil=cuatro_por_mil,
            total=total,
            observacion=request.data.get('observacion', ''),
            fecha=request.data.get('fecha'),
        )

        return Response(serialize_gasto_relacion(relacion), status=status.HTTP_201_CREATED)

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
def list_gasto_relaciones(request):
    """Listar relaciones de gasto con filtros y paginación"""
    try:
        relaciones = GastoRelacion.objects.select_related(
            'usuario', 'gasto', 'tarjeta'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            relaciones = relaciones.filter(
                Q(gasto__nombre__icontains=search_query) |
                Q(tarjeta__numero__icontains=search_query) |
                Q(tarjeta__titular__icontains=search_query) |
                Q(observacion__icontains=search_query)
            )

        # Filtro por gasto
        gasto_id = request.query_params.get('gasto', None)
        if gasto_id:
            relaciones = relaciones.filter(gasto_id=gasto_id)

        # Filtro por tarjeta
        tarjeta_id = request.query_params.get('tarjeta', None)
        if tarjeta_id:
            relaciones = relaciones.filter(tarjeta_id=tarjeta_id)

        # Filtro por usuario
        usuario_id = request.query_params.get('usuario', None)
        if usuario_id:
            relaciones = relaciones.filter(usuario_id=usuario_id)

        # Filtro por fecha
        fecha_start = request.query_params.get('fecha_start', None)
        fecha_end = request.query_params.get('fecha_end', None)

        if fecha_start:
            try:
                start_date = datetime.strptime(fecha_start, '%Y-%m-%d').date()
                relaciones = relaciones.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de fecha_start debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if fecha_end:
            try:
                end_date = datetime.strptime(fecha_end, '%Y-%m-%d').date()
                relaciones = relaciones.filter(fecha__lte=end_date)
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
                relaciones = relaciones.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                relaciones = relaciones.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            relaciones = relaciones.filter(deleted_at__isnull=True)

        # Ordenar
        relaciones = relaciones.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_relaciones = paginator.paginate_queryset(relaciones, request)

        data = [serialize_gasto_relacion(r) for r in paginated_relaciones]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener relaciones de gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gasto_relacion(request, pk):
    """Obtener una relación de gasto por ID"""
    try:
        relacion = get_object_or_404(
            GastoRelacion.objects.select_related('usuario', 'gasto', 'tarjeta'),
            pk=pk
        )
        return Response(serialize_gasto_relacion(relacion), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener relación de gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def update_gasto_relacion(request, pk):
    """Actualizar una relación de gasto"""
    try:
        relacion = get_object_or_404(GastoRelacion.objects.select_related('tarjeta'), pk=pk)

        # Validar que el gasto exista si se proporciona
        if 'gasto' in request.data:
            gasto_id = request.data.get('gasto')
            try:
                gasto = Gasto.objects.get(pk=gasto_id)
                if gasto.deleted_at is not None:
                    return Response(
                        {"error": "El gasto especificado está eliminado."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                relacion.gasto = gasto
            except Gasto.DoesNotExist:
                return Response(
                    {"error": "El gasto especificado no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Validar que la tarjeta exista si se proporciona
        tarjeta = relacion.tarjeta
        if 'tarjeta' in request.data:
            tarjeta_id = request.data.get('tarjeta')
            try:
                tarjeta = Tarjeta.objects.get(pk=tarjeta_id)
                if tarjeta.deleted_at is not None:
                    return Response(
                        {"error": "La tarjeta especificada está eliminada."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                relacion.tarjeta = tarjeta
            except Tarjeta.DoesNotExist:
                return Response(
                    {"error": "La tarjeta especificada no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Actualizar otros campos
        relacion.valor = request.data.get('valor', relacion.valor)
        relacion.observacion = request.data.get('observacion', relacion.observacion)
        relacion.fecha = request.data.get('fecha', relacion.fecha)

        # Recalcular cuatro_por_mil y total si cambió valor o tarjeta
        if 'valor' in request.data or 'tarjeta' in request.data:
            valor = Decimal(relacion.valor)
            relacion.cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
            relacion.total = valor + relacion.cuatro_por_mil

        relacion.save()

        return Response(serialize_gasto_relacion(relacion), status=status.HTTP_200_OK)

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
def delete_gasto_relacion(request, pk):
    """Eliminar una relación de gasto (soft delete)"""
    try:
        relacion = get_object_or_404(GastoRelacion.objects, pk=pk)
        relacion.soft_delete()
        return Response(
            {"message": "Relación de gasto eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar relación de gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def restore_gasto_relacion(request, pk):
    """Restaurar una relación de gasto eliminada"""
    try:
        relacion = get_object_or_404(GastoRelacion.objects, pk=pk)
        if not relacion.is_deleted:
            return Response(
                {"error": "La relación de gasto no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )
        relacion.restore()
        return Response(serialize_gasto_relacion(relacion), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar relación de gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def hard_delete_gasto_relacion(request, pk):
    """Eliminar permanentemente una relación de gasto"""
    try:
        relacion = get_object_or_404(GastoRelacion.objects, pk=pk)
        relacion.delete()
        return Response(
            {"message": "Relación de gasto eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar relación de gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin'])])
def gasto_relacion_history(request, pk):
    """Obtener el historial de cambios de una relación de gasto"""
    try:
        relacion = get_object_or_404(GastoRelacion.objects, pk=pk)
        history = relacion.history.all()

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
                'gasto_id': h.gasto_id,
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
