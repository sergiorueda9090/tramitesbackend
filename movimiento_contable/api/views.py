"""Endpoints read-only del libro mayor.

No exponemos create/update/delete: el libro solo se modifica desde
`movimiento_contable.services.registrar_asiento` / `revertir_asiento`,
que a su vez son llamados por los modulos de origen (devoluciones,
recepcion_pago, gastos, ...).
"""
from datetime import datetime

from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q

from movimiento_contable.models import MovimientoContable
from .permissions import RolePermission, ModulePermission


def serialize_movimiento(mov):
    return {
        'id': mov.id,
        'asiento_id': str(mov.asiento_id),
        'sub_cuenta': mov.sub_cuenta_id,
        'sub_cuenta_codigo': mov.sub_cuenta.codigo if mov.sub_cuenta else None,
        'sub_cuenta_nombre': mov.sub_cuenta.nombre_sub_cuenta if mov.sub_cuenta else None,
        'tipo_movimiento': mov.tipo_movimiento,
        'tipo_movimiento_display': mov.get_tipo_movimiento_display(),
        'valor': str(mov.valor),
        'fecha': mov.fecha,
        'modulo_origen': mov.modulo_origen,
        'origen_id': mov.origen_id,
        'descripcion': mov.descripcion,
        'usuario': mov.usuario_id,
        'usuario_name': f"{mov.usuario.first_name} {mov.usuario.last_name}".strip() if mov.usuario else None,
        'created_at': mov.created_at,
        'updated_at': mov.updated_at,
        'deleted_at': mov.deleted_at,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('movimiento_contable', 'view')])
def list_movimientos(request):
    """Lista paginada del libro mayor. Filtros opcionales:
    sub_cuenta, modulo_origen, origen_id, tipo_movimiento, fecha_start, fecha_end,
    asiento_id, search (descripcion), include_deleted=1.
    """
    try:
        movimientos = MovimientoContable.objects.select_related('sub_cuenta', 'usuario')

        sub_cuenta_id = request.query_params.get('sub_cuenta')
        if sub_cuenta_id:
            movimientos = movimientos.filter(sub_cuenta_id=sub_cuenta_id)

        modulo_origen = request.query_params.get('modulo_origen')
        if modulo_origen:
            movimientos = movimientos.filter(modulo_origen=modulo_origen)

        origen_id = request.query_params.get('origen_id')
        if origen_id:
            movimientos = movimientos.filter(origen_id=origen_id)

        tipo_movimiento = request.query_params.get('tipo_movimiento')
        if tipo_movimiento:
            movimientos = movimientos.filter(tipo_movimiento=tipo_movimiento)

        asiento_id = request.query_params.get('asiento_id')
        if asiento_id:
            movimientos = movimientos.filter(asiento_id=asiento_id)

        search = request.query_params.get('search')
        if search:
            movimientos = movimientos.filter(
                Q(descripcion__icontains=search) |
                Q(sub_cuenta__codigo__icontains=search) |
                Q(sub_cuenta__nombre_sub_cuenta__icontains=search)
            )

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

        data = [serialize_movimiento(m) for m in page]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener movimientos contables: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('movimiento_contable', 'view')])
def get_movimiento(request, pk):
    """Detalle de un movimiento por PK."""
    try:
        mov = get_object_or_404(
            MovimientoContable.objects.select_related('sub_cuenta', 'usuario'), pk=pk
        )
        return Response(serialize_movimiento(mov), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener movimiento contable: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('movimiento_contable', 'view')])
def get_asiento(request, asiento_id):
    """Devuelve los dos movimientos (debito + credito) de un mismo asiento.
    Util para auditar el par completo de la partida doble.
    """
    try:
        movs = MovimientoContable.objects.select_related('sub_cuenta', 'usuario').filter(
            asiento_id=asiento_id
        ).order_by('tipo_movimiento')
        if not movs.exists():
            return Response({"error": "Asiento no encontrado."},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                'asiento_id': str(asiento_id),
                'movimientos': [serialize_movimiento(m) for m in movs],
            },
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al obtener asiento contable: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('movimiento_contable', 'view')])
def movimiento_history(request, pk):
    """Historial (django-simple-history) de un movimiento."""
    try:
        mov = get_object_or_404(MovimientoContable.objects, pk=pk)
        history = mov.history.all()

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        page = paginator.paginate_queryset(history, request)

        data = []
        for h in page:
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
                'asiento_id': str(h.asiento_id),
                'sub_cuenta': h.sub_cuenta_id,
                'tipo_movimiento': h.tipo_movimiento,
                'valor': str(h.valor),
                'fecha': h.fecha,
                'modulo_origen': h.modulo_origen,
                'origen_id': h.origen_id,
                'descripcion': h.descripcion,
                'deleted_at': h.deleted_at,
            })
        return paginator.get_paginated_response(data)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial del movimiento: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
