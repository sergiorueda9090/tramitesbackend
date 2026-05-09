from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.core.validators import validate_ipv46_address
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from ..models import ComputadorIP
from .permissions import RolePermission, ModulePermission


def _parse_puerto(value):
    """Devuelve el puerto como int en [1, 65535], None si está vacío,
    o lanza ValueError con un mensaje claro si es inválido."""
    if value in (None, ''):
        return None
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError("El puerto debe ser un número entero.")
    if not (1 <= port <= 65535):
        raise ValueError("El puerto debe estar entre 1 y 65535.")
    return port


def serialize_computador_ip(ip):
    """Convierte un ComputadorIP a diccionario."""
    return {
        'id':          ip.id,
        'nombre':      ip.nombre,
        'ip':          ip.ip,
        'puerto':      ip.puerto,
        'protocolo':   ip.protocolo,
        'descripcion': ip.descripcion,
        'activo':      ip.activo,
        'url':         ip.url,
        'user':        ip.user_id,
        'user_name':   f"{ip.user.first_name} {ip.user.last_name}".strip() if ip.user else None,
        'created_at':  ip.created_at,
        'updated_at':  ip.updated_at,
        'deleted_at':  ip.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('computador_ips', 'create')])
def create_computador_ip(request):
    """Crear una nueva IP en el conmutador."""
    try:
        nombre = request.data.get('nombre')
        ip     = request.data.get('ip')

        if not nombre:
            return Response({"error": "El nombre es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if not ip:
            return Response({"error": "La IP es requerida."}, status=status.HTTP_400_BAD_REQUEST)

        # Validar formato IPv4/IPv6
        try:
            validate_ipv46_address(ip)
        except ValidationError:
            return Response({"error": f"La IP '{ip}' no tiene un formato válido."}, status=status.HTTP_400_BAD_REQUEST)

        # Validar puerto
        try:
            puerto = _parse_puerto(request.data.get('puerto'))
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        protocolo = request.data.get('protocolo', 'http')
        if protocolo not in ('http', 'https'):
            return Response({"error": "El protocolo debe ser 'http' o 'https'."}, status=status.HTTP_400_BAD_REQUEST)

        computador_ip = ComputadorIP.objects.create(
            nombre=nombre,
            ip=ip,
            puerto=puerto,
            protocolo=protocolo,
            descripcion=request.data.get('descripcion', ''),
            activo=bool(request.data.get('activo', False)),
            user=request.user if request.user.is_authenticated else None,
        )

        return Response(serialize_computador_ip(computador_ip), status=status.HTTP_201_CREATED)

    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('computador_ips', 'view')])
def list_computador_ips(request):
    """Listar IPs del conmutador con filtros y paginación."""
    try:
        ips = ComputadorIP.objects.select_related('user').all()

        search = request.query_params.get('search')
        if search:
            ips = ips.filter(
                Q(nombre__icontains=search) |
                Q(ip__icontains=search) |
                Q(descripcion__icontains=search)
            )

        protocolo = request.query_params.get('protocolo')
        if protocolo:
            ips = ips.filter(protocolo=protocolo)

        activo = request.query_params.get('activo')
        if activo is not None and activo != '':
            ips = ips.filter(activo=activo == '1')

        start_date_str = request.query_params.get('start_date')
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                ips = ips.filter(created_at__gte=start_date)
            except ValueError:
                return Response({"error": "El formato de start_date debe ser YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        end_date_str = request.query_params.get('end_date')
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                ips = ips.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response({"error": "El formato de end_date debe ser YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        include_deleted = request.query_params.get('include_deleted')
        if include_deleted != '1':
            ips = ips.filter(deleted_at__isnull=True)

        ips = ips.order_by('-created_at')

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(ips, request)

        data = [serialize_computador_ip(ip) for ip in paginated]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response({"error": f"Error al obtener IPs: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('computador_ips', 'view')])
def get_computador_ip(request, pk):
    """Obtener una IP por ID."""
    try:
        ip = get_object_or_404(ComputadorIP.objects.select_related('user'), pk=pk)
        return Response(serialize_computador_ip(ip), status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al obtener IP: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('computador_ips', 'edit')])
def update_computador_ip(request, pk):
    """Actualizar una IP del conmutador."""
    try:
        computador_ip = get_object_or_404(ComputadorIP.objects, pk=pk)

        if 'nombre' in request.data:
            computador_ip.nombre = request.data.get('nombre') or computador_ip.nombre

        if 'ip' in request.data:
            new_ip = request.data.get('ip')
            try:
                validate_ipv46_address(new_ip)
            except ValidationError:
                return Response({"error": f"La IP '{new_ip}' no tiene un formato válido."}, status=status.HTTP_400_BAD_REQUEST)
            computador_ip.ip = new_ip

        if 'puerto' in request.data:
            try:
                computador_ip.puerto = _parse_puerto(request.data.get('puerto'))
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if 'protocolo' in request.data:
            protocolo = request.data.get('protocolo')
            if protocolo not in ('http', 'https'):
                return Response({"error": "El protocolo debe ser 'http' o 'https'."}, status=status.HTTP_400_BAD_REQUEST)
            computador_ip.protocolo = protocolo

        if 'descripcion' in request.data:
            computador_ip.descripcion = request.data.get('descripcion') or ''

        if 'activo' in request.data:
            computador_ip.activo = bool(request.data.get('activo'))

        computador_ip.save()
        return Response(serialize_computador_ip(computador_ip), status=status.HTTP_200_OK)

    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('computador_ips', 'delete')])
def delete_computador_ip(request, pk):
    """Eliminar una IP (soft delete)."""
    try:
        computador_ip = get_object_or_404(ComputadorIP.objects, pk=pk)
        computador_ip.soft_delete()
        return Response({"message": "IP eliminada correctamente"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al eliminar IP: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('computador_ips', 'delete')])
def restore_computador_ip(request, pk):
    """Restaurar una IP eliminada."""
    try:
        computador_ip = get_object_or_404(ComputadorIP.objects, pk=pk)
        if not computador_ip.is_deleted:
            return Response({"error": "La IP no está eliminada"}, status=status.HTTP_400_BAD_REQUEST)
        computador_ip.restore()
        return Response(serialize_computador_ip(computador_ip), status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al restaurar IP: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('computador_ips', 'delete')])
def hard_delete_computador_ip(request, pk):
    """Eliminar permanentemente una IP."""
    try:
        computador_ip = get_object_or_404(ComputadorIP.objects, pk=pk)
        computador_ip.delete()
        return Response({"message": "IP eliminada permanentemente"}, status=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        return Response({"error": f"Error al eliminar IP: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('computador_ips', 'view')])
def computador_ip_history(request, pk):
    """Obtener el historial de cambios de una IP."""
    try:
        computador_ip = get_object_or_404(ComputadorIP.objects, pk=pk)
        history = computador_ip.history.all()

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
                'history_id':           h.history_id,
                'history_date':         h.history_date,
                'history_type':         h.history_type,
                'history_type_display': h.get_history_type_display(),
                'history_user': {
                    'id': h.history_user.id,
                    'username': h.history_user.username,
                    'name': f"{h.history_user.first_name} {h.history_user.last_name}".strip()
                } if h.history_user else None,
                'nombre':      h.nombre,
                'ip':          h.ip,
                'puerto':      h.puerto,
                'protocolo':   h.protocolo,
                'descripcion': h.descripcion,
                'activo':      h.activo,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response({"error": f"Error al obtener historial: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
