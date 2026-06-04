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

from ..models import UtilidadOcasional, UtilidadOcasionalConfig
from tarjetas.models import Tarjeta
from sub_cuentas.models import SubCuenta
from movimiento_contable.services import registrar_asiento, revertir_asiento
from .permissions import RolePermission, ModulePermission


MODULO_ORIGEN = 'utilidad_ocasional'


def _descripcion_asiento(u):
    return f"Utilidad ocasional #{u.id} | Tarjeta: {u.tarjeta.numero}"


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


def _resolver_sub_cuenta_config(tipo):
    """Resuelve la contracuenta desde la configuracion global segun el `tipo`
    (ganancia / perdida). Devuelve (sub_cuenta, error_response).

    - ganancia -> config.sub_cuenta_positiva
    - perdida  -> config.sub_cuenta_negativa
    """
    cfg = UtilidadOcasionalConfig.load()
    if tipo == 'ganancia':
        sub_cuenta = cfg.sub_cuenta_positiva
        etiqueta = 'ganancia'
    else:
        sub_cuenta = cfg.sub_cuenta_negativa
        etiqueta = 'perdida'

    if sub_cuenta is None:
        return None, Response(
            {"error": f"No hay una sub-cuenta configurada para valores {etiqueta}. "
                      f"Configurala en la pantalla de Utilidad Ocasional antes de registrar."},
            status=status.HTTP_400_BAD_REQUEST
        )
    if sub_cuenta.is_deleted:
        return None, Response(
            {"error": f"La sub-cuenta configurada para valores {etiqueta} esta eliminada. "
                      f"Actualiza la configuracion."},
            status=status.HTTP_400_BAD_REQUEST
        )
    return sub_cuenta, None


def serialize_config(cfg):
    """Convierte la configuracion (singleton) a diccionario."""
    pos = cfg.sub_cuenta_positiva
    neg = cfg.sub_cuenta_negativa
    return {
        'sub_cuenta_positiva': cfg.sub_cuenta_positiva_id,
        'sub_cuenta_positiva_codigo': pos.codigo if pos else None,
        'sub_cuenta_positiva_nombre': pos.nombre_sub_cuenta if pos else None,
        'sub_cuenta_negativa': cfg.sub_cuenta_negativa_id,
        'sub_cuenta_negativa_codigo': neg.codigo if neg else None,
        'sub_cuenta_negativa_nombre': neg.nombre_sub_cuenta if neg else None,
        'updated_at': cfg.updated_at,
    }


def calcular_cuatro_por_mil(valor, tarjeta):
    """Calcula el cuatro por mil si la tarjeta lo tiene activo (sobre el valor dado)."""
    if tarjeta.cuatro_por_mil == '1':
        return (Decimal(valor) * Decimal('4')) / Decimal('1000')
    return Decimal('0')


def _asiento_legs(utilidad, tarjeta):
    """Devuelve (debito_sub_cuenta, credito_sub_cuenta, monto_positivo) segun el `tipo`.

    El valor siempre es positivo; el tipo indica ganancia o perdida:
      - Ganancia: Debito -> tarjeta.sub_cuenta (banco sube) / Credito -> utilidad.sub_cuenta (ingreso).
      - Perdida:  se invierte -> Debito -> utilidad.sub_cuenta / Credito -> tarjeta.sub_cuenta (banco baja).
    El asiento se postea con el monto base en positivo (= valor); el 4x1000 NO se
    suma al asiento (queda registrado aparte en el modulo Cuatro por mil).
    """
    monto = abs(utilidad.valor)
    if utilidad.tipo == 'ganancia':
        return tarjeta.sub_cuenta, utilidad.sub_cuenta, monto
    return utilidad.sub_cuenta, tarjeta.sub_cuenta, monto


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
        'tipo': utilidad.tipo,
        'tipo_display': utilidad.get_tipo_display(),
        'valor': str(utilidad.valor),
        'cuatro_por_mil': str(utilidad.cuatro_por_mil),
        'total': str(utilidad.total),
        'debito': str(utilidad.debito),
        'credito': str(utilidad.credito),
        'sub_cuenta': utilidad.sub_cuenta_id,
        'sub_cuenta_codigo': utilidad.sub_cuenta.codigo if utilidad.sub_cuenta else None,
        'sub_cuenta_nombre': utilidad.sub_cuenta.nombre_sub_cuenta if utilidad.sub_cuenta else None,
        'asiento_id': str(utilidad.asiento_id) if utilidad.asiento_id else None,
        'observacion': utilidad.observacion,
        'fecha': utilidad.fecha,
        'created_at': utilidad.created_at,
        'updated_at': utilidad.updated_at,
        'deleted_at': utilidad.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('utilidad_ocasional', 'create')])
