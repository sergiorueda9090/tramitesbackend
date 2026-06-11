from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError, transaction
from django.db.models import Q
from datetime import datetime
import re

from ..models import CorreoAleatorio
from .permissions import RolePermission, ModulePermission

# Módulo de permisos propio (registrado en users/migrations/0018).
MODULO = 'correos_aleatorios'

# Campos por los que se permite ordenar el listado (vía ?ordering=campo / -campo).
ORDERING_PERMITIDO = {
    'id', 'correo', 'descripcion', 'activo', 'veces_usado',
    'ultimo_uso', 'created_at', 'updated_at',
}

# Validación básica de formato de correo (suficiente para la carga del pool).
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# ==================== HELPERS ====================

def serialize_correo(correo):
    """Convierte un objeto CorreoAleatorio a diccionario."""
    return {
        'id': correo.id,
        'correo': correo.correo,
        'descripcion': correo.descripcion,
        'activo': correo.activo,
        'veces_usado': correo.veces_usado,
        'ultimo_uso': correo.ultimo_uso,
        'usuario': {
            'id': correo.usuario.id,
            'name': f"{correo.usuario.first_name} {correo.usuario.last_name}".strip(),
        } if correo.usuario else None,
        'created_at': correo.created_at,
        'updated_at': correo.updated_at,
        'deleted_at': correo.deleted_at,
    }


# ==================== CRUD DEL POOL ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission(MODULO, 'create')])
def create_correo(request):
    """Agregar un correo al pool."""
    try:
        correo = request.data.get('correo')
        if not correo:
            return Response({"error": "El campo correo es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        if CorreoAleatorio.objects.filter(correo=correo, deleted_at__isnull=True).exists():
            return Response({"error": "Ese correo ya está registrado."}, status=status.HTTP_400_BAD_REQUEST)

        obj = CorreoAleatorio.objects.create(
            usuario=request.user,
            correo=correo,
            descripcion=request.data.get('descripcion', ''),
            activo=bool(request.data.get('activo', True)),
        )
        return Response(serialize_correo(obj), status=status.HTTP_201_CREATED)
    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission(MODULO, 'view')])
def list_correos(request):
    """Listar correos del pool con filtros y paginación."""
    try:
        correos = CorreoAleatorio.objects.select_related('usuario').all()

        search_query = request.query_params.get('search', None)
        if search_query:
            correos = correos.filter(
                Q(correo__icontains=search_query) | Q(descripcion__icontains=search_query)
            )

        activo = request.query_params.get('activo', None)
        if activo in ('0', '1', 'true', 'false'):
            correos = correos.filter(activo=activo in ('1', 'true'))

        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            correos = correos.filter(deleted_at__isnull=True)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                correos = correos.filter(created_at__date__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        end_date_str = request.query_params.get('end_date', None)
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                correos = correos.filter(created_at__date__lte=end_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Ordenamiento (whitelist); por defecto, más recientes primero
        ordering = request.query_params.get('ordering', None)
        if ordering and ordering.lstrip('-') in ORDERING_PERMITIDO:
            correos = correos.order_by(ordering)
        else:
            correos = correos.order_by('-created_at')

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(correos, request)

        data = [serialize_correo(c) for c in paginated]
        return paginator.get_paginated_response(data)
    except Exception as e:
        return Response({"error": f"Error al obtener correos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission(MODULO, 'view')])
def get_correo(request, pk):
    """Obtener un correo por ID."""
    try:
        correo = get_object_or_404(CorreoAleatorio.objects.select_related('usuario'), pk=pk)
        return Response(serialize_correo(correo), status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al obtener correo: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission(MODULO, 'edit')])
def update_correo(request, pk):
    """Actualizar un correo del pool."""
    try:
        correo = get_object_or_404(CorreoAleatorio.objects, pk=pk)
        correo.correo = request.data.get('correo', correo.correo)
        correo.descripcion = request.data.get('descripcion', correo.descripcion)
        if 'activo' in request.data:
            correo.activo = bool(request.data.get('activo'))
        correo.save()
        return Response(serialize_correo(correo), status=status.HTTP_200_OK)
    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission(MODULO, 'delete')])
def delete_correo(request, pk):
    """Eliminar un correo (soft delete)."""
    try:
        correo = get_object_or_404(CorreoAleatorio.objects, pk=pk)
        correo.soft_delete()
        return Response({"message": "Correo eliminado correctamente"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al eliminar correo: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission(MODULO, 'delete')])
def restore_correo(request, pk):
    """Restaurar un correo eliminado."""
    try:
        correo = get_object_or_404(CorreoAleatorio.objects, pk=pk)
        if not correo.is_deleted:
            return Response({"error": "El correo no está eliminado"}, status=status.HTTP_400_BAD_REQUEST)
        correo.restore()
        return Response(serialize_correo(correo), status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Error al restaurar correo: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission(MODULO, 'delete')])
