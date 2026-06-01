from decimal import Decimal, InvalidOperation
from datetime import datetime

from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from django.core.exceptions import ValidationError

from django.db.models import Sum, Count
from django.db import models as dj_models

from sub_cuentas.models import SubCuenta
from plan_de_cuentas.models import PlanDeCuentas, AcumuladoTipo
from movimiento_contable.models import MovimientoContable, TipoMovimiento
from .permissions import RolePermission, ModulePermission


def serialize_sub_cuenta(sub):
    """Convierte un objeto SubCuenta a diccionario"""
    return {
        'id': sub.id,
        'codigo': sub.codigo,
        'cuenta': sub.cuenta_id,
        'cuenta_codigo_puc': sub.cuenta.codigo_puc if sub.cuenta else None,
        'cuenta_nombre': sub.cuenta.nombre_cuenta if sub.cuenta else None,
        'cuenta_tipo': sub.cuenta.tipo if sub.cuenta else None,
        'cuenta_tipo_display': sub.cuenta.get_tipo_display() if sub.cuenta else None,
        'nombre_sub_cuenta': sub.nombre_sub_cuenta,
        'debito': str(sub.debito),
        'credito': str(sub.credito),
        'acumulado': str(sub.acumulado),
        'user': sub.user_id,
        'user_name': f"{sub.user.first_name} {sub.user.last_name}".strip() if sub.user else None,
        'created_at': sub.created_at,
        'updated_at': sub.updated_at,
        'deleted_at': sub.deleted_at,
    }


def _validar_codigo(valor):
    """3 letras mayusculas + 3 digitos"""
    if not isinstance(valor, str):
        return "El ID debe ser texto."
    import re
    if not re.match(r'^[A-Z]{3}\d{3}$', valor):
        return "El ID debe ser 3 letras mayusculas seguidas de 3 digitos (ej: ABC123)."
    return None


