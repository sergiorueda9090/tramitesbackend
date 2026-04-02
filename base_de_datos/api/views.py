from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from ..models import RegistroVehiculo
from clientes.models import Cliente
from .permissions import RolePermission, ModulePermission


def serialize_registro(registro):
    """Convierte un objeto RegistroVehiculo a diccionario"""
    return {
        'id': registro.id,
        'usuario': {
            'id': registro.usuario.id,
            'name': f"{registro.usuario.first_name} {registro.usuario.last_name}".strip(),
        } if registro.usuario else None,
        'cliente': {
            'id': registro.cliente.id,
            'nombre': registro.cliente.nombre,
        } if registro.cliente else None,
        # Trámite
        'tipo_tramite': registro.tipo_tramite,
        'tipo_vehiculo': registro.tipo_vehiculo,
        # Titular
        'es_propietario': registro.es_propietario,
        'tipo_documento': registro.tipo_documento,
        'numero_documento': registro.numero_documento,
        'nombre_completo': registro.nombre_completo,
        'telefono': registro.telefono,
        # Vehículo
        'placa': registro.placa,
        'clase': registro.clase,
        'clasificacion': registro.clasificacion,
        'tipo_servicio': registro.tipo_servicio,
        'tipo_carroceria': registro.tipo_carroceria,
        'vin': registro.vin,
        'num_motor': registro.num_motor,
        'num_chasis': registro.num_chasis,
        'marca': registro.marca,
        'linea': registro.linea,
        'modelo': registro.modelo,
        'cilindraje': registro.cilindraje,
        'color': registro.color,
        'organismo_transito': registro.organismo_transito,
        # Timestamps
        'created_at': registro.created_at,
        'updated_at': registro.updated_at,
        'deleted_at': registro.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('base_de_datos', 'create')])
def create_registro(request):
    """Crear un nuevo registro de vehículo"""
    try:
        required_fields = ['cliente', 'numero_documento', 'nombre_completo']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Validar que el cliente exista
        cliente_id = request.data.get('cliente')
        try:
            cliente = Cliente.objects.get(pk=cliente_id)
            if cliente.deleted_at is not None:
                return Response(
                    {"error": "El cliente especificado está eliminado."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Cliente.DoesNotExist:
            return Response(
                {"error": "El cliente especificado no existe."},
                status=status.HTTP_404_NOT_FOUND
            )

        registro = RegistroVehiculo.objects.create(
            usuario=request.user,
            cliente=cliente,
            # Trámite
            tipo_tramite=request.data.get('tipo_tramite', 'SOAT'),
            tipo_vehiculo=request.data.get('tipo_vehiculo', 'USADO'),
            # Titular
            es_propietario=request.data.get('es_propietario', True),
            tipo_documento=request.data.get('tipo_documento', 'C'),
            numero_documento=request.data.get('numero_documento'),
            nombre_completo=request.data.get('nombre_completo'),
            telefono=request.data.get('telefono', ''),
            # Vehículo
            placa=request.data.get('placa', ''),
            clase=request.data.get('clase', ''),
            clasificacion=request.data.get('clasificacion', ''),
            tipo_servicio=request.data.get('tipo_servicio', ''),
            tipo_carroceria=request.data.get('tipo_carroceria', ''),
            vin=request.data.get('vin', ''),
            num_motor=request.data.get('num_motor', ''),
            num_chasis=request.data.get('num_chasis', ''),
            marca=request.data.get('marca', ''),
            linea=request.data.get('linea', ''),
            modelo=request.data.get('modelo', ''),
            cilindraje=request.data.get('cilindraje', ''),
            color=request.data.get('color', ''),
            organismo_transito=request.data.get('organismo_transito', ''),
        )

        return Response(serialize_registro(registro), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('base_de_datos', 'view')])
def list_registros(request):
    """Listar registros de vehículos con filtros y paginación"""
    try:
        registros = RegistroVehiculo.objects.select_related(
            'usuario', 'cliente'
        ).all()

        # Filtro de búsqueda general
        search_query = request.query_params.get('search', None)
        if search_query:
            registros = registros.filter(
                Q(placa__icontains=search_query) |
                Q(nombre_completo__icontains=search_query) |
                Q(numero_documento__icontains=search_query) |
                Q(marca__icontains=search_query) |
                Q(linea__icontains=search_query) |
                Q(vin__icontains=search_query) |
                Q(num_chasis__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            registros = registros.filter(cliente_id=cliente_id)

        # Filtro por tipo de trámite
        tipo_tramite = request.query_params.get('tipo_tramite', None)
        if tipo_tramite:
            registros = registros.filter(tipo_tramite=tipo_tramite)

        # Filtro por tipo de vehículo
        tipo_vehiculo = request.query_params.get('tipo_vehiculo', None)
        if tipo_vehiculo:
            registros = registros.filter(tipo_vehiculo=tipo_vehiculo)

        # Filtro por tipo de documento
        tipo_documento = request.query_params.get('tipo_documento', None)
        if tipo_documento:
            registros = registros.filter(tipo_documento=tipo_documento)

        # Filtro por es_propietario
        es_propietario = request.query_params.get('es_propietario', None)
        if es_propietario is not None:
            registros = registros.filter(es_propietario=es_propietario == '1')

        # Filtro por usuario
        usuario_id = request.query_params.get('usuario', None)
        if usuario_id:
            registros = registros.filter(usuario_id=usuario_id)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                registros = registros.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de start_date debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                registros = registros.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de end_date debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            registros = registros.filter(deleted_at__isnull=True)

        # Ordenar
        registros = registros.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_registros = paginator.paginate_queryset(registros, request)

        data = [serialize_registro(r) for r in paginated_registros]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener registros: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('base_de_datos', 'view')])
def get_registro(request, pk):
    """Obtener un registro de vehículo por ID"""
    try:
        registro = get_object_or_404(
            RegistroVehiculo.objects.select_related('usuario', 'cliente'),
            pk=pk
        )
        return Response(serialize_registro(registro), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener registro: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('base_de_datos', 'edit')])