def create_utilidad_ocasional(request):
    """Crear una nueva utilidad ocasional + asiento contable (partida doble).

    El valor siempre es positivo; el `tipo` (ganancia/perdida) define la direccion.
    Asiento (la sub-cuenta de la tarjeta se deriva; la contracuenta se resuelve desde
    la configuracion global segun el tipo):
      - Ganancia: Debito -> tarjeta.sub_cuenta (banco) / Credito -> config.sub_cuenta_positiva (ingreso).
      - Perdida:  se invierte (Debito -> config.sub_cuenta_negativa / Credito -> banco).
      - 4x1000 se calcula sobre el valor; el asiento se postea con el monto en positivo.
    """
    try:
        required_fields = ['tarjeta', 'valor', 'fecha']
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

        # El valor SIEMPRE se almacena positivo (magnitud). El tipo (ganancia/perdida)
        # llega en el payload y reemplaza al antiguo signo del valor.
        valor = abs(Decimal(request.data.get('valor')))
        if valor == 0:
            return Response(
                {"error": "El valor de la utilidad ocasional no puede ser 0."},
                status=status.HTTP_400_BAD_REQUEST
            )
        tipo = (request.data.get('tipo') or 'ganancia').strip().lower()
        if tipo not in ('ganancia', 'perdida'):
            return Response(
                {"error": "El tipo debe ser 'ganancia' o 'perdida'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # 4x1000 sobre el valor; total siempre positivo (valor + 4x1000).
        cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
        total = valor + cuatro_por_mil

        # La contracuenta se resuelve desde la configuracion global segun el tipo.
        sub_cuenta_credito, error_response = _resolver_sub_cuenta_config(tipo)
        if error_response:
            return error_response

        if sub_cuenta_credito.pk == tarjeta.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta configurada no puede ser la misma que la de la tarjeta."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                utilidad = UtilidadOcasional.objects.create(
                    usuario=request.user,
                    tarjeta=tarjeta,
                    tipo=tipo,
                    valor=valor,
                    cuatro_por_mil=cuatro_por_mil,
                    total=total,
                    # El 4x1000 NO se suma al asiento contable: debito/credito reflejan
                    # solo el valor base. El 4x1000 queda registrado aparte.
                    debito=valor,
                    credito=valor,
                    sub_cuenta=sub_cuenta_credito,
                    observacion=request.data.get('observacion', ''),
                    fecha=request.data.get('fecha'),
                )

                # Direccion del asiento segun el signo (positivo=ganancia / negativo=perdida).
                debito_sc, credito_sc, monto_asiento = _asiento_legs(utilidad, tarjeta)
                asiento_id = registrar_asiento(
                    fecha=utilidad.fecha,
                    debito_sub_cuenta=debito_sc,
                    credito_sub_cuenta=credito_sc,
                    valor=monto_asiento,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=utilidad.id,
                    descripcion=_descripcion_asiento(utilidad),
                    usuario=request.user,
                )
                UtilidadOcasional.objects.filter(pk=utilidad.pk).update(asiento_id=asiento_id)
                utilidad.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

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
@permission_classes([IsAuthenticated, ModulePermission('utilidad_ocasional', 'view')])
def get_config(request):
    """Obtener la configuracion global de sub-cuentas (positivos / negativos)."""
    try:
        cfg = UtilidadOcasionalConfig.load()
        return Response(serialize_config(cfg), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener la configuracion: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('utilidad_ocasional', 'edit')])
