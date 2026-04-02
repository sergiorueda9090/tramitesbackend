from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime
import urllib.request
import urllib.error
import json

from ..models import ExternalEndpoint
from .permissions import RolePermission, ModulePermission


# ================================================================
# HELPERS
# ================================================================

EXTERNAL_API_HOST = 'http://190.120.231.117:8080'


def serialize_endpoint(endpoint):
    """Convierte un objeto ExternalEndpoint a diccionario"""
    return {
        'id': endpoint.id,
        'nombre': endpoint.nombre,
        'codigo': endpoint.codigo,
        'url_base': endpoint.url_base,
        'metodo_http': endpoint.metodo_http,
        'descripcion': endpoint.descripcion,
        'activo': endpoint.activo,
        'timeout': endpoint.timeout,
        'created_at': endpoint.created_at,
        'updated_at': endpoint.updated_at,
        'deleted_at': endpoint.deleted_at,
    }


def proxy_get(url, timeout=30):
    """Realiza una petición GET al servicio externo y retorna la respuesta."""
    req = urllib.request.Request(url, method='GET')
    req.add_header('Accept', 'application/json')
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def proxy_post_image(url, imagen, timeout=60):
    """Envía una imagen al servicio externo vía multipart/form-data."""
    imagen_bytes = imagen.read()
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'

    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="imagen"; filename="{imagen.name}"\r\n'
        f'Content-Type: {imagen.content_type}\r\n\r\n'
    ).encode('utf-8') + imagen_bytes + f'\r\n--{boundary}--\r\n'.encode('utf-8')

    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    req.add_header('Accept', 'application/json')

    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def handle_external_error(e, servicio='servicio externo'):
    """Maneja errores de las peticiones a servicios externos."""
    if isinstance(e, urllib.error.HTTPError):
        body = e.read().decode('utf-8', errors='replace')
        return Response(
            {"error": f"Error del {servicio}: {e.code}", "detalle": body},
            status=e.code if 400 <= e.code < 600 else status.HTTP_502_BAD_GATEWAY
        )
    elif isinstance(e, urllib.error.URLError):
        return Response(
            {"error": f"No se pudo conectar al {servicio}: {str(e.reason)}"},
            status=status.HTTP_502_BAD_GATEWAY
        )
    else:
        return Response(
            {"error": f"Error inesperado al consultar {servicio}: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ================================================================
# CRUD — ExternalEndpoint
# ================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('api_app', 'create')])
def create_endpoint(request):
    """Crear un nuevo endpoint externo"""
    try:
        required_fields = ['nombre', 'codigo', 'url_base']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Validar código único
        codigo = request.data.get('codigo')
        if ExternalEndpoint.objects.filter(codigo=codigo, deleted_at__isnull=True).exists():
            return Response(
                {"error": f"Ya existe un endpoint con el código '{codigo}'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        endpoint = ExternalEndpoint.objects.create(
            nombre=request.data.get('nombre'),
            codigo=request.data.get('codigo'),
            url_base=request.data.get('url_base'),
            metodo_http=request.data.get('metodo_http', 'GET'),
            descripcion=request.data.get('descripcion', ''),
            activo=request.data.get('activo', True),
            timeout=request.data.get('timeout', 30),
        )

        return Response(serialize_endpoint(endpoint), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('api_app', 'view')])
def list_endpoints(request):
    """Listar endpoints externos con filtros y paginación"""
    try:
        endpoints = ExternalEndpoint.objects.all()

        search_query = request.query_params.get('search', None)
        if search_query:
            endpoints = endpoints.filter(
                Q(nombre__icontains=search_query) |
                Q(codigo__icontains=search_query) |
                Q(url_base__icontains=search_query) |
                Q(descripcion__icontains=search_query)
            )

        metodo = request.query_params.get('metodo_http', None)
        if metodo:
            endpoints = endpoints.filter(metodo_http=metodo)

        activo = request.query_params.get('activo', None)
        if activo is not None:
            endpoints = endpoints.filter(activo=activo == '1')

        start_date_str = request.query_params.get('start_date', None)
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                endpoints = endpoints.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de start_date debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        end_date_str = request.query_params.get('end_date', None)
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                endpoints = endpoints.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de end_date debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            endpoints = endpoints.filter(deleted_at__isnull=True)

        endpoints = endpoints.order_by('nombre')

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(endpoints, request)

        data = [serialize_endpoint(ep) for ep in paginated]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener endpoints: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('api_app', 'view')])
