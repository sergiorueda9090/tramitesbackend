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

from ..models import CargoNoRegistrado
from tarjetas.models import Tarjeta
from clientes.models import Cliente
from sub_cuentas.models import SubCuenta
from movimiento_contable.services import registrar_asiento, revertir_asiento
from .permissions import RolePermission, ModulePermission


MODULO_ORIGEN = 'cargos_no_registrados'


def _descripcion_asiento(cargo):
    return (
        f"Cargo no registrado #{cargo.id} | "
        f"Cliente: {cargo.cliente.nombre} | "
        f"Tarjeta: {cargo.tarjeta.numero}"
    )


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
        'debito': str(cargo.debito),
        'credito': str(cargo.credito),
        'sub_cuenta': cargo.sub_cuenta_id,
        'sub_cuenta_codigo': cargo.sub_cuenta.codigo if cargo.sub_cuenta else None,
        'sub_cuenta_nombre': cargo.sub_cuenta.nombre_sub_cuenta if cargo.sub_cuenta else None,
        'asiento_id': str(cargo.asiento_id) if cargo.asiento_id else None,
        'observacion': cargo.observacion,
        'fecha': cargo.fecha,
        'created_at': cargo.created_at,
        'updated_at': cargo.updated_at,
        'deleted_at': cargo.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cargos_no_registrados', 'create')])