def _parse_decimal(valor, default=Decimal('0')):
    """Convierte un valor a Decimal o devuelve default si esta vacio. Lanza ValueError si invalido."""
    if valor is None or valor == '':
        return default
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Valor numerico invalido: {valor}")


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('sub_cuentas', 'create')])
def create_sub_cuenta(request):
    """Crear una nueva sub-cuenta"""
    try:
        codigo = request.data.get('codigo')
        cuenta_id = request.data.get('cuenta')
        nombre_sub_cuenta = request.data.get('nombre_sub_cuenta')

        if not codigo or not cuenta_id or not nombre_sub_cuenta:
            return Response(
                {"error": "Los campos codigo, cuenta y nombre_sub_cuenta son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        codigo = str(codigo).strip()

        error = _validar_codigo(codigo)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        if SubCuenta.objects.filter(codigo=codigo).exists():
            return Response(
                {"error": f"Ya existe una sub-cuenta con el ID {codigo}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        cuenta = get_object_or_404(PlanDeCuentas, pk=cuenta_id)
        if cuenta.is_deleted:
            return Response(
                {"error": "La cuenta del PUC seleccionada está eliminada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            debito    = _parse_decimal(request.data.get('debito'))
            credito   = _parse_decimal(request.data.get('credito'))
            acumulado = _parse_decimal(request.data.get('acumulado'))
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        sub = SubCuenta.objects.create(
            codigo=codigo,
            cuenta=cuenta,
            nombre_sub_cuenta=nombre_sub_cuenta,
            debito=debito,
            credito=credito,
            acumulado=acumulado,
            user=request.user,
        )

        return Response(serialize_sub_cuenta(sub), status=status.HTTP_201_CREATED)

    except ValidationError as e:
        return Response(
            {"error": f"Error de validacion: {e.message_dict if hasattr(e, 'message_dict') else str(e)}"},
            status=status.HTTP_400_BAD_REQUEST
        )
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
@permission_classes([IsAuthenticated, ModulePermission('sub_cuentas', 'view')])
def list_sub_cuentas(request):
    """Listar sub-cuentas con filtros y paginacion"""
    try:
        subs = SubCuenta.objects.select_related('user', 'cuenta').all()

        # Filtro de busqueda (codigo, nombre_sub_cuenta o nombre/codigo de la cuenta padre)
        search_query = request.query_params.get('search', None)
        if search_query:
            subs = subs.filter(
                Q(codigo__icontains=search_query) |
                Q(nombre_sub_cuenta__icontains=search_query) |
                Q(cuenta__codigo_puc__icontains=search_query) |
                Q(cuenta__nombre_cuenta__icontains=search_query)
            )

        # Filtro por cuenta (FK)
        cuenta_id = request.query_params.get('cuenta', None)
        if cuenta_id:
            subs = subs.filter(cuenta_id=cuenta_id)

        # Filtro por tipo de la cuenta padre
        tipo = request.query_params.get('tipo', None)
        if tipo:
            subs = subs.filter(cuenta__tipo=tipo)

        # Filtro por fecha de creacion
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                subs = subs.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                subs = subs.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            subs = subs.filter(deleted_at__isnull=True)

        # Ordenar
        subs = subs.order_by('codigo')

        # Paginacion
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_subs = paginator.paginate_queryset(subs, request)

        data = [serialize_sub_cuenta(s) for s in paginated_subs]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener sub-cuentas: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('sub_cuentas', 'view')])
def get_sub_cuenta(request, pk):
    """Obtener una sub-cuenta por ID"""
    try:
        sub = get_object_or_404(SubCuenta.objects.select_related('user', 'cuenta'), pk=pk)
        return Response(serialize_sub_cuenta(sub), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener sub-cuenta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Regla de negocio: las sub-cuentas son parcialmente inmutables despues de crearse.
#   - Se permite editar UNICAMENTE: codigo, cuenta (FK a PlanDeCuentas) y nombre_sub_cuenta.
#   - Los campos financieros (debito, credito, acumulado) son inmutables: si llegan en
#     el payload, el PUT se rechaza con 400.
#   - Eliminar (soft/hard) y restaurar siguen bloqueados con 405 para todos los roles,
#     incluido SuperAdmin. La traza historica (history) sigue accesible.
_CAMPOS_FINANCIEROS_INMUTABLES = ('debito', 'credito', 'acumulado')


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('sub_cuentas', 'edit')])
def update_sub_cuenta(request, pk):
    """Actualizar codigo, cuenta y/o nombre_sub_cuenta. Los campos financieros son inmutables."""
    try:
        # Rechazar inmediato si llega cualquier campo financiero, sea cual sea el valor.
        campos_prohibidos = [c for c in _CAMPOS_FINANCIEROS_INMUTABLES if c in request.data]
        if campos_prohibidos:
            return Response(
                {"error": f"Los campos {', '.join(campos_prohibidos)} no se pueden modificar despues de crear la sub-cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sub = get_object_or_404(SubCuenta.objects, pk=pk)

        codigo = request.data.get('codigo')
        if codigo is not None:
            codigo = str(codigo).strip()
            error = _validar_codigo(codigo)
            if error:
                return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
            if SubCuenta.objects.filter(codigo=codigo).exclude(pk=sub.pk).exists():
                return Response(
                    {"error": f"Ya existe otra sub-cuenta con el ID {codigo}."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            sub.codigo = codigo

        cuenta_id = request.data.get('cuenta')
        if cuenta_id is not None:
            cuenta = get_object_or_404(PlanDeCuentas, pk=cuenta_id)
            if cuenta.is_deleted:
                return Response(
                    {"error": "La cuenta del PUC seleccionada está eliminada."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            sub.cuenta = cuenta

        nombre_sub_cuenta = request.data.get('nombre_sub_cuenta')
        if nombre_sub_cuenta is not None:
            sub.nombre_sub_cuenta = nombre_sub_cuenta

        sub.save()

        return Response(serialize_sub_cuenta(sub), status=status.HTTP_200_OK)

    except ValidationError as e:
        return Response(
            {"error": f"Error de validacion: {e.message_dict if hasattr(e, 'message_dict') else str(e)}"},
            status=status.HTTP_400_BAD_REQUEST
        )
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
@permission_classes([IsAuthenticated])
def delete_sub_cuenta(request, pk):
    """Bloqueado: las sub-cuentas no se pueden eliminar despues de crearse."""
    return Response(
        {"error": "Las sub-cuentas no se pueden eliminar despues de crearse."},
        status=status.HTTP_405_METHOD_NOT_ALLOWED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def restore_sub_cuenta(request, pk):
    """Bloqueado: las sub-cuentas no se eliminan, por tanto no hay restauracion."""
    return Response(
        {"error": "Las sub-cuentas no se pueden restaurar (no se eliminan)."},
        status=status.HTTP_405_METHOD_NOT_ALLOWED,
    )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def hard_delete_sub_cuenta(request, pk):
    """Bloqueado: las sub-cuentas no se pueden eliminar despues de crearse."""
    return Response(
        {"error": "Las sub-cuentas no se pueden eliminar despues de crearse."},
        status=status.HTTP_405_METHOD_NOT_ALLOWED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('sub_cuentas', 'view')])
def sub_cuenta_history(request, pk):
    """Obtener el historial de cambios de una sub-cuenta"""
    try:
        sub = get_object_or_404(SubCuenta.objects, pk=pk)
        history = sub.history.all()

        # Paginacion
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
                'codigo': h.codigo,
                'cuenta': h.cuenta_id,
                'nombre_sub_cuenta': h.nombre_sub_cuenta,
                'debito': str(h.debito),
                'credito': str(h.credito),
                'acumulado': str(h.acumulado),
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =========================================================================
# Endpoints contables (Fase 5): saldo, movimientos, balance.
# Leen del libro mayor (MovimientoContable) en vez de los campos cacheados
# de SubCuenta, para tener siempre el valor mas actualizado.
# =========================================================================

def _calcular_saldo(sub):
    """Devuelve (debito_total, credito_total, acumulado) leyendo MovimientoContable."""
    movs = MovimientoContable.objects.filter(sub_cuenta_id=sub.pk, deleted_at__isnull=True)
    total_debito  = movs.filter(tipo_movimiento=TipoMovimiento.DEBITO ).aggregate(s=Sum('valor'))['s'] or Decimal('0')
    total_credito = movs.filter(tipo_movimiento=TipoMovimiento.CREDITO).aggregate(s=Sum('valor'))['s'] or Decimal('0')

    tipo_acumulado = sub.cuenta.acumulado if sub.cuenta_id else None
    if tipo_acumulado == AcumuladoTipo.DEBITO_CREDITO:
        acumulado = total_debito - total_credito
    elif tipo_acumulado == AcumuladoTipo.CREDITO_DEBITO:
        acumulado = total_credito - total_debito
    else:
        acumulado = Decimal('0')
    return total_debito, total_credito, acumulado


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('sub_cuentas', 'view')])
def saldo_sub_cuenta(request, pk):
    """Saldo actual de una sub-cuenta calculado desde el libro mayor."""
    try:
        sub = get_object_or_404(SubCuenta.objects.select_related('cuenta'), pk=pk)
        debito_total, credito_total, acumulado = _calcular_saldo(sub)
        return Response({
            'sub_cuenta': sub.pk,
            'codigo': sub.codigo,
            'nombre_sub_cuenta': sub.nombre_sub_cuenta,
            'cuenta': sub.cuenta_id,
            'cuenta_codigo_puc': sub.cuenta.codigo_puc if sub.cuenta else None,
            'cuenta_nombre': sub.cuenta.nombre_cuenta if sub.cuenta else None,
            'cuenta_tipo': sub.cuenta.tipo if sub.cuenta else None,
            'cuenta_tipo_display': sub.cuenta.get_tipo_display() if sub.cuenta else None,
            'cuenta_acumulado_tipo': sub.cuenta.acumulado if sub.cuenta else None,
            'debito_total': str(debito_total),
            'credito_total': str(credito_total),
            'acumulado': str(acumulado),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al calcular saldo: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('sub_cuentas', 'view')])
def movimientos_sub_cuenta(request, pk):
    """Lista paginada de movimientos contables de una sub-cuenta.

    Filtros: modulo_origen, fecha_start, fecha_end, tipo_movimiento, include_deleted=1.
    """
    try:
        sub = get_object_or_404(SubCuenta.objects, pk=pk)
        movimientos = MovimientoContable.objects.select_related('usuario').filter(
            sub_cuenta_id=sub.pk
        )

        modulo_origen = request.query_params.get('modulo_origen')
        if modulo_origen:
            movimientos = movimientos.filter(modulo_origen=modulo_origen)

        tipo_movimiento = request.query_params.get('tipo_movimiento')
        if tipo_movimiento:
            movimientos = movimientos.filter(tipo_movimiento=tipo_movimiento)

        fecha_start = request.query_params.get('fecha_start')
        if fecha_start:
            try:
                start = datetime.strptime(fecha_start, '%Y-%m-%d').date()
                movimientos = movimientos.filter(fecha__gte=start)
            except ValueError:
                return Response({"error": "El formato de fecha_start debe ser YYYY-MM-DD."},
                                status=status.HTTP_400_BAD_REQUEST)

        fecha_end = request.query_params.get('fecha_end')
        if fecha_end:
            try:
                end = datetime.strptime(fecha_end, '%Y-%m-%d').date()
                end_inclusive = datetime.combine(end, datetime.max.time())
                movimientos = movimientos.filter(fecha__lte=end_inclusive)
            except ValueError:
                return Response({"error": "El formato de fecha_end debe ser YYYY-MM-DD."},
                                status=status.HTTP_400_BAD_REQUEST)

        include_deleted = request.query_params.get('include_deleted')
        if include_deleted != '1':
            movimientos = movimientos.filter(deleted_at__isnull=True)

        movimientos = movimientos.order_by('-fecha', '-id')

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        page = paginator.paginate_queryset(movimientos, request)

        data = []
        for m in page:
            data.append({
                'id': m.id,
                'asiento_id': str(m.asiento_id),
                'tipo_movimiento': m.tipo_movimiento,
                'tipo_movimiento_display': m.get_tipo_movimiento_display(),
                'valor': str(m.valor),
                'fecha': m.fecha,
                'modulo_origen': m.modulo_origen,
                'origen_id': m.origen_id,
                'descripcion': m.descripcion,
                'usuario': m.usuario_id,
                'usuario_name': f"{m.usuario.first_name} {m.usuario.last_name}".strip() if m.usuario else None,
                'created_at': m.created_at,
                'deleted_at': m.deleted_at,
            })
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener movimientos de la sub-cuenta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('sub_cuentas', 'view')])
def balance_sub_cuentas(request):
    """Snapshot de saldo (debito_total, credito_total, acumulado) de todas las
    sub-cuentas activas, calculado en una sola query con aggregations.

    Filtros: cuenta (FK a PlanDeCuentas), tipo (tipo de cuenta PUC),
    search (en codigo o nombre), include_deleted=1.
    """
    try:
        qs = SubCuenta.objects.select_related('cuenta').all()

        cuenta_id = request.query_params.get('cuenta')
        if cuenta_id:
            qs = qs.filter(cuenta_id=cuenta_id)

        tipo = request.query_params.get('tipo')
        if tipo:
            qs = qs.filter(cuenta__tipo=tipo)

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(codigo__icontains=search) |
                Q(nombre_sub_cuenta__icontains=search) |
                Q(cuenta__nombre_cuenta__icontains=search) |
                Q(cuenta__codigo_puc__icontains=search)
            )

        include_deleted = request.query_params.get('include_deleted')
        if include_deleted != '1':
            qs = qs.filter(deleted_at__isnull=True)

        qs = qs.order_by('codigo')

        page_size_param = request.query_params.get('page_size', 25)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 25

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        page = paginator.paginate_queryset(qs, request)

        sub_ids = [s.pk for s in page]
        totales = {sid: {'debito': Decimal('0'), 'credito': Decimal('0')} for sid in sub_ids}
        for row in (MovimientoContable.objects
                    .filter(sub_cuenta_id__in=sub_ids, deleted_at__isnull=True)
                    .values('sub_cuenta_id', 'tipo_movimiento')
                    .annotate(total=Sum('valor'))):
            totales[row['sub_cuenta_id']][row['tipo_movimiento']] = row['total'] or Decimal('0')

        data = []
        for sub in page:
            t = totales.get(sub.pk, {'debito': Decimal('0'), 'credito': Decimal('0')})
            debito_total  = t['debito']
            credito_total = t['credito']
            tipo_acum = sub.cuenta.acumulado if sub.cuenta_id else None
            if tipo_acum == AcumuladoTipo.DEBITO_CREDITO:
                acumulado = debito_total - credito_total
            elif tipo_acum == AcumuladoTipo.CREDITO_DEBITO:
                acumulado = credito_total - debito_total
            else:
                acumulado = Decimal('0')

            data.append({
                'sub_cuenta': sub.pk,
                'codigo': sub.codigo,
                'nombre_sub_cuenta': sub.nombre_sub_cuenta,
                'cuenta': sub.cuenta_id,
                'cuenta_codigo_puc': sub.cuenta.codigo_puc if sub.cuenta else None,
                'cuenta_nombre': sub.cuenta.nombre_cuenta if sub.cuenta else None,
                'cuenta_tipo': sub.cuenta.tipo if sub.cuenta else None,
                'cuenta_tipo_display': sub.cuenta.get_tipo_display() if sub.cuenta else None,
                'debito_total': str(debito_total),
                'credito_total': str(credito_total),
                'acumulado': str(acumulado),
                'deleted_at': sub.deleted_at,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al calcular balance: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('sub_cuentas', 'view')])
def balance_resumen(request):
    """KPIs agregados por tipo de cuenta del PUC.

    Devuelve `resumen[tipo]` con `debito_total`, `credito_total`, `acumulado`
    y `sub_cuentas_count` para cada tipo (activo, pasivo, patrimonio, ingreso,
    gasto). Lo usan las tarjetas resumen del dashboard contable.
    """
    try:
        rows = (
            MovimientoContable.objects
                .filter(deleted_at__isnull=True, sub_cuenta__deleted_at__isnull=True)
                .values('sub_cuenta__cuenta__tipo', 'tipo_movimiento')
                .annotate(total=Sum('valor'))
        )
        conteos = dict(
            SubCuenta.objects
                .filter(deleted_at__isnull=True)
                .values('cuenta__tipo')
                .annotate(c=Count('pk'))
                .values_list('cuenta__tipo', 'c')
        )

        TIPOS = ['activo', 'pasivo', 'patrimonio', 'ingreso', 'gasto']
        resumen = {
            tipo: {
                'debito_total':  Decimal('0'),
                'credito_total': Decimal('0'),
                'acumulado':     Decimal('0'),
                'sub_cuentas_count': conteos.get(tipo, 0),
            } for tipo in TIPOS
        }

        for row in rows:
            tipo = row['sub_cuenta__cuenta__tipo']
            if tipo not in resumen:
                continue
            if row['tipo_movimiento'] == TipoMovimiento.DEBITO:
                resumen[tipo]['debito_total'] = row['total'] or Decimal('0')
            else:
                resumen[tipo]['credito_total'] = row['total'] or Decimal('0')

        for tipo, data in resumen.items():
            d = data['debito_total']
            c = data['credito_total']
            data['acumulado'] = (d - c) if tipo in ('activo', 'gasto') else (c - d)
            data['debito_total']  = str(d)
            data['credito_total'] = str(c)
            data['acumulado']     = str(data['acumulado'])

        return Response({
            'resumen': resumen,
            'total_sub_cuentas': sum(conteos.values()),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al calcular resumen: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