def get_endpoint(request, pk):
    """Obtener un endpoint por ID"""
    try:
        endpoint = get_object_or_404(ExternalEndpoint, pk=pk)
        return Response(serialize_endpoint(endpoint), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener endpoint: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('api_app', 'edit')])
def update_endpoint(request, pk):
    """Actualizar un endpoint externo"""
    try:
        endpoint = get_object_or_404(ExternalEndpoint, pk=pk)

        campos = ['nombre', 'codigo', 'url_base', 'metodo_http', 'descripcion', 'activo', 'timeout']
        for campo in campos:
            if campo in request.data:
                setattr(endpoint, campo, request.data.get(campo))

        endpoint.save()
        return Response(serialize_endpoint(endpoint), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('api_app', 'delete')])
def delete_endpoint(request, pk):
    """Eliminar un endpoint (soft delete)"""
    try:
        endpoint = get_object_or_404(ExternalEndpoint, pk=pk)
        endpoint.soft_delete()
        return Response(
            {"message": "Endpoint eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar endpoint: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('api_app', 'delete')])
def restore_endpoint(request, pk):
    """Restaurar un endpoint eliminado"""
    try:
        endpoint = get_object_or_404(ExternalEndpoint, pk=pk)
        if not endpoint.is_deleted:
            return Response(
                {"error": "El endpoint no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        endpoint.restore()
        return Response(serialize_endpoint(endpoint), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar endpoint: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('api_app', 'delete')])
def hard_delete_endpoint(request, pk):
    """Eliminar permanentemente un endpoint"""
    try:
        endpoint = get_object_or_404(ExternalEndpoint, pk=pk)
        endpoint.delete()
        return Response(
            {"message": "Endpoint eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar endpoint: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('api_app', 'view')])
def endpoint_history(request, pk):
    """Obtener el historial de cambios de un endpoint"""
    try:
        endpoint = get_object_or_404(ExternalEndpoint, pk=pk)
        history = endpoint.history.all()

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
                'nombre': h.nombre,
                'codigo': h.codigo,
                'url_base': h.url_base,
                'metodo_http': h.metodo_http,
                'activo': h.activo,
                'timeout': h.timeout,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ================================================================
# PROXY — Endpoints externos (APIs de terceros)
# ================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('api_app', 'view')])
def runt_vehiculo(request):
    """
    Consulta datos de un vehículo en el RUNT por placa y documento del propietario.
    Ejemplo: /api/runt_vehiculo/LUM228/C/8851343
    """
    placa = request.query_params.get('placa', None)
    tipo_documento = request.query_params.get('tipo_documento', 'C')
    numero_documento = request.query_params.get('numero_documento', None)

    if not placa and not numero_documento:
        return Response(
            {"error": "Se requiere al menos un parámetro: placa o numero_documento."},
            status=status.HTTP_400_BAD_REQUEST
        )

    url = f"{EXTERNAL_API_HOST}/api/runt_vehiculo/{placa or ''}/{tipo_documento}/{numero_documento or ''}"

    try:
        data = proxy_get(url)
        return Response(data, status=status.HTTP_200_OK)
    except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
        return handle_external_error(e, 'RUNT Vehículo')


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('api_app', 'view')])
def runt_vehiculo_vin(request):
    """
    Consulta datos de un vehículo en el RUNT usando el VIN (17 dígitos).
    Ejemplo: /api/runt_vehiculo_vin/9GNAL7EK4CS535206
    """
    vin = request.query_params.get('vin', None)

    if not vin:
        return Response(
            {"error": "Se requiere el parámetro 'vin'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    url = f"{EXTERNAL_API_HOST}/api/runt_vehiculo_vin/{vin}"

    try:
        data = proxy_get(url)
        return Response(data, status=status.HTTP_200_OK)
    except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
        return handle_external_error(e, 'RUNT VIN')


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('api_app', 'view')])
def tarjeta_propiedad(request):
    """
    Recibe imagen de tarjeta de propiedad y la envía al servicio de IA
    para extraer placa, tipo_documento y número de documento.
    """
    imagen = request.FILES.get('imagen')
    if not imagen:
        return Response(
            {"error": "El campo 'imagen' es requerido."},
            status=status.HTTP_400_BAD_REQUEST
        )

    url = f"{EXTERNAL_API_HOST}/api/tarjeta_propiedad"

    try:
        data = proxy_post_image(url, imagen, timeout=60)
        return Response(data, status=status.HTTP_200_OK)
    except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
        return handle_external_error(e, 'IA Tarjeta de Propiedad')


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('api_app', 'view')])
def vin_extractor(request):
    """
    Recibe imagen del VIN y la envía al servicio de IA para extraer el número VIN.
    """
    imagen = request.FILES.get('imagen')
    if not imagen:
        return Response(
            {"error": "El campo 'imagen' es requerido."},
            status=status.HTTP_400_BAD_REQUEST
        )

    url = f"{EXTERNAL_API_HOST}/api/vin"

    try:
        data = proxy_post_image(url, imagen, timeout=60)
        return Response(data, status=status.HTTP_200_OK)
    except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
        return handle_external_error(e, 'IA VIN')


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('api_app', 'view')])
def runt_persona(request):
    """
    Consulta datos de persona/conductor en RUNT por número de documento.
    """
    numero_documento = request.query_params.get('numero_documento', None)

    if not numero_documento:
        return Response(
            {"error": "Se requiere el parámetro 'numero_documento'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    url = f"{EXTERNAL_API_HOST}/api/runt/{numero_documento}"

    try:
        data = proxy_get(url)
        return Response(data, status=status.HTTP_200_OK)
    except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
        return handle_external_error(e, 'RUNT Persona')


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('api_app', 'view')])
def nombre_cliente(request):
    """
    Consulta nombre de persona por número de documento.
    Primero consulta RUNT; si no está inscrita, consulta API judicial como fallback.
    """
    numero_documento = request.query_params.get('numero_documento', None)

    if not numero_documento:
        return Response(
            {"error": "Se requiere el parámetro 'numero_documento'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Paso 1: Consultar RUNT
    url_runt = f"{EXTERNAL_API_HOST}/api/runt/{numero_documento}"

    try:
        data = proxy_get(url_runt)

        if not data.get('no_inscrito', False):
            data['fuente'] = 'runt'
            return Response(data, status=status.HTTP_200_OK)
    except (urllib.error.HTTPError, urllib.error.URLError, Exception):
        pass  # Fallback a judicial

    # Paso 2: Fallback API judicial
    url_judicial = f"{EXTERNAL_API_HOST}/api/judicial/cc/{numero_documento}"

    try:
        data = proxy_get(url_judicial)
        data['fuente'] = 'judicial'
        return Response(data, status=status.HTTP_200_OK)
    except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
        return handle_external_error(e, 'servicio de consulta de persona')


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('api_app', 'view')])
def previsora(request):
    """
    Consulta información de vehículo en Previsora/Falabella por placa.
    """
    placa = request.query_params.get('placa', None)

    if not placa:
        return Response(
            {"error": "Se requiere el parámetro 'placa'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    url = f"{EXTERNAL_API_HOST}/api/previsora/{placa}"

    try:
        data = proxy_get(url)
        return Response(data, status=status.HTTP_200_OK)
    except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
        return handle_external_error(e, 'Previsora/Falabella')