def update_registro(request, pk):
    """Actualizar un registro de vehículo"""
    try:
        registro = get_object_or_404(RegistroVehiculo, pk=pk)

        # Validar cliente si se proporciona
        if 'cliente' in request.data:
            cliente_id = request.data.get('cliente')
            try:
                cliente = Cliente.objects.get(pk=cliente_id)
                if cliente.deleted_at is not None:
                    return Response(
                        {"error": "El cliente especificado está eliminado."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                registro.cliente = cliente
            except Cliente.DoesNotExist:
                return Response(
                    {"error": "El cliente especificado no existe."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Campos actualizables
        campos = [
            'tipo_tramite', 'tipo_vehiculo', 'es_propietario',
            'tipo_documento', 'numero_documento', 'nombre_completo', 'telefono',
            'placa', 'clase', 'clasificacion', 'tipo_servicio', 'tipo_carroceria',
            'vin', 'num_motor', 'num_chasis', 'marca', 'linea', 'modelo',
            'cilindraje', 'color', 'organismo_transito',
        ]

        for campo in campos:
            if campo in request.data:
                setattr(registro, campo, request.data.get(campo))

        registro.save()

        return Response(serialize_registro(registro), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('base_de_datos', 'delete')])
def delete_registro(request, pk):
    """Eliminar un registro de vehículo (soft delete)"""
    try:
        registro = get_object_or_404(RegistroVehiculo, pk=pk)
        registro.soft_delete()
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('base_de_datos', 'delete')])
def restore_registro(request, pk):
    """Restaurar un registro de vehículo eliminado"""
    try:
        registro = get_object_or_404(RegistroVehiculo, pk=pk)
        if not registro.is_deleted:
            return Response(
                {"error": "El registro no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        registro.restore()
        return Response(serialize_registro(registro), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar registro: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('base_de_datos', 'delete')])
def hard_delete_registro(request, pk):
    """Eliminar permanentemente un registro de vehículo"""
    try:
        registro = get_object_or_404(RegistroVehiculo, pk=pk)
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('base_de_datos', 'view')])
def registro_history(request, pk):
    """Obtener el historial de cambios de un registro de vehículo"""
    try:
        registro = get_object_or_404(RegistroVehiculo, pk=pk)
        history = registro.history.all()

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
                'tipo_tramite': h.tipo_tramite,
                'tipo_vehiculo': h.tipo_vehiculo,
                'es_propietario': h.es_propietario,
                'tipo_documento': h.tipo_documento,
                'numero_documento': h.numero_documento,
                'nombre_completo': h.nombre_completo,
                'telefono': h.telefono,
                'placa': h.placa,
                'clase': h.clase,
                'clasificacion': h.clasificacion,
                'tipo_servicio': h.tipo_servicio,
                'tipo_carroceria': h.tipo_carroceria,
                'vin': h.vin,
                'num_motor': h.num_motor,
                'num_chasis': h.num_chasis,
                'marca': h.marca,
                'linea': h.linea,
                'modelo': h.modelo,
                'cilindraje': h.cilindraje,
                'color': h.color,
                'organismo_transito': h.organismo_transito,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
