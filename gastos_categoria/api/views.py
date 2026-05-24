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

from ..models import GastoCategoria
from sub_cuentas.models import SubCuenta
from .permissions import RolePermission, ModulePermission


def _validar_sub_cuenta(sub_cuenta_id, excluir_pk=None):
    """Valida sub_cuenta obligatoria + no eliminada + UNIQUE intra-tabla."""
    if not sub_cuenta_id:
        return None, Response({"error": "La sub-cuenta es obligatoria."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        sub = SubCuenta.objects.get(pk=sub_cuenta_id)
    except SubCuenta.DoesNotExist:
        return None, Response({"error": "La sub-cuenta especificada no existe."}, status=status.HTTP_404_NOT_FOUND)
    if sub.is_deleted:
        return None, Response({"error": "La sub-cuenta especificada esta eliminada."}, status=status.HTTP_400_BAD_REQUEST)
    qs = GastoCategoria.objects.filter(sub_cuenta_id=sub.pk)
    if excluir_pk is not None:
        qs = qs.exclude(pk=excluir_pk)
    if qs.exists():
        return None, Response(
            {"error": f"La sub-cuenta {sub.codigo} ya esta asociada a otra Categoria de Gasto."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return sub, None


def serialize_categoria(c):
    """Convierte un GastoCategoria a dict."""
    return {
        'id': c.id,
        'nombre': c.nombre,
        'descripcion': c.descripcion,
        'user': {
            'id': c.user.id,
            'name': f"{c.user.first_name} {c.user.last_name}".strip(),
            'username': c.user.username,
        } if c.user else None,
        'debito': str(c.debito),
        'credito': str(c.credito),
        'sub_cuenta': c.sub_cuenta_id,
        'sub_cuenta_codigo': c.sub_cuenta.codigo if c.sub_cuenta else None,
        'sub_cuenta_nombre': c.sub_cuenta.nombre_sub_cuenta if c.sub_cuenta else None,
        'created_at': c.created_at,
        'updated_at': c.updated_at,
        'deleted_at': c.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos_categoria', 'create')])
def create_categoria(request):
    """Crear una nueva categoría de gasto."""
    try:
        nombre = (request.data.get('nombre') or '').strip()
        if not nombre:
            return Response({"error": "El nombre es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        sub_cuenta, error_response = _validar_sub_cuenta(request.data.get('sub_cuenta'))
        if error_response:
            return error_response

        categoria = GastoCategoria.objects.create(
            user=request.user,
            nombre=nombre,
            descripcion=request.data.get('descripcion', '') or '',
            debito=Decimal(str(request.data.get('debito', 0) or 0)),
            credito=Decimal(str(request.data.get('credito', 0) or 0)),
            sub_cuenta=sub_cuenta,
        )
        return Response(serialize_categoria(categoria), status=status.HTTP_201_CREATED)

    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('gastos_categoria', 'view')])
def list_categorias(request):
    """Listar categorías con filtros y paginación."""
    try:
        categorias = GastoCategoria.objects.select_related('user').all()

        search_query = request.query_params.get('search', None)
        if search_query:
            categorias = categorias.filter(
                Q(nombre__icontains=search_query) |
                Q(descripcion__icontains=search_query)
            )

        usuario_filter = request.query_params.get('user', None)
        if usuario_filter:
            categorias = categorias.filter(user_id=usuario_filter)

        # Fechas
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                categorias = categorias.filter(created_at__gte=start_date)
            except ValueError:
                return Response({"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                categorias = categorias.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response({"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            categorias = categorias.filter(deleted_at__isnull=True)

        categorias = categorias.order_by('-created_at')

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(categorias, request)

        data = [serialize_categoria(c) for c in paginated]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response({"error": f"Error al obtener categorías: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('gastos_categoria', 'view')])
def get_categoria(request, pk):
    """Obtener una categoría por ID."""
    try:
        categoria = get_object_or_404(GastoCategoria.objects.select_related('user'), pk=pk)
        return Response(serialize_categoria(categoria), status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al obtener categoría: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos_categoria', 'edit')])
def update_categoria(request, pk):
    """Actualizar una categoría."""
    try:
        categoria = get_object_or_404(GastoCategoria.objects, pk=pk)

        if 'nombre' in request.data:
            nombre = (request.data.get('nombre') or '').strip()
            if not nombre:
                return Response({"error": "El nombre no puede estar vacío."}, status=status.HTTP_400_BAD_REQUEST)
            categoria.nombre = nombre
        if 'descripcion' in request.data:
            categoria.descripcion = request.data.get('descripcion') or ''

        categoria.save()
        return Response(serialize_categoria(categoria), status=status.HTTP_200_OK)

    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos_categoria', 'delete')])
def delete_categoria(request, pk):
    """Eliminar (soft delete) una categoría."""
    try:
        categoria = get_object_or_404(GastoCategoria.objects, pk=pk)
        categoria.soft_delete()
        return Response({"message": "Categoría eliminada correctamente"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al eliminar categoría: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos_categoria', 'delete')])
def restore_categoria(request, pk):
    """Restaurar una categoría eliminada."""
    try:
        categoria = get_object_or_404(GastoCategoria.objects, pk=pk)
        if not categoria.is_deleted:
            return Response({"error": "La categoría no está eliminada"}, status=status.HTTP_400_BAD_REQUEST)
        categoria.restore()
        return Response(serialize_categoria(categoria), status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al restaurar categoría: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos_categoria', 'delete')])
def hard_delete_categoria(request, pk):
    """Eliminar permanentemente una categoría."""
    try:
        categoria = get_object_or_404(GastoCategoria.objects, pk=pk)
        categoria.delete()
        return Response({"message": "Categoría eliminada permanentemente"}, status=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        return Response({"error": f"Error al eliminar categoría: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('gastos_categoria', 'view')])
def categoria_history(request, pk):
    """Obtener el historial de cambios de una categoría."""
    try:
        categoria = get_object_or_404(GastoCategoria.objects, pk=pk)
        history = categoria.history.all()

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
                    'name': f"{h.history_user.first_name} {h.history_user.last_name}".strip(),
                } if h.history_user else None,
                'nombre': h.nombre,
                'descripcion': h.descripcion,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response({"error": f"Error al obtener historial: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
