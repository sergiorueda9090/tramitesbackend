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

from ..models import AjusteDeSaldo
from clientes.models import Cliente
from sub_cuentas.models import SubCuenta
from movimiento_contable.services import registrar_asiento, revertir_asiento
from .permissions import RolePermission, ModulePermission


MODULO_ORIGEN = 'ajuste_de_saldo'


def _descripcion_asiento(ajuste):
    return f"Ajuste de saldo #{ajuste.id} | Cliente: {ajuste.cliente.nombre}"


def _decimal_or_zero(v):
    try:
        return Decimal(str(v)) if v not in (None, '') else Decimal('0')
    except Exception:
        return Decimal('0')


def _resolver_direccion_asiento(payload):
    """A partir del payload, devuelve (monto, sentido, error_response).

    sentido = 'debito_cliente'  → D=cliente.sub_cuenta, C=ajuste.sub_cuenta
              'credito_cliente' → D=ajuste.sub_cuenta,  C=cliente.sub_cuenta
    """
    debito  = _decimal_or_zero(payload.get('debito'))
    credito = _decimal_or_zero(payload.get('credito'))

    if debito > 0 and credito > 0:
        return None, None, Response(
            {"error": "El ajuste debe traer solo debito o solo credito, no ambos."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if debito <= 0 and credito <= 0:
        return None, None, Response(
            {"error": "El ajuste debe traer un debito o un credito mayor a 0."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if debito > 0:
        return debito, 'debito_cliente', None
    return credito, 'credito_cliente', None


def _validar_sub_cuenta(sub_cuenta_id, excluir_pk=None):
    """Valida sub_cuenta obligatoria + no eliminada."""
    if not sub_cuenta_id:
        return None, Response({"error": "La sub-cuenta es obligatoria."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        sub = SubCuenta.objects.get(pk=sub_cuenta_id)
    except SubCuenta.DoesNotExist:
        return None, Response({"error": "La sub-cuenta especificada no existe."}, status=status.HTTP_404_NOT_FOUND)
    if sub.is_deleted:
        return None, Response({"error": "La sub-cuenta especificada esta eliminada."}, status=status.HTTP_400_BAD_REQUEST)
    return sub, None


def serialize_ajuste_de_saldo(ajuste):
    """Convierte un objeto AjusteDeSaldo a diccionario"""
    return {
        'id': ajuste.id,
        'usuario': {
            'id': ajuste.usuario.id,
            'name': f"{ajuste.usuario.first_name} {ajuste.usuario.last_name}".strip(),
        } if ajuste.usuario else None,
        'cliente': {
            'id': ajuste.cliente.id,
            'nombre': ajuste.cliente.nombre,
        } if ajuste.cliente else None,
        'valor': str(ajuste.valor),
        'debito': str(ajuste.debito),
        'credito': str(ajuste.credito),
        'sub_cuenta': ajuste.sub_cuenta_id,
        'sub_cuenta_codigo': ajuste.sub_cuenta.codigo if ajuste.sub_cuenta else None,
        'sub_cuenta_nombre': ajuste.sub_cuenta.nombre_sub_cuenta if ajuste.sub_cuenta else None,
        'asiento_id': str(ajuste.asiento_id) if ajuste.asiento_id else None,
        'observacion': ajuste.observacion,
        'fecha': ajuste.fecha,
        'created_at': ajuste.created_at,
        'updated_at': ajuste.updated_at,
        'deleted_at': ajuste.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('ajuste_saldo', 'create')])
def create_ajuste_de_saldo(request):
    """Crear un nuevo ajuste de saldo + asiento contable (partida doble).

    Direccion del asiento (segun payload):
      - debito  > 0 → D=cliente.sub_cuenta, C=ajuste.sub_cuenta (deuda sube).
      - credito > 0 → D=ajuste.sub_cuenta,  C=cliente.sub_cuenta (deuda baja).
    """
    try:
        required_fields = ['cliente', 'fecha']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        monto, sentido, error_response = _resolver_direccion_asiento(request.data)
        if error_response:
            return error_response

        try:
            cliente = Cliente.objects.select_related('sub_cuenta').get(pk=request.data.get('cliente'))
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

        sub_cuenta_contraparte, error_response = _validar_sub_cuenta(request.data.get('sub_cuenta'))
        if error_response:
            return error_response

        if sub_cuenta_contraparte.pk == cliente.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta del ajuste no puede ser la misma que la del cliente."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if sentido == 'debito_cliente':
            debito_sub_cuenta  = cliente.sub_cuenta
            credito_sub_cuenta = sub_cuenta_contraparte
            debito_val, credito_val = monto, Decimal('0')
        else:
            debito_sub_cuenta  = sub_cuenta_contraparte
            credito_sub_cuenta = cliente.sub_cuenta
            debito_val, credito_val = Decimal('0'), monto

        try:
            with transaction.atomic():
                ajuste = AjusteDeSaldo.objects.create(
                    usuario=request.user,
                    cliente=cliente,
                    valor=monto,
                    debito=debito_val,
                    credito=credito_val,
                    sub_cuenta=sub_cuenta_contraparte,
                    observacion=request.data.get('observacion', ''),
                    fecha=request.data.get('fecha'),
                )

                asiento_id = registrar_asiento(
                    fecha=ajuste.fecha,
                    debito_sub_cuenta=debito_sub_cuenta,
                    credito_sub_cuenta=credito_sub_cuenta,
                    valor=monto,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=ajuste.id,
                    descripcion=_descripcion_asiento(ajuste),
                    usuario=request.user,
                )
                AjusteDeSaldo.objects.filter(pk=ajuste.pk).update(asiento_id=asiento_id)
                ajuste.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(serialize_ajuste_de_saldo(ajuste), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('ajuste_saldo', 'view')])
def list_ajustes_de_saldo(request):
    """Listar ajustes de saldo con filtros y paginación"""
    try:
        ajustes = AjusteDeSaldo.objects.select_related(
            'usuario', 'cliente'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            ajustes = ajustes.filter(
                Q(cliente__nombre__icontains=search_query) |
                Q(observacion__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            ajustes = ajustes.filter(cliente_id=cliente_id)

        # Filtro por usuario
        usuario_id = request.query_params.get('usuario', None)
        if usuario_id:
            ajustes = ajustes.filter(usuario_id=usuario_id)

        # Filtro por fecha
        fecha_start = request.query_params.get('fecha_start', None)
        fecha_end = request.query_params.get('fecha_end', None)

        if fecha_start:
            try:
                start_date = datetime.strptime(fecha_start, '%Y-%m-%d').date()
                ajustes = ajustes.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de fecha_start debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if fecha_end:
            try:
                end_date = datetime.strptime(fecha_end, '%Y-%m-%d').date()
                ajustes = ajustes.filter(fecha__lte=end_date)
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
                ajustes = ajustes.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                ajustes = ajustes.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            ajustes = ajustes.filter(deleted_at__isnull=True)

        # Ordenar
        ajustes = ajustes.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_ajustes = paginator.paginate_queryset(ajustes, request)

        data = [serialize_ajuste_de_saldo(a) for a in paginated_ajustes]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener ajustes de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('ajuste_saldo', 'view')])
def get_ajuste_de_saldo(request, pk):
    """Obtener un ajuste de saldo por ID"""
    try:
        ajuste = get_object_or_404(
            AjusteDeSaldo.objects.select_related('usuario', 'cliente'),
            pk=pk
        )
        return Response(serialize_ajuste_de_saldo(ajuste), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener ajuste de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('ajuste_saldo', 'edit')])
def update_ajuste_de_saldo(request, pk):
    """Actualizar un ajuste de saldo.

    Cualquier cambio revierte el asiento previo y registra uno nuevo (atomico).
    Si el payload trae debito o credito, recalcula la direccion del asiento.
    Si no, mantiene los valores actuales del registro.
    """
    try:
        ajuste = get_object_or_404(
            AjusteDeSaldo.objects.select_related('cliente__sub_cuenta', 'sub_cuenta'), pk=pk
        )

        if 'cliente' in request.data:
            try:
                cliente = Cliente.objects.select_related('sub_cuenta').get(pk=request.data.get('cliente'))
                if cliente.deleted_at is not None:
                    return Response(
                        {"error": "El cliente especificado está eliminado."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ajuste.cliente = cliente
            except Cliente.DoesNotExist:
                return Response(
                    {"error": "El cliente especificado no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        if 'sub_cuenta' in request.data:
            sub_cuenta_contraparte, error_response = _validar_sub_cuenta(
                request.data.get('sub_cuenta'), excluir_pk=ajuste.pk
            )
            if error_response:
                return error_response
            ajuste.sub_cuenta = sub_cuenta_contraparte

        # Determinar la direccion: si el payload trae debito o credito, usar eso.
        # Si no, usar lo que ya tenia el registro.
        if 'debito' in request.data or 'credito' in request.data:
            sintetico = {
                'debito':  request.data.get('debito',  ajuste.debito),
                'credito': request.data.get('credito', ajuste.credito),
            }
            monto, sentido, error_response = _resolver_direccion_asiento(sintetico)
            if error_response:
                return error_response
        else:
            if ajuste.debito > 0 and ajuste.credito == 0:
                monto, sentido = ajuste.debito, 'debito_cliente'
            elif ajuste.credito > 0 and ajuste.debito == 0:
                monto, sentido = ajuste.credito, 'credito_cliente'
            else:
                return Response(
                    {"error": "El ajuste existente no tiene una direccion contable valida; envia debito o credito."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        ajuste.observacion = request.data.get('observacion', ajuste.observacion)
        ajuste.fecha = request.data.get('fecha', ajuste.fecha)
        ajuste.valor = monto

        cliente_actual = ajuste.cliente
        if cliente_actual.sub_cuenta_id is None or cliente_actual.sub_cuenta.is_deleted:
            return Response(
                {"error": "El cliente no tiene una sub-cuenta contable valida asignada."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if ajuste.sub_cuenta_id == cliente_actual.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta del ajuste no puede ser la misma que la del cliente."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if sentido == 'debito_cliente':
            debito_sub_cuenta  = cliente_actual.sub_cuenta
            credito_sub_cuenta = ajuste.sub_cuenta
            ajuste.debito,  ajuste.credito = monto, Decimal('0')
        else:
            debito_sub_cuenta  = ajuste.sub_cuenta
            credito_sub_cuenta = cliente_actual.sub_cuenta
            ajuste.debito,  ajuste.credito = Decimal('0'), monto

        try:
            with transaction.atomic():
                revertir_asiento(ajuste.asiento_id)
                ajuste.save()
                asiento_id = registrar_asiento(
                    fecha=ajuste.fecha,
                    debito_sub_cuenta=debito_sub_cuenta,
                    credito_sub_cuenta=credito_sub_cuenta,
                    valor=monto,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=ajuste.id,
                    descripcion=_descripcion_asiento(ajuste),
                    usuario=request.user,
                )
                AjusteDeSaldo.objects.filter(pk=ajuste.pk).update(asiento_id=asiento_id)
                ajuste.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(serialize_ajuste_de_saldo(ajuste), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('ajuste_saldo', 'delete')])
def delete_ajuste_de_saldo(request, pk):
    """Eliminar un ajuste de saldo (soft delete) y revertir su asiento."""
    try:
        ajuste = get_object_or_404(AjusteDeSaldo.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(ajuste.asiento_id)
            AjusteDeSaldo.objects.filter(pk=ajuste.pk).update(asiento_id=None)
            ajuste.refresh_from_db(fields=['asiento_id'])
            ajuste.soft_delete()
        return Response(
            {"message": "Ajuste de saldo eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar ajuste de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('ajuste_saldo', 'delete')])
def restore_ajuste_de_saldo(request, pk):
    """Restaurar un ajuste de saldo eliminado y volver a registrar el asiento."""
    try:
        ajuste = get_object_or_404(
            AjusteDeSaldo.objects.select_related('cliente__sub_cuenta', 'sub_cuenta'), pk=pk
        )
        if not ajuste.is_deleted:
            return Response(
                {"error": "El ajuste de saldo no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )

        cliente = ajuste.cliente
        if cliente.sub_cuenta_id is None or cliente.sub_cuenta.is_deleted:
            return Response(
                {"error": "El cliente no tiene una sub-cuenta contable valida; no se puede restaurar."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if ajuste.sub_cuenta_id == cliente.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta del ajuste no puede ser la misma que la del cliente."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if ajuste.debito > 0 and ajuste.credito == 0:
            debito_sub_cuenta, credito_sub_cuenta, monto = cliente.sub_cuenta, ajuste.sub_cuenta, ajuste.debito
        elif ajuste.credito > 0 and ajuste.debito == 0:
            debito_sub_cuenta, credito_sub_cuenta, monto = ajuste.sub_cuenta, cliente.sub_cuenta, ajuste.credito
        else:
            return Response(
                {"error": "El ajuste no tiene una direccion contable valida; no se puede restaurar."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                ajuste.restore()
                asiento_id = registrar_asiento(
                    fecha=ajuste.fecha,
                    debito_sub_cuenta=debito_sub_cuenta,
                    credito_sub_cuenta=credito_sub_cuenta,
                    valor=monto,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=ajuste.id,
                    descripcion=_descripcion_asiento(ajuste),
                    usuario=request.user,
                )
                AjusteDeSaldo.objects.filter(pk=ajuste.pk).update(asiento_id=asiento_id)
                ajuste.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(serialize_ajuste_de_saldo(ajuste), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar ajuste de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('ajuste_saldo', 'delete')])
def hard_delete_ajuste_de_saldo(request, pk):
    """Eliminar permanentemente un ajuste de saldo (revierte el asiento si seguia activo)."""
    try:
        ajuste = get_object_or_404(AjusteDeSaldo.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(ajuste.asiento_id)
            ajuste.delete()
        return Response(
            {"message": "Ajuste de saldo eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar ajuste de saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('ajuste_saldo', 'view')])
def ajuste_de_saldo_history(request, pk):
    """Obtener el historial de cambios de un ajuste de saldo"""
    try:
        ajuste = get_object_or_404(AjusteDeSaldo.objects, pk=pk)
        history = ajuste.history.all()

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
                'valor': str(h.valor),
                'observacion': h.observacion,
                'fecha': h.fecha,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
