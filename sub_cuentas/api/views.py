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

from sub_cuentas.models import SubCuenta
from plan_de_cuentas.models import PlanDeCuentas
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


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('sub_cuentas', 'edit')])
def update_sub_cuenta(request, pk):
    """Actualizar una sub-cuenta"""
    try:
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

        try:
            if 'debito' in request.data:
                sub.debito = _parse_decimal(request.data.get('debito'))
            if 'credito' in request.data:
                sub.credito = _parse_decimal(request.data.get('credito'))
            if 'acumulado' in request.data:
                sub.acumulado = _parse_decimal(request.data.get('acumulado'))
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('sub_cuentas', 'delete')])
def delete_sub_cuenta(request, pk):
    """Eliminar una sub-cuenta (soft delete)"""
    try:
        sub = get_object_or_404(SubCuenta.objects, pk=pk)
        sub.soft_delete()
        return Response(
            {"message": "Sub-cuenta eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar sub-cuenta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('sub_cuentas', 'delete')])
def restore_sub_cuenta(request, pk):
    """Restaurar una sub-cuenta eliminada"""
    try:
        sub = get_object_or_404(SubCuenta.objects, pk=pk)
        if not sub.is_deleted:
            return Response(
                {"error": "La sub-cuenta no esta eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )
        sub.restore()
        return Response(serialize_sub_cuenta(sub), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar sub-cuenta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('sub_cuentas', 'delete')])
def hard_delete_sub_cuenta(request, pk):
    """Eliminar permanentemente una sub-cuenta"""
    try:
        sub = get_object_or_404(SubCuenta.objects, pk=pk)
        sub.delete()
        return Response(
            {"message": "Sub-cuenta eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar sub-cuenta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
