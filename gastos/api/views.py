from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from datetime import datetime
from decimal import Decimal

from ..models import Gasto, GastoRelacion
from gastos_categoria.models import GastoCategoria
from tarjetas.models import Tarjeta
from movimiento_contable.services import registrar_asiento, revertir_asiento
from .permissions import RolePermission, ModulePermission


MODULO_ORIGEN_RELACION = 'gastos'


def _descripcion_asiento_relacion(relacion):
    return (
        f"Gasto #{relacion.id} | "
        f"Categoria: {relacion.gasto.nombre} | "
        f"Tarjeta: {relacion.tarjeta.numero}"
    )


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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('gastos', 'create')])
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
@permission_classes([IsAuthenticated, ModulePermission('gastos', 'view')])
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
@permission_classes([IsAuthenticated, ModulePermission('gastos', 'view')])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('gastos', 'edit')])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos', 'delete')])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos', 'delete')])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos', 'delete')])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos', 'view')])
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
        'debito': str(relacion.debito),
        'credito': str(relacion.credito),
        'sub_cuenta': relacion.sub_cuenta_id,
        'sub_cuenta_codigo': relacion.sub_cuenta.codigo if relacion.sub_cuenta else None,
        'sub_cuenta_nombre': relacion.sub_cuenta.nombre_sub_cuenta if relacion.sub_cuenta else None,
        'asiento_id': str(relacion.asiento_id) if relacion.asiento_id else None,
        'observacion': relacion.observacion,
        'fecha': relacion.fecha,
        'created_at': relacion.created_at,
        'updated_at': relacion.updated_at,
        'deleted_at': relacion.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('gastos', 'create')])
