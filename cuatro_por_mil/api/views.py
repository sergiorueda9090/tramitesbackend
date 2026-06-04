from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta

from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError, transaction
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate, TruncMonth, Coalesce

from cuatro_por_mil.models import CuatroPorMil, CuatroPorMilConfig, ModuloOrigen
from cuatro_por_mil.services import sincronizar_asiento_4xmil
from tarjetas.models import Tarjeta
from sub_cuentas.models import SubCuenta
from movimiento_contable.services import revertir_asiento
from .permissions import RolePermission, ModulePermission


MODULOS_VALIDOS = {choice.value for choice in ModuloOrigen}
MODULO_DISPLAY = dict(ModuloOrigen.choices)


def serialize_cuatro_por_mil(registro):
    """Convierte un objeto CuatroPorMil a diccionario."""
    return {
        'id': registro.id,
        'modulo': registro.modulo,
        'modulo_display': registro.get_modulo_display(),
        'registro_id': registro.registro_id,
        'valor': str(registro.valor),
        'valor_base': str(registro.valor_base),
        'tarjeta': {
            'id': registro.tarjeta.id,
            'numero': registro.tarjeta.numero,
            'titular': registro.tarjeta.titular,
            'cuatro_por_mil': registro.tarjeta.cuatro_por_mil,
            'sub_cuenta_codigo': registro.tarjeta.sub_cuenta.codigo if registro.tarjeta.sub_cuenta_id else None,
            'sub_cuenta_nombre': registro.tarjeta.sub_cuenta.nombre_sub_cuenta if registro.tarjeta.sub_cuenta_id else None,
        } if registro.tarjeta else None,
        'asiento_id': str(registro.asiento_id) if registro.asiento_id else None,
        'observacion': registro.observacion,
        'fecha': registro.fecha,
        'usuario': registro.usuario_id,
        'usuario_name': (
            f"{registro.usuario.first_name} {registro.usuario.last_name}".strip()
            if registro.usuario else None
        ),
        'created_at': registro.created_at,
        'updated_at': registro.updated_at,
        'deleted_at': registro.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cuatro_por_mil', 'create')])
def create_cuatro_por_mil(request):
    """Crear un registro de 4x1000."""
    try:
        modulo = request.data.get('modulo')
        if not modulo:
            return Response({"error": "El módulo es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if modulo not in MODULOS_VALIDOS:
            return Response(
                {"error": f"Módulo inválido. Valores permitidos: {sorted(MODULOS_VALIDOS)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        registro_id = request.data.get('registro_id')
        if registro_id is None:
            return Response({"error": "El registro_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            registro_id = int(registro_id)
        except (ValueError, TypeError):
            return Response({"error": "registro_id debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST)

        valor_raw = request.data.get('valor')
        if valor_raw is None:
            return Response({"error": "El valor es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            valor = Decimal(str(valor_raw))
        except (InvalidOperation, ValueError, TypeError):
            return Response({"error": "valor debe ser numérico."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            valor_base = Decimal(str(request.data.get('valor_base', '0')))
        except (InvalidOperation, ValueError, TypeError):
            return Response({"error": "valor_base debe ser numérico."}, status=status.HTTP_400_BAD_REQUEST)

        tarjeta = None
        tarjeta_id = request.data.get('tarjeta_id') or request.data.get('tarjeta')
        if tarjeta_id:
            tarjeta = get_object_or_404(Tarjeta.objects.filter(deleted_at__isnull=True), pk=tarjeta_id)

        with transaction.atomic():
            registro = CuatroPorMil.objects.create(
                modulo=modulo,
                registro_id=registro_id,
                valor=valor,
                valor_base=valor_base,
                tarjeta=tarjeta,
                observacion=request.data.get('observacion', ''),
                fecha=request.data.get('fecha'),
                usuario=request.user,
            )
            sincronizar_asiento_4xmil(registro, usuario=request.user)

        return Response(serialize_cuatro_por_mil(registro), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('cuatro_por_mil', 'view')])
def list_cuatro_por_mil(request):
    """Listar registros de 4x1000 con filtros y paginación."""
    try:
        registros = CuatroPorMil.objects.select_related('tarjeta__sub_cuenta', 'usuario').all()

        modulo = request.query_params.get('modulo')
        if modulo:
            if modulo not in MODULOS_VALIDOS:
                return Response(
                    {"error": f"Módulo inválido. Valores permitidos: {sorted(MODULOS_VALIDOS)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            registros = registros.filter(modulo=modulo)

        registro_id = request.query_params.get('registro_id')
        if registro_id:
            try:
                registros = registros.filter(registro_id=int(registro_id))
            except (ValueError, TypeError):
                return Response({"error": "registro_id debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST)

        tarjeta_id = request.query_params.get('tarjeta_id')
        if tarjeta_id:
            try:
                registros = registros.filter(tarjeta_id=int(tarjeta_id))
            except (ValueError, TypeError):
                return Response({"error": "tarjeta_id debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST)

        search_query = request.query_params.get('search')
        if search_query:
            registros = registros.filter(observacion__icontains=search_query)

        start_date_str = request.query_params.get('start_date')
        end_date_str   = request.query_params.get('end_date')

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                registros = registros.filter(fecha__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                registros = registros.filter(fecha__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        include_deleted = request.query_params.get('include_deleted')
        if include_deleted != '1':
            registros = registros.filter(deleted_at__isnull=True)

        registros = registros.order_by('-created_at')

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(registros, request)

        data = [serialize_cuatro_por_mil(r) for r in paginated]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener registros: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('cuatro_por_mil', 'view')])
def get_cuatro_por_mil(request, pk):
    """Obtener un registro de 4x1000 por ID."""
    try:
        registro = get_object_or_404(
            CuatroPorMil.objects.select_related('tarjeta__sub_cuenta', 'usuario'),
            pk=pk
        )
        return Response(serialize_cuatro_por_mil(registro), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener registro: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cuatro_por_mil', 'edit')])
def update_cuatro_por_mil(request, pk):
    """Actualizar un registro de 4x1000."""
    try:
        registro = get_object_or_404(CuatroPorMil.objects, pk=pk)

        if 'modulo' in request.data:
            modulo = request.data.get('modulo')
            if modulo not in MODULOS_VALIDOS:
                return Response(
                    {"error": f"Módulo inválido. Valores permitidos: {sorted(MODULOS_VALIDOS)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            registro.modulo = modulo

        if 'registro_id' in request.data:
            try:
                registro.registro_id = int(request.data.get('registro_id'))
            except (ValueError, TypeError):
                return Response({"error": "registro_id debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST)

        if 'valor' in request.data:
            try:
                registro.valor = Decimal(str(request.data.get('valor')))
            except (InvalidOperation, ValueError, TypeError):
                return Response({"error": "valor debe ser numérico."}, status=status.HTTP_400_BAD_REQUEST)

        if 'valor_base' in request.data:
            try:
                registro.valor_base = Decimal(str(request.data.get('valor_base')))
            except (InvalidOperation, ValueError, TypeError):
                return Response({"error": "valor_base debe ser numérico."}, status=status.HTTP_400_BAD_REQUEST)

        if 'tarjeta_id' in request.data or 'tarjeta' in request.data:
            tarjeta_id = request.data.get('tarjeta_id') or request.data.get('tarjeta')
            if tarjeta_id in (None, '', 0, '0'):
                registro.tarjeta = None
            else:
                registro.tarjeta = get_object_or_404(
                    Tarjeta.objects.filter(deleted_at__isnull=True), pk=tarjeta_id
                )

        registro.observacion = request.data.get('observacion', registro.observacion)
        registro.fecha       = request.data.get('fecha', registro.fecha)

        with transaction.atomic():
            registro.save()
            # El valor / tarjeta pudo cambiar: re-sincronizar el asiento contable.
            sincronizar_asiento_4xmil(registro, usuario=request.user)

        return Response(serialize_cuatro_por_mil(registro), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cuatro_por_mil', 'delete')])
def delete_cuatro_por_mil(request, pk):
    """Eliminar un registro de 4x1000 (soft delete)."""
    try:
        registro = get_object_or_404(CuatroPorMil.objects, pk=pk)
        with transaction.atomic():
            registro.soft_delete()
            # Revertir el asiento contable asociado.
            sincronizar_asiento_4xmil(registro, usuario=request.user)
        return Response(
            {"message": "Registro eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar registro: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cuatro_por_mil', 'delete')])
def restore_cuatro_por_mil(request, pk):
    """Restaurar un registro de 4x1000 eliminado."""
    try:
        registro = get_object_or_404(
            CuatroPorMil.objects.select_related('tarjeta__sub_cuenta'), pk=pk
        )
        if not registro.is_deleted:
            return Response(
                {"error": "El registro no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            registro.restore()
            # Volver a postear el asiento contable del 4x1000.
            sincronizar_asiento_4xmil(registro, usuario=request.user)
        return Response(serialize_cuatro_por_mil(registro), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar registro: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cuatro_por_mil', 'delete')])
def hard_delete_cuatro_por_mil(request, pk):
    """Eliminar permanentemente un registro de 4x1000."""
    try:
        registro = get_object_or_404(CuatroPorMil.objects, pk=pk)
        with transaction.atomic():
            # Revertir el asiento contable antes de borrar definitivamente.
            if registro.asiento_id:
                revertir_asiento(registro.asiento_id)
            registro.delete()
        return Response(
            {"message": "Registro eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar registro: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cuatro_por_mil', 'view')])
def cuatro_por_mil_history(request, pk):
    """Obtener el historial de cambios de un registro de 4x1000."""
    try:
        registro = get_object_or_404(CuatroPorMil.objects, pk=pk)
        history = registro.history.all()

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
                'modulo': h.modulo,
                'registro_id': h.registro_id,
                'valor': str(h.valor),
                'valor_base': str(h.valor_base),
                'tarjeta_id': h.tarjeta_id,
                'observacion': h.observacion,
                'fecha': h.fecha,
                'usuario_id': h.usuario_id,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ---------------------------------------------------------------------------
# Configuración (singleton): sub-cuenta de débito por defecto
# ---------------------------------------------------------------------------

def serialize_config(cfg):
    """Convierte la configuracion (singleton) a diccionario."""
    sc = cfg.sub_cuenta_debito
    return {
        'sub_cuenta_debito': cfg.sub_cuenta_debito_id,
        'sub_cuenta_debito_codigo': sc.codigo if sc else None,
        'sub_cuenta_debito_nombre': sc.nombre_sub_cuenta if sc else None,
        'updated_at': cfg.updated_at,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('cuatro_por_mil', 'view')])
def get_config(request):
    """Obtener la configuracion del modulo (sub-cuenta de debito por defecto)."""
    try:
        cfg = CuatroPorMilConfig.load()
        return Response(serialize_config(cfg), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener la configuracion: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cuatro_por_mil', 'edit')])
def update_config(request):
    """Actualizar la sub-cuenta de debito por defecto.

    Acepta `sub_cuenta_debito` (id). Si viene vacio/None se limpia. Debe ser una
    sub-cuenta valida (no eliminada).
    """
    try:
        cfg = CuatroPorMilConfig.load()

        if 'sub_cuenta_debito' in request.data:
            val = request.data.get('sub_cuenta_debito')
            if val in (None, '', 0, '0'):
                cfg.sub_cuenta_debito = None
            else:
                try:
                    sub = SubCuenta.objects.get(pk=val)
                except SubCuenta.DoesNotExist:
                    return Response(
                        {"error": "La sub-cuenta especificada no existe."},
                        status=status.HTTP_404_NOT_FOUND
                    )
                if sub.is_deleted:
                    return Response(
                        {"error": "La sub-cuenta especificada esta eliminada."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                cfg.sub_cuenta_debito = sub

        cfg.save()
        return Response(serialize_config(cfg), status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al guardar la configuracion: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ---------------------------------------------------------------------------
# Estadísticas / Dashboard
# ---------------------------------------------------------------------------

def _apply_stats_filters(qs, request):
    """Aplica los mismos filtros que list_cuatro_por_mil sobre un queryset.

    Devuelve (queryset, error_response_or_None). Si error_response_or_None no
    es None, la vista debe devolverlo directamente.
    """
    modulo = request.query_params.get('modulo')
    if modulo:
        if modulo not in MODULOS_VALIDOS:
            return qs, Response(
                {"error": f"Módulo inválido. Valores permitidos: {sorted(MODULOS_VALIDOS)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        qs = qs.filter(modulo=modulo)

    tarjeta_id = request.query_params.get('tarjeta_id')
    if tarjeta_id:
        try:
            qs = qs.filter(tarjeta_id=int(tarjeta_id))
        except (ValueError, TypeError):
            return qs, Response(
                {"error": "tarjeta_id debe ser un entero."},
                status=status.HTTP_400_BAD_REQUEST
            )

    search_query = request.query_params.get('search')
    if search_query:
        qs = qs.filter(observacion__icontains=search_query)

    start_date_str = request.query_params.get('start_date')
    end_date_str   = request.query_params.get('end_date')

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            qs = qs.filter(fecha__gte=start_date)
        except ValueError:
            return qs, Response(
                {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            end_date_inclusive = datetime.combine(end_date, datetime.max.time())
            qs = qs.filter(fecha__lte=end_date_inclusive)
        except ValueError:
            return qs, Response(
                {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

    include_deleted = request.query_params.get('include_deleted')
    if include_deleted != '1':
        qs = qs.filter(deleted_at__isnull=True)

    return qs, None


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('cuatro_por_mil', 'view')])
def stats_cuatro_por_mil(request):
    """Resumen agregado de 4x1000 según los filtros aplicados.

    Devuelve totales globales, breakdown por módulo, top tarjetas y serie temporal.
    """
    try:
        qs = CuatroPorMil.objects.all()
        qs, err = _apply_stats_filters(qs, request)
        if err is not None:
            return err

        # ----- Totales globales -----
        totales_agg = qs.aggregate(
            registros        = Count('id'),
            valor_total      = Coalesce(Sum('valor'),      Decimal('0')),
            valor_base_total = Coalesce(Sum('valor_base'), Decimal('0')),
        )
        tarjetas_distintas = qs.exclude(tarjeta__isnull=True) \
                               .values('tarjeta_id').distinct().count()

        totales = {
            'registros':          totales_agg['registros'],
            'valor_total':        str(totales_agg['valor_total']),
            'valor_base_total':   str(totales_agg['valor_base_total']),
            'tarjetas_distintas': tarjetas_distintas,
        }
        valor_total_dec = Decimal(totales_agg['valor_total'] or 0)

        # ----- Breakdown por módulo -----
        por_modulo_qs = (
            qs.values('modulo')
              .annotate(count=Count('id'),
                        valor=Coalesce(Sum('valor'), Decimal('0')),
                        valor_base=Coalesce(Sum('valor_base'), Decimal('0')))
              .order_by('-valor')
        )
        por_modulo = []
        for row in por_modulo_qs:
            valor = Decimal(row['valor'] or 0)
            porcentaje = float((valor / valor_total_dec) * 100) if valor_total_dec > 0 else 0.0
            por_modulo.append({
                'modulo':         row['modulo'],
                'modulo_display': MODULO_DISPLAY.get(row['modulo'], row['modulo']),
                'count':          row['count'],
                'valor':          str(valor),
                'valor_base':     str(row['valor_base']),
                'porcentaje':     round(porcentaje, 2),
            })

        # ----- Top tarjetas -----
        try:
            top_n = int(request.query_params.get('top_tarjetas', 10))
        except (ValueError, TypeError):
            top_n = 10
        top_n = max(1, min(top_n, 50))

        por_tarjeta_qs = (
            qs.exclude(tarjeta__isnull=True)
              .values('tarjeta_id', 'tarjeta__titular', 'tarjeta__numero')
              .annotate(count=Count('id'),
                        valor=Coalesce(Sum('valor'), Decimal('0')))
              .order_by('-valor')[:top_n]
        )
        por_tarjeta = []
        for row in por_tarjeta_qs:
            numero = row['tarjeta__numero'] or ''
            por_tarjeta.append({
                'tarjeta_id':    row['tarjeta_id'],
                'titular':       row['tarjeta__titular'],
                'numero_last4':  numero[-4:] if numero else '',
                'count':         row['count'],
                'valor':         str(row['valor']),
            })

        # ----- Serie temporal -----
        # Decide día vs mes según el rango filtrado (si no hay rango, usa 90d).
        date_qs = qs.exclude(fecha__isnull=True)

        start_date_str = request.query_params.get('start_date')
        end_date_str   = request.query_params.get('end_date')
        try:
            d0 = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            d1 = datetime.strptime(end_date_str,   '%Y-%m-%d').date() if end_date_str   else None
        except ValueError:
            d0, d1 = None, None

        if d0 and d1:
            span_days = (d1 - d0).days
        else:
            span_days = 90  # default razonable

        granularidad = 'dia' if span_days <= 90 else 'mes'
        trunc_fn = TruncDate('fecha') if granularidad == 'dia' else TruncMonth('fecha')

        serie_qs = (
            date_qs.annotate(periodo=trunc_fn)
                   .values('periodo')
                   .annotate(count=Count('id'),
                             valor=Coalesce(Sum('valor'), Decimal('0')))
                   .order_by('periodo')
        )
        serie_temporal = [{
            'periodo': row['periodo'].strftime('%Y-%m-%d') if row['periodo'] else None,
            'count':   row['count'],
            'valor':   str(row['valor']),
        } for row in serie_qs]

        return Response({
            'totales':        totales,
            'por_modulo':     por_modulo,
            'por_tarjeta':    por_tarjeta,
            'serie_temporal': serie_temporal,
            'granularidad':   granularidad,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener estadísticas: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
