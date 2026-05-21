from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.core.exceptions import ValidationError
from datetime import datetime

from plan_de_cuentas.models import PlanDeCuentas, TipoCuenta
from .permissions import RolePermission, ModulePermission


def serialize_plan_de_cuentas(cuenta):
    """Convierte un objeto PlanDeCuentas a diccionario"""
    return {
        'id': cuenta.id,
        'tipo': cuenta.tipo,
        'tipo_display': cuenta.get_tipo_display(),
        'codigo_puc': cuenta.codigo_puc,
        'nombre_cuenta': cuenta.nombre_cuenta,
        'acumulado': cuenta.acumulado,
        'acumulado_display': cuenta.get_acumulado_display(),
        'user': cuenta.user_id,
        'user_name': f"{cuenta.user.first_name} {cuenta.user.last_name}".strip() if cuenta.user else None,
        'created_at': cuenta.created_at,
        'updated_at': cuenta.updated_at,
        'deleted_at': cuenta.deleted_at,
    }


def _validar_tipo(valor):
    if valor not in TipoCuenta.values:
        return f"Tipo invalido. Valores permitidos: {', '.join(TipoCuenta.values)}."
    return None


# NOTA: 'acumulado' no se valida ni se acepta desde el cliente; el modelo lo
# deriva automaticamente desde 'tipo' en save() (ver ACUMULADO_POR_TIPO).


def _validar_codigo_puc(valor):
    if not isinstance(valor, str) or not valor.isdigit() or len(valor) != 4:
        return "El Codigo PUC debe ser numerico de 4 digitos."
    return None


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('plan_de_cuentas', 'create')])
def create_plan_de_cuentas(request):
    """Crear una nueva cuenta del PUC"""
    try:
        tipo = request.data.get('tipo')
        codigo_puc = request.data.get('codigo_puc')
        nombre_cuenta = request.data.get('nombre_cuenta')

        if not tipo or not codigo_puc or not nombre_cuenta:
            return Response(
                {"error": "Los campos tipo, codigo_puc y nombre_cuenta son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        codigo_puc = str(codigo_puc).strip()

        error = _validar_tipo(tipo)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        error = _validar_codigo_puc(codigo_puc)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        if PlanDeCuentas.objects.filter(codigo_puc=codigo_puc).exists():
            return Response(
                {"error": f"Ya existe una cuenta con el Codigo PUC {codigo_puc}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 'acumulado' lo deriva el modelo automaticamente en save() segun el tipo.
        cuenta = PlanDeCuentas.objects.create(
            tipo=tipo,
            codigo_puc=codigo_puc,
            nombre_cuenta=nombre_cuenta,
            user=request.user,
        )

        return Response(serialize_plan_de_cuentas(cuenta), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('plan_de_cuentas', 'view')])
def list_plan_de_cuentas(request):
    """Listar cuentas del PUC con filtros y paginacion"""
    try:
        cuentas = PlanDeCuentas.objects.select_related('user').all()

        # Filtro de busqueda (por codigo o nombre)
        search_query = request.query_params.get('search', None)
        if search_query:
            from django.db.models import Q
            cuentas = cuentas.filter(
                Q(codigo_puc__icontains=search_query) |
                Q(nombre_cuenta__icontains=search_query)
            )

        # Filtro por tipo
        tipo = request.query_params.get('tipo', None)
        if tipo:
            cuentas = cuentas.filter(tipo=tipo)

        # Filtro por acumulado
        acumulado = request.query_params.get('acumulado', None)
        if acumulado:
            cuentas = cuentas.filter(acumulado=acumulado)

        # Filtro por fecha de creacion
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                cuentas = cuentas.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                cuentas = cuentas.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            cuentas = cuentas.filter(deleted_at__isnull=True)

        # Ordenar por codigo PUC (estructura natural del PUC)
        cuentas = cuentas.order_by('codigo_puc')

        # Paginacion
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_cuentas = paginator.paginate_queryset(cuentas, request)

        data = [serialize_plan_de_cuentas(c) for c in paginated_cuentas]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener cuentas: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('plan_de_cuentas', 'view')])
def get_plan_de_cuentas(request, pk):
    """Obtener una cuenta del PUC por ID"""
    try:
        cuenta = get_object_or_404(PlanDeCuentas.objects.select_related('user'), pk=pk)
        return Response(serialize_plan_de_cuentas(cuenta), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener cuenta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('plan_de_cuentas', 'edit')])
def update_plan_de_cuentas(request, pk):
    """Actualizar una cuenta del PUC"""
    try:
        cuenta = get_object_or_404(PlanDeCuentas.objects, pk=pk)

        tipo = request.data.get('tipo')
        if tipo is not None:
            error = _validar_tipo(tipo)
            if error:
                return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
            cuenta.tipo = tipo
            # 'acumulado' se re-derivara en save() segun el nuevo tipo.

        codigo_puc = request.data.get('codigo_puc')
        if codigo_puc is not None:
            codigo_puc = str(codigo_puc).strip()
            error = _validar_codigo_puc(codigo_puc)
            if error:
                return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
            if PlanDeCuentas.objects.filter(codigo_puc=codigo_puc).exclude(pk=cuenta.pk).exists():
                return Response(
                    {"error": f"Ya existe otra cuenta con el Codigo PUC {codigo_puc}."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            cuenta.codigo_puc = codigo_puc

        nombre_cuenta = request.data.get('nombre_cuenta')
        if nombre_cuenta is not None:
            cuenta.nombre_cuenta = nombre_cuenta

        cuenta.save()

        return Response(serialize_plan_de_cuentas(cuenta), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('plan_de_cuentas', 'delete')])
def delete_plan_de_cuentas(request, pk):
    """Eliminar una cuenta del PUC (soft delete)"""
    try:
        cuenta = get_object_or_404(PlanDeCuentas.objects, pk=pk)
        cuenta.soft_delete()
        return Response(
            {"message": "Cuenta eliminada correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cuenta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('plan_de_cuentas', 'delete')])
def restore_plan_de_cuentas(request, pk):
    """Restaurar una cuenta del PUC eliminada"""
    try:
        cuenta = get_object_or_404(PlanDeCuentas.objects, pk=pk)
        if not cuenta.is_deleted:
            return Response(
                {"error": "La cuenta no esta eliminada"},
                status=status.HTTP_400_BAD_REQUEST
            )
        cuenta.restore()
        return Response(serialize_plan_de_cuentas(cuenta), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar cuenta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('plan_de_cuentas', 'delete')])
def hard_delete_plan_de_cuentas(request, pk):
    """Eliminar permanentemente una cuenta del PUC"""
    try:
        cuenta = get_object_or_404(PlanDeCuentas.objects, pk=pk)
        cuenta.delete()
        return Response(
            {"message": "Cuenta eliminada permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cuenta: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('plan_de_cuentas', 'view')])
def plan_de_cuentas_history(request, pk):
    """Obtener el historial de cambios de una cuenta del PUC"""
    try:
        cuenta = get_object_or_404(PlanDeCuentas.objects, pk=pk)
        history = cuenta.history.all()

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
                'tipo': h.tipo,
                'codigo_puc': h.codigo_puc,
                'nombre_cuenta': h.nombre_cuenta,
                'acumulado': h.acumulado,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
