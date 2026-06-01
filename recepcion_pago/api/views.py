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

from ..models import RecepcionPago
from tarjetas.models import Tarjeta
from clientes.models import Cliente
from sub_cuentas.models import SubCuenta
from movimiento_contable.services import registrar_asiento, revertir_asiento
from .permissions import RolePermission, ModulePermission


MODULO_ORIGEN = 'recepcion_pago'


def _descripcion_asiento(recepcion):
    return (
        f"Recepcion de pago #{recepcion.id} | "
        f"Cliente: {recepcion.cliente.nombre} | "
        f"Tarjeta: {recepcion.tarjeta.numero}"
    )


def _validar_sub_cuenta(sub_cuenta_id, excluir_pk=None):
    """Valida sub_cuenta obligatoria + no eliminada."""
    if not sub_cuenta_id:
        return None, Response(
            {"error": "La sub-cuenta es obligatoria."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        sub = SubCuenta.objects.get(pk=sub_cuenta_id)
    except SubCuenta.DoesNotExist:
        return None, Response(
            {"error": "La sub-cuenta especificada no existe."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if sub.is_deleted:
        return None, Response(
            {"error": "La sub-cuenta especificada esta eliminada."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return sub, None


def calcular_cuatro_por_mil(valor, tarjeta):
    """Calcula el cuatro por mil si la tarjeta lo tiene activo"""
    if tarjeta.cuatro_por_mil == '1':
        return (Decimal(valor) * Decimal('4')) / Decimal('1000')
    return Decimal('0')


def serialize_recepcion_pago(recepcion):
    """Convierte un objeto RecepcionPago a diccionario"""
    return {
        'id': recepcion.id,
        'usuario': {
            'id': recepcion.usuario.id,
            'name': f"{recepcion.usuario.first_name} {recepcion.usuario.last_name}".strip(),
        } if recepcion.usuario else None,
        'cliente': {
            'id': recepcion.cliente.id,
            'nombre': recepcion.cliente.nombre,
        } if recepcion.cliente else None,
        'tarjeta': {
            'id': recepcion.tarjeta.id,
            'numero': recepcion.tarjeta.numero,
            'titular': recepcion.tarjeta.titular,
            'cuatro_por_mil': recepcion.tarjeta.cuatro_por_mil,
        } if recepcion.tarjeta else None,
        'valor': str(recepcion.valor),
        'cuatro_por_mil': str(recepcion.cuatro_por_mil),
        'total': str(recepcion.total),
        'debito': str(recepcion.debito),
        'credito': str(recepcion.credito),
        'sub_cuenta': recepcion.sub_cuenta_id,
        'sub_cuenta_codigo': recepcion.sub_cuenta.codigo if recepcion.sub_cuenta else None,
        'sub_cuenta_nombre': recepcion.sub_cuenta.nombre_sub_cuenta if recepcion.sub_cuenta else None,
        'asiento_id': str(recepcion.asiento_id) if recepcion.asiento_id else None,
        'observacion': recepcion.observacion,
        'fecha': recepcion.fecha,
        'created_at': recepcion.created_at,
        'updated_at': recepcion.updated_at,
        'deleted_at': recepcion.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('recepcion_pagos', 'create')])
def create_recepcion_pago(request):
    """Crear una nueva recepción de pago + asiento contable (partida doble).

    Asiento:
      - Debito  -> recepcion.sub_cuenta  (caja/banco que recibe el pago).
      - Credito -> cliente.sub_cuenta    (cuenta por cobrar del cliente).
      - Valor   -> recepcion.total       (valor + 4x1000).
    """
    try:
        required_fields = ['cliente', 'tarjeta', 'valor', 'fecha']
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

        cliente_id = request.data.get('cliente')
        try:
            cliente = Cliente.objects.select_related('sub_cuenta').get(pk=cliente_id)
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

        if cliente.sub_cuenta_id is None or cliente.sub_cuenta.is_deleted:
            return Response(
                {"error": "El cliente no tiene una sub-cuenta contable valida asignada."},
                status=status.HTTP_400_BAD_REQUEST
            )

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
        if valor <= 0:
            return Response(
                {"error": "El valor de la recepcion de pago debe ser mayor a 0."},
                status=status.HTTP_400_BAD_REQUEST
            )
        cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
        total = valor + cuatro_por_mil

        sub_cuenta_debito, error_response = _validar_sub_cuenta(request.data.get('sub_cuenta'))
        if error_response:
            return error_response

        if sub_cuenta_debito.pk == cliente.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta de debito (caja/banco) no puede ser la misma que la sub-cuenta del cliente (credito)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                recepcion = RecepcionPago.objects.create(
                    usuario=request.user,
                    cliente=cliente,
                    tarjeta=tarjeta,
                    valor=valor,
                    cuatro_por_mil=cuatro_por_mil,
                    total=total,
                    debito=total,
                    credito=total,
                    sub_cuenta=sub_cuenta_debito,
                    observacion=request.data.get('observacion', ''),
                    fecha=request.data.get('fecha'),
                )

                asiento_id = registrar_asiento(
                    fecha=recepcion.fecha,
                    debito_sub_cuenta=sub_cuenta_debito,
                    credito_sub_cuenta=cliente.sub_cuenta,
                    valor=total,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=recepcion.id,
                    descripcion=_descripcion_asiento(recepcion),
                    usuario=request.user,
                )
                RecepcionPago.objects.filter(pk=recepcion.pk).update(asiento_id=asiento_id)
                recepcion.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(serialize_recepcion_pago(recepcion), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('recepcion_pagos', 'view')])
def list_recepciones_pago(request):
    """Listar recepciones de pago con filtros y paginación"""
    try:
        recepciones = RecepcionPago.objects.select_related(
            'usuario', 'cliente', 'tarjeta'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            recepciones = recepciones.filter(
                Q(cliente__nombre__icontains=search_query) |
                Q(tarjeta__numero__icontains=search_query) |
                Q(tarjeta__titular__icontains=search_query) |
                Q(observacion__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            recepciones = recepciones.filter(cliente_id=cliente_id)

        # Filtro por tarjeta
        tarjeta_id = request.query_params.get('tarjeta', None)
        if tarjeta_id:
            recepciones = recepciones.filter(tarjeta_id=tarjeta_id)

        # Filtro por usuario
        usuario_id = request.query_params.get('usuario', None)
        if usuario_id:
            recepciones = recepciones.filter(usuario_id=usuario_id)

        # Filtro por fecha de recepción
        fecha_start = request.query_params.get('fecha_start', None)
        fecha_end = request.query_params.get('fecha_end', None)

        if fecha_start:
            try:
                start_date = datetime.strptime(fecha_start, '%Y-%m-%d').date()
                recepciones = recepciones.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de fecha_start debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if fecha_end:
            try:
                end_date = datetime.strptime(fecha_end, '%Y-%m-%d').date()
                recepciones = recepciones.filter(fecha__lte=end_date)
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
                recepciones = recepciones.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                recepciones = recepciones.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            recepciones = recepciones.filter(deleted_at__isnull=True)

        # Ordenar
        recepciones = recepciones.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_recepciones = paginator.paginate_queryset(recepciones, request)

        data = [serialize_recepcion_pago(r) for r in paginated_recepciones]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener recepciones de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('recepcion_pagos', 'view')])
def get_recepcion_pago(request, pk):
    """Obtener una recepción de pago por ID"""
    try:
        recepcion = get_object_or_404(
            RecepcionPago.objects.select_related('usuario', 'cliente', 'tarjeta'),
            pk=pk
        )
        return Response(serialize_recepcion_pago(recepcion), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener recepción de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('recepcion_pagos', 'edit')])
def update_recepcion_pago(request, pk):
    """Actualizar una recepción de pago.

    Cualquier cambio revierte el asiento previo y registra uno nuevo de forma atomica.
    """
    try:
        recepcion = get_object_or_404(
            RecepcionPago.objects.select_related('tarjeta', 'cliente', 'sub_cuenta'), pk=pk
        )

        if 'cliente' in request.data:
            cliente_id = request.data.get('cliente')
            try:
                cliente = Cliente.objects.select_related('sub_cuenta').get(pk=cliente_id)
                if cliente.deleted_at is not None:
                    return Response(
                        {"error": "El cliente especificado está eliminado."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                recepcion.cliente = cliente
            except Cliente.DoesNotExist:
                return Response(
                    {"error": "El cliente especificado no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        tarjeta = recepcion.tarjeta
        if 'tarjeta' in request.data:
            tarjeta_id = request.data.get('tarjeta')
            try:
                tarjeta = Tarjeta.objects.get(pk=tarjeta_id)
                if tarjeta.deleted_at is not None:
                    return Response(
                        {"error": "La tarjeta especificada está eliminada."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                recepcion.tarjeta = tarjeta
            except Tarjeta.DoesNotExist:
                return Response(
                    {"error": "La tarjeta especificada no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        if 'sub_cuenta' in request.data:
            sub_cuenta_debito, error_response = _validar_sub_cuenta(
                request.data.get('sub_cuenta'), excluir_pk=recepcion.pk
            )
            if error_response:
                return error_response
            recepcion.sub_cuenta = sub_cuenta_debito

        recepcion.valor = request.data.get('valor', recepcion.valor)
        recepcion.observacion = request.data.get('observacion', recepcion.observacion)
        recepcion.fecha = request.data.get('fecha', recepcion.fecha)

        valor = Decimal(recepcion.valor)
        if valor <= 0:
            return Response(
                {"error": "El valor de la recepcion de pago debe ser mayor a 0."},
                status=status.HTTP_400_BAD_REQUEST
            )
        recepcion.cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
        recepcion.total = valor + recepcion.cuatro_por_mil
        recepcion.debito = recepcion.total
        recepcion.credito = recepcion.total

        cliente_actual = recepcion.cliente
        if cliente_actual.sub_cuenta_id is None or cliente_actual.sub_cuenta.is_deleted:
            return Response(
                {"error": "El cliente no tiene una sub-cuenta contable valida asignada."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if recepcion.sub_cuenta_id == cliente_actual.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta de debito no puede ser la misma que la sub-cuenta del cliente (credito)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                revertir_asiento(recepcion.asiento_id)
                recepcion.save()
                asiento_id = registrar_asiento(
                    fecha=recepcion.fecha,
                    debito_sub_cuenta=recepcion.sub_cuenta,
                    credito_sub_cuenta=cliente_actual.sub_cuenta,
                    valor=recepcion.total,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=recepcion.id,
                    descripcion=_descripcion_asiento(recepcion),
                    usuario=request.user,
                )
                RecepcionPago.objects.filter(pk=recepcion.pk).update(asiento_id=asiento_id)
                recepcion.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(serialize_recepcion_pago(recepcion), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('recepcion_pagos', 'delete')])
def delete_recepcion_pago(request, pk):
    """Eliminar una recepción de pago (soft delete) y revertir su asiento contable."""
    try:
        recepcion = get_object_or_404(RecepcionPago.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(recepcion.asiento_id)
            RecepcionPago.objects.filter(pk=recepcion.pk).update(asiento_id=None)
            recepcion.refresh_from_db(fields=['asiento_id'])
            recepcion.soft_delete()
        return Response(
            {"message": "Recepción de pago eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar recepción de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('recepcion_pagos', 'delete')])
def restore_recepcion_pago(request, pk):
    """Restaurar una recepción de pago eliminada y volver a registrar el asiento contable."""
    try:
        recepcion = get_object_or_404(
            RecepcionPago.objects.select_related('cliente__sub_cuenta', 'sub_cuenta'), pk=pk
        )
        if not recepcion.is_deleted:
            return Response(
                {"error": "La recepción de pago no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )

        cliente = recepcion.cliente
        if cliente.sub_cuenta_id is None or cliente.sub_cuenta.is_deleted:
            return Response(
                {"error": "El cliente no tiene una sub-cuenta contable valida; no se puede restaurar el asiento."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if recepcion.sub_cuenta_id == cliente.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta de debito no puede ser la misma que la del cliente; no se puede restaurar."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                recepcion.restore()
                asiento_id = registrar_asiento(
                    fecha=recepcion.fecha,
                    debito_sub_cuenta=recepcion.sub_cuenta,
                    credito_sub_cuenta=cliente.sub_cuenta,
                    valor=recepcion.total,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=recepcion.id,
                    descripcion=_descripcion_asiento(recepcion),
                    usuario=request.user,
                )
                RecepcionPago.objects.filter(pk=recepcion.pk).update(asiento_id=asiento_id)
                recepcion.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(serialize_recepcion_pago(recepcion), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar recepción de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('recepcion_pagos', 'delete')])
def hard_delete_recepcion_pago(request, pk):
    """Eliminar permanentemente una recepción de pago (revierte el asiento si seguia activo)."""
    try:
        recepcion = get_object_or_404(RecepcionPago.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(recepcion.asiento_id)
            recepcion.delete()
        return Response(
            {"message": "Recepción de pago eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar recepción de pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('recepcion_pagos', 'view')])
def recepcion_pago_history(request, pk):
    """Obtener el historial de cambios de una recepción de pago"""
    try:
        recepcion = get_object_or_404(RecepcionPago.objects, pk=pk)
        history = recepcion.history.all()

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