def create_cargo_no_registrado(request):
    """Crear un nuevo cargo no registrado + asiento contable (partida doble).

    Un cargo no registrado representa una deuda que aumenta para el cliente.

    Asiento:
      - Debito  -> cliente.sub_cuenta  (cuenta por cobrar del cliente sube).
      - Credito -> cargo.sub_cuenta    (contraparte del cargo, ej. ingresos).
      - Valor   -> cargo.total         (valor + 4x1000).
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
                {"error": "El valor del cargo debe ser mayor a 0."},
                status=status.HTTP_400_BAD_REQUEST
            )
        cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
        total = valor + cuatro_por_mil

        sub_cuenta_credito, error_response = _validar_sub_cuenta(request.data.get('sub_cuenta'))
        if error_response:
            return error_response

        if sub_cuenta_credito.pk == cliente.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta del cargo (credito) no puede ser la misma que la sub-cuenta del cliente (debito)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                cargo = CargoNoRegistrado.objects.create(
                    usuario=request.user,
                    cliente=cliente,
                    tarjeta=tarjeta,
                    valor=valor,
                    cuatro_por_mil=cuatro_por_mil,
                    total=total,
                    debito=total,
                    credito=total,
                    sub_cuenta=sub_cuenta_credito,
                    observacion=request.data.get('observacion', ''),
                    fecha=request.data.get('fecha'),
                )

                asiento_id = registrar_asiento(
                    fecha=cargo.fecha,
                    debito_sub_cuenta=cliente.sub_cuenta,
                    credito_sub_cuenta=sub_cuenta_credito,
                    valor=total,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=cargo.id,
                    descripcion=_descripcion_asiento(cargo),
                    usuario=request.user,
                )
                CargoNoRegistrado.objects.filter(pk=cargo.pk).update(asiento_id=asiento_id)
                cargo.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

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
@permission_classes([IsAuthenticated, ModulePermission('cargos_no_registrados', 'view')])
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
@permission_classes([IsAuthenticated, ModulePermission('cargos_no_registrados', 'view')])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cargos_no_registrados', 'edit')])
def update_cargo_no_registrado(request, pk):
    """Actualizar un cargo no registrado.

    Cualquier cambio revierte el asiento previo y registra uno nuevo (atomico).
    """
    try:
        cargo = get_object_or_404(
            CargoNoRegistrado.objects.select_related('tarjeta', 'cliente', 'sub_cuenta'), pk=pk
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
                cargo.cliente = cliente
            except Cliente.DoesNotExist:
                return Response(
                    {"error": "El cliente especificado no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

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

        if 'sub_cuenta' in request.data:
            sub_cuenta_credito, error_response = _validar_sub_cuenta(
                request.data.get('sub_cuenta'), excluir_pk=cargo.pk
            )
            if error_response:
                return error_response
            cargo.sub_cuenta = sub_cuenta_credito

        cargo.valor = request.data.get('valor', cargo.valor)
        cargo.observacion = request.data.get('observacion', cargo.observacion)
        cargo.fecha = request.data.get('fecha', cargo.fecha)

        valor = Decimal(cargo.valor)
        if valor <= 0:
            return Response(
                {"error": "El valor del cargo debe ser mayor a 0."},
                status=status.HTTP_400_BAD_REQUEST
            )
        cargo.cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
        cargo.total = valor + cargo.cuatro_por_mil
        cargo.debito = cargo.total
        cargo.credito = cargo.total

        cliente_actual = cargo.cliente
        if cliente_actual.sub_cuenta_id is None or cliente_actual.sub_cuenta.is_deleted:
            return Response(
                {"error": "El cliente no tiene una sub-cuenta contable valida asignada."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if cargo.sub_cuenta_id == cliente_actual.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta del cargo (credito) no puede ser la misma que la sub-cuenta del cliente (debito)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                revertir_asiento(cargo.asiento_id)
                cargo.save()
                asiento_id = registrar_asiento(
                    fecha=cargo.fecha,
                    debito_sub_cuenta=cliente_actual.sub_cuenta,
                    credito_sub_cuenta=cargo.sub_cuenta,
                    valor=cargo.total,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=cargo.id,
                    descripcion=_descripcion_asiento(cargo),
                    usuario=request.user,
                )
                CargoNoRegistrado.objects.filter(pk=cargo.pk).update(asiento_id=asiento_id)
                cargo.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cargos_no_registrados', 'delete')])
def delete_cargo_no_registrado(request, pk):
    """Eliminar un cargo no registrado (soft delete) y revertir su asiento contable."""
    try:
        cargo = get_object_or_404(CargoNoRegistrado.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(cargo.asiento_id)
            CargoNoRegistrado.objects.filter(pk=cargo.pk).update(asiento_id=None)
            cargo.refresh_from_db(fields=['asiento_id'])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cargos_no_registrados', 'delete')])
def restore_cargo_no_registrado(request, pk):
    """Restaurar un cargo no registrado eliminado y volver a registrar el asiento."""
    try:
        cargo = get_object_or_404(
            CargoNoRegistrado.objects.select_related('cliente__sub_cuenta', 'sub_cuenta'), pk=pk
        )
        if not cargo.is_deleted:
            return Response(
                {"error": "El cargo no registrado no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )

        cliente = cargo.cliente
        if cliente.sub_cuenta_id is None or cliente.sub_cuenta.is_deleted:
            return Response(
                {"error": "El cliente no tiene una sub-cuenta contable valida; no se puede restaurar el asiento."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if cargo.sub_cuenta_id == cliente.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta del cargo no puede ser la misma que la del cliente; no se puede restaurar."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                cargo.restore()
                asiento_id = registrar_asiento(
                    fecha=cargo.fecha,
                    debito_sub_cuenta=cliente.sub_cuenta,
                    credito_sub_cuenta=cargo.sub_cuenta,
                    valor=cargo.total,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=cargo.id,
                    descripcion=_descripcion_asiento(cargo),
                    usuario=request.user,
                )
                CargoNoRegistrado.objects.filter(pk=cargo.pk).update(asiento_id=asiento_id)
                cargo.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(serialize_cargo_no_registrado(cargo), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar cargo no registrado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cargos_no_registrados', 'delete')])
def hard_delete_cargo_no_registrado(request, pk):
    """Eliminar permanentemente un cargo no registrado (revierte el asiento si seguia activo)."""
    try:
        cargo = get_object_or_404(CargoNoRegistrado.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(cargo.asiento_id)
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cargos_no_registrados', 'view')])
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