def create_gasto_relacion(request):
    """Crear una nueva relación de gasto + asiento contable (partida doble).

    Asiento (las sub-cuentas se derivan automaticamente, no se envian en el payload):
      - Debito  -> gasto_categoria.sub_cuenta  (cuenta de gasto del PUC sube).
      - Credito -> tarjeta.sub_cuenta          (medio de pago baja).
      - Valor   -> relacion.total              (valor + 4x1000).
    """
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

        gasto_id = request.data.get('gasto')
        try:
            gasto = GastoCategoria.objects.select_related('sub_cuenta').get(pk=gasto_id)
            if gasto.deleted_at is not None:
                return Response(
                    {"error": "La categoría especificada está eliminada."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except GastoCategoria.DoesNotExist:
            return Response(
                {"error": "La categoría especificada no existe."},
                status=status.HTTP_404_NOT_FOUND
            )

        if gasto.sub_cuenta_id is None or gasto.sub_cuenta.is_deleted:
            return Response(
                {"error": "La categoria del gasto no tiene una sub-cuenta contable valida."},
                status=status.HTTP_400_BAD_REQUEST
            )

        tarjeta_id = request.data.get('tarjeta')
        try:
            tarjeta = Tarjeta.objects.select_related('sub_cuenta').get(pk=tarjeta_id)
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

        if tarjeta.sub_cuenta_id is None or tarjeta.sub_cuenta.is_deleted:
            return Response(
                {"error": "La tarjeta no tiene una sub-cuenta contable valida asignada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if tarjeta.sub_cuenta_id == gasto.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta de la tarjeta (credito) no puede ser la misma que la sub-cuenta de la categoria (debito)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        valor = Decimal(request.data.get('valor'))
        if valor <= 0:
            return Response(
                {"error": "El valor del gasto debe ser mayor a 0."},
                status=status.HTTP_400_BAD_REQUEST
            )
        cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
        total = valor + cuatro_por_mil

        # La sub-cuenta de credito (medio de pago) se deriva siempre de la tarjeta.
        sub_cuenta_credito = tarjeta.sub_cuenta

        try:
            with transaction.atomic():
                relacion = GastoRelacion.objects.create(
                    usuario=request.user,
                    gasto=gasto,
                    tarjeta=tarjeta,
                    valor=valor,
                    cuatro_por_mil=cuatro_por_mil,
                    total=total,
                    # El 4x1000 NO se suma al asiento contable: debito/credito reflejan
                    # solo el valor base. El 4x1000 queda registrado aparte (campo
                    # cuatro_por_mil + modulo Cuatro por mil via signal).
                    debito=valor,
                    credito=valor,
                    sub_cuenta=sub_cuenta_credito,
                    observacion=request.data.get('observacion', ''),
                    fecha=request.data.get('fecha'),
                )

                asiento_id = registrar_asiento(
                    fecha=relacion.fecha,
                    debito_sub_cuenta=gasto.sub_cuenta,
                    credito_sub_cuenta=sub_cuenta_credito,
                    valor=valor,
                    modulo_origen=MODULO_ORIGEN_RELACION,
                    origen_id=relacion.id,
                    descripcion=_descripcion_asiento_relacion(relacion),
                    usuario=request.user,
                )
                GastoRelacion.objects.filter(pk=relacion.pk).update(asiento_id=asiento_id)
                relacion.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

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
@permission_classes([IsAuthenticated, ModulePermission('gastos', 'view')])
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
@permission_classes([IsAuthenticated, ModulePermission('gastos', 'view')])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('gastos', 'edit')])
def update_gasto_relacion(request, pk):
    """Actualizar una relación de gasto.

    Cualquier cambio revierte el asiento previo y registra uno nuevo (atomico).
    """
    try:
        relacion = get_object_or_404(
            GastoRelacion.objects.select_related('tarjeta__sub_cuenta', 'gasto__sub_cuenta', 'sub_cuenta'), pk=pk
        )

        if 'gasto' in request.data:
            gasto_id = request.data.get('gasto')
            try:
                gasto = GastoCategoria.objects.select_related('sub_cuenta').get(pk=gasto_id)
                if gasto.deleted_at is not None:
                    return Response(
                        {"error": "La categoría especificada está eliminada."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                relacion.gasto = gasto
            except GastoCategoria.DoesNotExist:
                return Response(
                    {"error": "La categoría especificada no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        tarjeta = relacion.tarjeta
        if 'tarjeta' in request.data:
            tarjeta_id = request.data.get('tarjeta')
            try:
                tarjeta = Tarjeta.objects.select_related('sub_cuenta').get(pk=tarjeta_id)
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

        if tarjeta.sub_cuenta_id is None or tarjeta.sub_cuenta.is_deleted:
            return Response(
                {"error": "La tarjeta no tiene una sub-cuenta contable valida asignada."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Sincronizar siempre la sub_cuenta (credito) de la relacion con la de la tarjeta.
        relacion.sub_cuenta = tarjeta.sub_cuenta

        relacion.valor = request.data.get('valor', relacion.valor)
        relacion.observacion = request.data.get('observacion', relacion.observacion)
        relacion.fecha = request.data.get('fecha', relacion.fecha)

        valor = Decimal(relacion.valor)
        if valor <= 0:
            return Response(
                {"error": "El valor del gasto debe ser mayor a 0."},
                status=status.HTTP_400_BAD_REQUEST
            )
        relacion.cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
        relacion.total = valor + relacion.cuatro_por_mil
        # El 4x1000 NO se suma al asiento: debito/credito reflejan solo el valor base.
        relacion.debito = valor
        relacion.credito = valor

        gasto_actual = relacion.gasto
        if gasto_actual.sub_cuenta_id is None or gasto_actual.sub_cuenta.is_deleted:
            return Response(
                {"error": "La categoria del gasto no tiene una sub-cuenta contable valida."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if relacion.sub_cuenta_id == gasto_actual.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta del gasto (credito) no puede ser la misma que la sub-cuenta de la categoria (debito)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                revertir_asiento(relacion.asiento_id)
                relacion.save()
                asiento_id = registrar_asiento(
                    fecha=relacion.fecha,
                    debito_sub_cuenta=gasto_actual.sub_cuenta,
                    credito_sub_cuenta=relacion.sub_cuenta,
                    valor=valor,
                    modulo_origen=MODULO_ORIGEN_RELACION,
                    origen_id=relacion.id,
                    descripcion=_descripcion_asiento_relacion(relacion),
                    usuario=request.user,
                )
                GastoRelacion.objects.filter(pk=relacion.pk).update(asiento_id=asiento_id)
                relacion.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos', 'delete')])
def delete_gasto_relacion(request, pk):
    """Eliminar una relación de gasto (soft delete) y revertir su asiento contable."""
    try:
        relacion = get_object_or_404(GastoRelacion.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(relacion.asiento_id)
            GastoRelacion.objects.filter(pk=relacion.pk).update(asiento_id=None)
            relacion.refresh_from_db(fields=['asiento_id'])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos', 'delete')])
def restore_gasto_relacion(request, pk):
    """Restaurar una relación de gasto eliminada y volver a registrar el asiento."""
    try:
        relacion = get_object_or_404(
            GastoRelacion.objects.select_related('gasto__sub_cuenta', 'sub_cuenta'), pk=pk
        )
        if not relacion.is_deleted:
            return Response(
                {"error": "La relación de gasto no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )

        gasto = relacion.gasto
        if gasto.sub_cuenta_id is None or gasto.sub_cuenta.is_deleted:
            return Response(
                {"error": "La categoria del gasto no tiene una sub-cuenta contable valida; no se puede restaurar."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if relacion.sub_cuenta_id == gasto.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta del gasto no puede ser la misma que la de la categoria; no se puede restaurar."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # El 4x1000 no entra al asiento; debito/credito reflejan solo el valor base.
                relacion.debito = relacion.valor
                relacion.credito = relacion.valor
                relacion.restore()
                asiento_id = registrar_asiento(
                    fecha=relacion.fecha,
                    debito_sub_cuenta=gasto.sub_cuenta,
                    credito_sub_cuenta=relacion.sub_cuenta,
                    valor=relacion.valor,
                    modulo_origen=MODULO_ORIGEN_RELACION,
                    origen_id=relacion.id,
                    descripcion=_descripcion_asiento_relacion(relacion),
                    usuario=request.user,
                )
                GastoRelacion.objects.filter(pk=relacion.pk).update(asiento_id=asiento_id)
                relacion.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(serialize_gasto_relacion(relacion), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar relación de gasto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos', 'delete')])
def hard_delete_gasto_relacion(request, pk):
    """Eliminar permanentemente una relación de gasto (revierte el asiento si seguia activo)."""
    try:
        relacion = get_object_or_404(GastoRelacion.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(relacion.asiento_id)
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos', 'view')])
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