def hard_delete_correo(request, pk):
    """Eliminar permanentemente un correo."""
    try:
        correo = get_object_or_404(CorreoAleatorio.objects, pk=pk)
        correo.delete()
        return Response({"message": "Correo eliminado permanentemente"}, status=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        return Response({"error": f"Error al eliminar correo: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission(MODULO, 'view')])
def correo_history(request, pk):
    """Historial de cambios de un correo."""
    try:
        correo = get_object_or_404(CorreoAleatorio.objects, pk=pk)
        history = correo.history.all()

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(history, request)

        data = []
        for h in paginated:
            data.append({
                'history_id': h.history_id,
                'history_date': h.history_date,
                'history_type': h.history_type,
                'history_type_display': h.get_history_type_display(),
                'history_user': {
                    'id': h.history_user.id,
                    'name': f"{h.history_user.first_name} {h.history_user.last_name}".strip()
                } if h.history_user else None,
                'correo': h.correo,
                'activo': h.activo,
            })

        return paginator.get_paginated_response(data)
    except Exception as e:
        return Response({"error": f"Error al obtener historial: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission(MODULO, 'create')])
def bulk_create_correos(request):
    """
    Carga masiva de correos al pool desde Excel (el frontend parsea el .xlsx y
    envía las filas como JSON).
    Body: { "registros": [ { "correo": "a@b.com", "descripcion": "", "activo": true }, ... ] }

    Validación todo-o-nada: si alguna fila tiene error (correo vacío, formato
    inválido, duplicado en el archivo o ya existente en el pool) no se crea
    ninguna y se devuelven los errores por fila para corregir el Excel.
    """
    try:
        registros = request.data.get('registros', [])
        if not isinstance(registros, list) or len(registros) == 0:
            return Response(
                {"error": "Debe enviar una lista de registros en el campo 'registros'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Correos ya existentes en el pool (activos o no), en minúsculas.
        existentes = set(
            CorreoAleatorio.objects
            .filter(deleted_at__isnull=True)
            .values_list('correo', flat=True)
        )
        existentes = {str(c).strip().lower() for c in existentes}

        errores = []
        registros_validos = []
        vistos_en_archivo = set()

        def _parse_activo(valor):
            if isinstance(valor, bool):
                return valor
            if valor is None or valor == '':
                return True
            return str(valor).strip().lower() in ('1', 'true', 'si', 'sí', 'activo', 'x', 'yes', 'verdadero')

        for index, registro in enumerate(registros):
            fila = index + 2  # +2 porque la fila 1 es el header del Excel
            mensajes = []

            correo = str(registro.get('correo', '')).strip().lower()
            if not correo:
                mensajes.append('Correo está vacío')
            elif not EMAIL_RE.match(correo):
                mensajes.append('Correo no tiene un formato válido')
            elif correo in vistos_en_archivo:
                mensajes.append('Correo duplicado dentro del archivo')
            elif correo in existentes:
                mensajes.append('Correo ya está registrado en el pool')

            descripcion = str(registro.get('descripcion', '')).strip()
            activo = _parse_activo(registro.get('activo', True))

            if mensajes:
                errores.append({
                    'fila': fila,
                    'correo': registro.get('correo', ''),
                    'mensajes': mensajes,
                })
            else:
                vistos_en_archivo.add(correo)
                registros_validos.append({'correo': correo, 'descripcion': descripcion, 'activo': activo})

        if errores:
            return Response(
                {"errores": errores, "total_errores": len(errores)},
                status=status.HTTP_400_BAD_REQUEST
            )

        creados = []
        with transaction.atomic():
            for datos in registros_validos:
                obj = CorreoAleatorio.objects.create(
                    usuario=request.user,
                    correo=datos['correo'],
                    descripcion=datos['descripcion'],
                    activo=datos['activo'],
                )
                creados.append(serialize_correo(obj))

        return Response(
            {"message": f"Se cargaron {len(creados)} correo(s) correctamente.", "total_creados": len(creados)},
            status=status.HTTP_201_CREATED
        )

    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