def update_config(request):
    """Actualizar la configuracion global de sub-cuentas.

    Acepta `sub_cuenta_positiva` y/o `sub_cuenta_negativa` (ids). Si un campo no
    viene en el payload se conserva; si viene vacio/None se limpia. Ambas deben
    ser sub-cuentas validas (no eliminadas) y distintas entre si.
    """
    try:
        cfg = UtilidadOcasionalConfig.load()

        def _resolver(campo):
            # No enviado -> conservar valor actual.
            if campo not in request.data:
                return getattr(cfg, campo), None
            val = request.data.get(campo)
            # Enviado vacio -> limpiar.
            if val in (None, '', 0, '0'):
                return None, None
            try:
                sub = SubCuenta.objects.get(pk=val)
            except SubCuenta.DoesNotExist:
                return None, Response(
                    {"error": "La sub-cuenta especificada no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )
            if sub.is_deleted:
                return None, Response(
                    {"error": "La sub-cuenta especificada esta eliminada."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return sub, None

        positiva, error_response = _resolver('sub_cuenta_positiva')
        if error_response:
            return error_response
        negativa, error_response = _resolver('sub_cuenta_negativa')
        if error_response:
            return error_response

        if positiva and negativa and positiva.pk == negativa.pk:
            return Response(
                {"error": "La sub-cuenta de positivos y la de negativos deben ser distintas."},
                status=status.HTTP_400_BAD_REQUEST
            )

        cfg.sub_cuenta_positiva = positiva
        cfg.sub_cuenta_negativa = negativa
        cfg.save()

        return Response(serialize_config(cfg), status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al guardar la configuracion: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('utilidad_ocasional', 'view')])
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
@permission_classes([IsAuthenticated, ModulePermission('utilidad_ocasional', 'view')])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('utilidad_ocasional', 'edit')])
def update_utilidad_ocasional(request, pk):
    """Actualizar una utilidad ocasional.

    Cualquier cambio revierte el asiento previo y registra uno nuevo (atomico).
    """
    try:
        utilidad = get_object_or_404(
            UtilidadOcasional.objects.select_related('tarjeta__sub_cuenta', 'sub_cuenta'), pk=pk
        )

        tarjeta = utilidad.tarjeta
        if 'tarjeta' in request.data:
            tarjeta_id = request.data.get('tarjeta')
            try:
                tarjeta = Tarjeta.objects.select_related('sub_cuenta').get(pk=tarjeta_id)
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

        # Valor siempre positivo; tipo (ganancia/perdida) reemplaza al signo.
        if 'valor' in request.data:
            utilidad.valor = abs(Decimal(request.data.get('valor')))
        if 'tipo' in request.data:
            tipo = (request.data.get('tipo') or '').strip().lower()
            if tipo not in ('ganancia', 'perdida'):
                return Response(
                    {"error": "El tipo debe ser 'ganancia' o 'perdida'."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            utilidad.tipo = tipo
        utilidad.observacion = request.data.get('observacion', utilidad.observacion)
        utilidad.fecha = request.data.get('fecha', utilidad.fecha)

        valor = abs(Decimal(utilidad.valor))
        if valor == 0:
            return Response(
                {"error": "El valor de la utilidad ocasional no puede ser 0."},
                status=status.HTTP_400_BAD_REQUEST
            )
        utilidad.valor = valor
        # 4x1000 sobre el valor; total siempre positivo (valor + 4x1000).
        utilidad.cuatro_por_mil = calcular_cuatro_por_mil(valor, tarjeta)
        utilidad.total = valor + utilidad.cuatro_por_mil
        # El 4x1000 NO se suma al asiento: debito/credito reflejan solo el valor base.
        utilidad.debito = valor
        utilidad.credito = valor

        # La contracuenta se re-resuelve desde la configuracion global segun el tipo.
        sub_cuenta_credito, error_response = _resolver_sub_cuenta_config(utilidad.tipo)
        if error_response:
            return error_response
        utilidad.sub_cuenta = sub_cuenta_credito

        if tarjeta.sub_cuenta_id is None or tarjeta.sub_cuenta.is_deleted:
            return Response(
                {"error": "La tarjeta no tiene una sub-cuenta contable valida asignada."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if utilidad.sub_cuenta_id == tarjeta.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta de la utilidad no puede ser la misma que la de la tarjeta."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                revertir_asiento(utilidad.asiento_id)
                utilidad.save()
                # Direccion del asiento segun el signo (positivo=ganancia / negativo=perdida).
                debito_sc, credito_sc, monto_asiento = _asiento_legs(utilidad, tarjeta)
                asiento_id = registrar_asiento(
                    fecha=utilidad.fecha,
                    debito_sub_cuenta=debito_sc,
                    credito_sub_cuenta=credito_sc,
                    valor=monto_asiento,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=utilidad.id,
                    descripcion=_descripcion_asiento(utilidad),
                    usuario=request.user,
                )
                UtilidadOcasional.objects.filter(pk=utilidad.pk).update(asiento_id=asiento_id)
                utilidad.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('utilidad_ocasional', 'delete')])
def delete_utilidad_ocasional(request, pk):
    """Eliminar una utilidad ocasional (soft delete) y revertir su asiento."""
    try:
        utilidad = get_object_or_404(UtilidadOcasional.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(utilidad.asiento_id)
            UtilidadOcasional.objects.filter(pk=utilidad.pk).update(asiento_id=None)
            utilidad.refresh_from_db(fields=['asiento_id'])
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('utilidad_ocasional', 'delete')])
def restore_utilidad_ocasional(request, pk):
    """Restaurar una utilidad ocasional eliminada y volver a registrar el asiento."""
    try:
        utilidad = get_object_or_404(
            UtilidadOcasional.objects.select_related('tarjeta__sub_cuenta', 'sub_cuenta'), pk=pk
        )
        if not utilidad.is_deleted:
            return Response(
                {"error": "La utilidad ocasional no está eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )

        tarjeta = utilidad.tarjeta
        if tarjeta.sub_cuenta_id is None or tarjeta.sub_cuenta.is_deleted:
            return Response(
                {"error": "La tarjeta no tiene una sub-cuenta contable valida; no se puede restaurar."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if utilidad.sub_cuenta_id == tarjeta.sub_cuenta_id:
            return Response(
                {"error": "La sub-cuenta de la utilidad no puede ser la misma que la de la tarjeta; no se puede restaurar."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # El 4x1000 no entra al asiento; debito/credito reflejan solo el valor base.
                utilidad.debito = utilidad.valor
                utilidad.credito = utilidad.valor
                utilidad.restore()
                # Direccion del asiento segun el signo (positivo=ganancia / negativo=perdida).
                debito_sc, credito_sc, monto_asiento = _asiento_legs(utilidad, tarjeta)
                asiento_id = registrar_asiento(
                    fecha=utilidad.fecha,
                    debito_sub_cuenta=debito_sc,
                    credito_sub_cuenta=credito_sc,
                    valor=monto_asiento,
                    modulo_origen=MODULO_ORIGEN,
                    origen_id=utilidad.id,
                    descripcion=_descripcion_asiento(utilidad),
                    usuario=request.user,
                )
                UtilidadOcasional.objects.filter(pk=utilidad.pk).update(asiento_id=asiento_id)
                utilidad.asiento_id = asiento_id
        except ValidationError as ve:
            return Response({"error": str(ve.messages[0] if ve.messages else ve)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(serialize_utilidad_ocasional(utilidad), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar utilidad ocasional: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('utilidad_ocasional', 'delete')])
def hard_delete_utilidad_ocasional(request, pk):
    """Eliminar permanentemente una utilidad ocasional (revierte el asiento si seguia activo)."""
    try:
        utilidad = get_object_or_404(UtilidadOcasional.objects, pk=pk)
        with transaction.atomic():
            revertir_asiento(utilidad.asiento_id)
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('utilidad_ocasional', 'view')])
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
                'tipo': h.tipo,
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
