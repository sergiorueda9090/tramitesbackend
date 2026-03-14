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

from ..models import Cotizador, CotizadorPagos
from .permissions import RolePermission, ModulePermission


def serialize_cotizador(cotizador):
    """Convierte un objeto Cotizador a diccionario"""
    return {
        'id': cotizador.id,
        'usuario': {
            'id': cotizador.usuario.id,
            'name': f"{cotizador.usuario.first_name} {cotizador.usuario.last_name}".strip(),
        } if cotizador.usuario else None,
        'cliente': {
            'id': cotizador.cliente.id,
            'nombre': cotizador.cliente.nombre,
        } if cotizador.cliente else None,
        'etiqueta': {
            'id': cotizador.etiqueta.id,
            'nombre': cotizador.etiqueta.nombre,
            'color': cotizador.etiqueta.color,
        } if cotizador.etiqueta else None,
        'precio_cliente': {
            'id': cotizador.precio_cliente.id,
        } if cotizador.precio_cliente else None,
        'descripcion': cotizador.descripcion,
        'precio_lay': str(cotizador.precio_lay),
        'comision': str(cotizador.comision),
        'placa': cotizador.placa,
        'clindraje': cotizador.clindraje,
        'modelo': cotizador.modelo,
        'chasis': cotizador.chasis,
        'tipo_documento': cotizador.tipo_documento,
        'tipo_documento_display': cotizador.get_tipo_documento_display(),
        'numero_documento': cotizador.numero_documento,
        'nombre_completo': cotizador.nombre_completo,
        'telefono': cotizador.telefono,
        'correo': cotizador.correo,
        'direccion': cotizador.direccion,
        'cotizador_estado': cotizador.cotizador_estado,
        'tramite_estado': cotizador.tramite_estado,
        'confirmacion_estado': cotizador.confirmacion_estado,
        'cargar_pdf_estado': cotizador.cargar_pdf_estado,
        'created_at': cotizador.created_at,
        'updated_at': cotizador.updated_at,
        'deleted_at': cotizador.deleted_at,
    }


def serialize_pago(pago):
    """Convierte un objeto CotizadorPagos a diccionario"""
    return {
        'id': pago.id,
        'cotizador_id': pago.cotizador_id,
        'precio_lay': str(pago.precio_lay),
        'comision': str(pago.comision),
        'fecha_pago': pago.fecha_pago,
        'created_at': pago.created_at,
        'updated_at': pago.updated_at,
        'deleted_at': pago.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('cotizador', 'create')])
def create_cotizador(request):
    """Crear un nuevo cotizador"""
    try:
        required_fields = ['cliente', 'etiqueta', 'precio_cliente', 'descripcion',
                          'precio_lay', 'comision', 'placa', 'clindraje', 'modelo',
                          'chasis', 'numero_documento', 'nombre_completo', 'telefono',
                          'correo', 'direccion']

        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        cotizador = Cotizador.objects.create(
            usuario=request.user,
            cliente_id=request.data.get('cliente'),
            etiqueta_id=request.data.get('etiqueta'),
            precio_cliente_id=request.data.get('precio_cliente'),
            descripcion=request.data.get('descripcion'),
            precio_lay=request.data.get('precio_lay'),
            comision=request.data.get('comision'),
            placa=request.data.get('placa'),
            clindraje=request.data.get('clindraje'),
            modelo=request.data.get('modelo'),
            chasis=request.data.get('chasis'),
            tipo_documento=request.data.get('tipo_documento', 'CC'),
            numero_documento=request.data.get('numero_documento'),
            nombre_completo=request.data.get('nombre_completo'),
            telefono=request.data.get('telefono'),
            correo=request.data.get('correo'),
            direccion=request.data.get('direccion'),
        )

        return Response(serialize_cotizador(cotizador), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('cotizador', 'view')])
def list_cotizadores(request):
    """Listar cotizadores con filtros y paginación"""
    try:
        cotizadores = Cotizador.objects.select_related(
            'usuario', 'cliente', 'etiqueta', 'precio_cliente'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            cotizadores = cotizadores.filter(
                Q(placa__icontains=search_query) |
                Q(nombre_completo__icontains=search_query) |
                Q(numero_documento__icontains=search_query) |
                Q(chasis__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            cotizadores = cotizadores.filter(cliente_id=cliente_id)

        # Filtro por etiqueta
        etiqueta_id = request.query_params.get('etiqueta', None)
        if etiqueta_id:
            cotizadores = cotizadores.filter(etiqueta_id=etiqueta_id)

        # Filtro por estados
        cotizador_estado = request.query_params.get('cotizador_estado', None)
        if cotizador_estado:
            cotizadores = cotizadores.filter(cotizador_estado=cotizador_estado)

        tramite_estado = request.query_params.get('tramite_estado', None)
        if tramite_estado:
            cotizadores = cotizadores.filter(tramite_estado=tramite_estado)

        confirmacion_estado = request.query_params.get('confirmacion_estado', None)
        if confirmacion_estado:
            cotizadores = cotizadores.filter(confirmacion_estado=confirmacion_estado)

        cargar_pdf_estado = request.query_params.get('cargar_pdf_estado', None)
        if cargar_pdf_estado:
            cotizadores = cotizadores.filter(cargar_pdf_estado=cargar_pdf_estado)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                cotizadores = cotizadores.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                cotizadores = cotizadores.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            cotizadores = cotizadores.filter(deleted_at__isnull=True)

        # Ordenar
        cotizadores = cotizadores.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_cotizadores = paginator.paginate_queryset(cotizadores, request)

        data = [serialize_cotizador(c) for c in paginated_cotizadores]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener cotizadores: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('cotizador', 'view')])
def get_cotizador(request, pk):
    """Obtener un cotizador por ID"""
    try:
        cotizador = get_object_or_404(
            Cotizador.objects.select_related('usuario', 'cliente', 'etiqueta', 'precio_cliente'),
            pk=pk
        )
        return Response(serialize_cotizador(cotizador), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener cotizador: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('cotizador', 'edit')])
def update_cotizador(request, pk):
    """Actualizar un cotizador"""
    try:
        cotizador = get_object_or_404(Cotizador.objects, pk=pk)

        # Actualizar campos FK si se proporcionan
        if 'cliente' in request.data:
            cotizador.cliente_id = request.data.get('cliente')
        if 'etiqueta' in request.data:
            cotizador.etiqueta_id = request.data.get('etiqueta')
        if 'precio_cliente' in request.data:
            cotizador.precio_cliente_id = request.data.get('precio_cliente')

        # Actualizar campos de texto
        cotizador.descripcion = request.data.get('descripcion', cotizador.descripcion)
        cotizador.precio_lay = request.data.get('precio_lay', cotizador.precio_lay)
        cotizador.comision = request.data.get('comision', cotizador.comision)
        cotizador.placa = request.data.get('placa', cotizador.placa)
        cotizador.clindraje = request.data.get('clindraje', cotizador.clindraje)
        cotizador.modelo = request.data.get('modelo', cotizador.modelo)
        cotizador.chasis = request.data.get('chasis', cotizador.chasis)
        cotizador.tipo_documento = request.data.get('tipo_documento', cotizador.tipo_documento)
        cotizador.numero_documento = request.data.get('numero_documento', cotizador.numero_documento)
        cotizador.nombre_completo = request.data.get('nombre_completo', cotizador.nombre_completo)
        cotizador.telefono = request.data.get('telefono', cotizador.telefono)
        cotizador.correo = request.data.get('correo', cotizador.correo)
        cotizador.direccion = request.data.get('direccion', cotizador.direccion)

        # Actualizar estados
        cotizador.cotizador_estado = request.data.get('cotizador_estado', cotizador.cotizador_estado)
        cotizador.tramite_estado = request.data.get('tramite_estado', cotizador.tramite_estado)
        cotizador.confirmacion_estado = request.data.get('confirmacion_estado', cotizador.confirmacion_estado)
        cotizador.cargar_pdf_estado = request.data.get('cargar_pdf_estado', cotizador.cargar_pdf_estado)

        cotizador.save()

        return Response(serialize_cotizador(cotizador), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cotizador', 'delete')])
def delete_cotizador(request, pk):
    """Eliminar un cotizador (soft delete)"""
    try:
        cotizador = get_object_or_404(Cotizador.objects, pk=pk)
        cotizador.soft_delete()
        return Response(
            {"message": "Cotizador eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cotizador: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cotizador', 'delete')])
def restore_cotizador(request, pk):
    """Restaurar un cotizador eliminado"""
    try:
        cotizador = get_object_or_404(Cotizador.objects, pk=pk)
        if not cotizador.is_deleted:
            return Response(
                {"error": "El cotizador no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        cotizador.restore()
        return Response(serialize_cotizador(cotizador), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar cotizador: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cotizador', 'delete')])
def hard_delete_cotizador(request, pk):
    """Eliminar permanentemente un cotizador"""
    try:
        cotizador = get_object_or_404(Cotizador.objects, pk=pk)
        cotizador.delete()
        return Response(
            {"message": "Cotizador eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cotizador: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cotizador', 'view')])
def cotizador_history(request, pk):
    """Obtener el historial de cambios de un cotizador"""
    try:
        cotizador = get_object_or_404(Cotizador.objects, pk=pk)
        history = cotizador.history.all()

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
                'placa': h.placa,
                'nombre_completo': h.nombre_completo,
                'cotizador_estado': h.cotizador_estado,
                'tramite_estado': h.tramite_estado,
                'confirmacion_estado': h.confirmacion_estado,
                'cargar_pdf_estado': h.cargar_pdf_estado,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== TRANSICIONES DE ESTADO ====================

ESTADO_TRANSICIONES = {
    'tramite': {
        'desde': 'cotizador_estado',
        'hacia': 'tramite_estado',
        'nombre': 'Trámite'
    },
    'confirmacion': {
        'desde': 'tramite_estado',
        'hacia': 'confirmacion_estado',
        'nombre': 'Confirmación'
    },
    'cargaro': {
        'desde': 'confirmacion_estado',
        'hacia': 'cargar_pdf_estado',
        'nombre': 'Cargaro'
    },
}


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('cotizador', 'edit')])
def cambiar_estado(request, pk):
    """
    Cambiar el estado del cotizador al siguiente paso.

    Body: { "paso": "tramite" | "confirmacion" | "cargaro" }

    Flujo:
    - cotizador(1) → tramite: cotizador_estado=0, tramite_estado=1
    - tramite(1) → confirmacion: tramite_estado=0, confirmacion_estado=1
    - confirmacion(1) → cargaro: confirmacion_estado=0, cargar_pdf_estado=1
    """
    try:
        cotizador = get_object_or_404(Cotizador.objects, pk=pk)
        paso = request.data.get('paso')

        if not paso:
            return Response(
                {"error": "El campo 'paso' es requerido. Opciones: tramite, confirmacion, cargaro"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if paso not in ESTADO_TRANSICIONES:
            return Response(
                {"error": f"Paso inválido: {paso}. Opciones: tramite, confirmacion, cargaro"},
                status=status.HTTP_400_BAD_REQUEST
            )

        transicion = ESTADO_TRANSICIONES[paso]
        campo_desde = transicion['desde']
        campo_hacia = transicion['hacia']

        # Verificar que el estado actual permita la transición
        if getattr(cotizador, campo_desde) != '1':
            return Response(
                {"error": f"No se puede avanzar a {transicion['nombre']}. El estado anterior no está activo."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar que no se haya pasado ya a este estado
        if getattr(cotizador, campo_hacia) == '1':
            return Response(
                {"error": f"El cotizador ya está en estado {transicion['nombre']}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Realizar la transición
        setattr(cotizador, campo_desde, '0')
        setattr(cotizador, campo_hacia, '1')
        cotizador.save()

        return Response({
            "message": f"Estado actualizado a {transicion['nombre']} correctamente",
            "cotizador": serialize_cotizador(cotizador)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al cambiar estado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cotizador', 'edit')])
def revertir_estado(request, pk):
    """
    Revertir el estado del cotizador al paso anterior.

    Body: { "paso": "cotizador" | "tramite" | "confirmacion" }

    Flujo inverso:
    - tramite(1) → cotizador: tramite_estado=0, cotizador_estado=1
    - confirmacion(1) → tramite: confirmacion_estado=0, tramite_estado=1
    - cargaro(1) → confirmacion: cargar_pdf_estado=0, confirmacion_estado=1
    """
    try:
        cotizador = get_object_or_404(Cotizador.objects, pk=pk)
        paso = request.data.get('paso')

        REVERTIR_TRANSICIONES = {
            'cotizador': {
                'desde': 'tramite_estado',
                'hacia': 'cotizador_estado',
                'nombre': 'Cotizador'
            },
            'tramite': {
                'desde': 'confirmacion_estado',
                'hacia': 'tramite_estado',
                'nombre': 'Trámite'
            },
            'confirmacion': {
                'desde': 'cargar_pdf_estado',
                'hacia': 'confirmacion_estado',
                'nombre': 'Confirmación'
            },
        }

        if not paso:
            return Response(
                {"error": "El campo 'paso' es requerido. Opciones: cotizador, tramite, confirmacion"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if paso not in REVERTIR_TRANSICIONES:
            return Response(
                {"error": f"Paso inválido: {paso}. Opciones: cotizador, tramite, confirmacion"},
                status=status.HTTP_400_BAD_REQUEST
            )

        transicion = REVERTIR_TRANSICIONES[paso]
        campo_desde = transicion['desde']
        campo_hacia = transicion['hacia']

        # Verificar que el estado actual permita la reversión
        if getattr(cotizador, campo_desde) != '1':
            return Response(
                {"error": f"No se puede revertir a {transicion['nombre']}. El estado actual no lo permite."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Realizar la reversión
        setattr(cotizador, campo_desde, '0')
        setattr(cotizador, campo_hacia, '1')
        cotizador.save()

        return Response({
            "message": f"Estado revertido a {transicion['nombre']} correctamente",
            "cotizador": serialize_cotizador(cotizador)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al revertir estado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== PAGOS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cotizador', 'create')])
def create_pago(request, cotizador_pk):
    """Crear un nuevo pago para un cotizador"""
    try:
        cotizador = get_object_or_404(Cotizador.objects, pk=cotizador_pk)

        required_fields = ['precio_lay', 'comision', 'fecha_pago']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        pago = CotizadorPagos.objects.create(
            cotizador=cotizador,
            precio_lay=request.data.get('precio_lay'),
            comision=request.data.get('comision'),
            fecha_pago=request.data.get('fecha_pago'),
        )

        return Response(serialize_pago(pago), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('cotizador', 'view')])
def list_pagos(request, cotizador_pk):
    """Listar pagos de un cotizador"""
    try:
        cotizador = get_object_or_404(Cotizador.objects, pk=cotizador_pk)
        pagos = CotizadorPagos.objects.filter(cotizador=cotizador, deleted_at__isnull=True)

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_pagos = paginator.paginate_queryset(pagos, request)

        data = [serialize_pago(p) for p in paginated_pagos]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener pagos: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('cotizador', 'edit')])
def update_pago(request, pk):
    """Actualizar un pago"""
    try:
        pago = get_object_or_404(CotizadorPagos.objects, pk=pk)

        pago.precio_lay = request.data.get('precio_lay', pago.precio_lay)
        pago.comision = request.data.get('comision', pago.comision)
        pago.fecha_pago = request.data.get('fecha_pago', pago.fecha_pago)

        pago.save()

        return Response(serialize_pago(pago), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cotizador', 'delete')])
def delete_pago(request, pk):
    """Eliminar un pago (soft delete)"""
    try:
        pago = get_object_or_404(CotizadorPagos.objects, pk=pk)
        from django.utils import timezone
        pago.deleted_at = timezone.now()
        pago.save()
        return Response(
            {"message": "Pago eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar pago: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



"""
APIS EXTERNAS PARA INTEGRACIÓN CON SISTEMAS DE TERCEROS (SIN AUTENTICACIÓN)
Estas APIs permiten a sistemas externos consultar información de cotizadores sin necesidad de autenticación.
"""
@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cotizador', 'view')])
def external_placa_documento_runt(request):
    
    placa            = request.query_params.get('placa', None)
    numero_documento = request.query_params.get('numero_documento', None)
    tipo_documento   = request.query_params.get('tipo_documento', 'C')

    if not placa and not numero_documento and not tipo_documento:
        return Response(
            {"error": "Se requiere al menos un parámetro: placa o numero_documento con tipo_documento."},
            status=status.HTTP_400_BAD_REQUEST
        )

    tipo_documento = request.query_params.get('tipo_documento', 'C')

    # Construir URL del servicio RUNT externo
    url = f"http://190.120.231.117:8080/api/runt_vehiculo/{placa or ''}/{tipo_documento}/{numero_documento or ''}"

    try:
        req = urllib.request.Request(url, method='GET')
        req.add_header('Accept', 'application/json')
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
        return Response(data, status=status.HTTP_200_OK)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return Response(
            {"error": f"Error del servicio RUNT: {e.code}", "detalle": body},
            status=e.code if 400 <= e.code < 600 else status.HTTP_502_BAD_GATEWAY
        )
    except urllib.error.URLError as e:
        return Response(
            {"error": f"No se pudo conectar al servicio RUNT: {str(e.reason)}"},
            status=status.HTTP_502_BAD_GATEWAY
        )
    except Exception as e:
        return Response(
            {"error": f"Error inesperado al consultar RUNT: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cotizador', 'view')])
def get_user_info_external(request):
    
    numero_documento = request.query_params.get('numero_documento', None)

    if not numero_documento:
        return Response(
            {"error": "Se requiere el parámetro 'numero_documento'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Construir URL del servicio RUNT externo
    url = f"http://190.120.231.117:8080/api/runt/{numero_documento}"

    try:
        req = urllib.request.Request(url, method='GET')
        req.add_header('Accept', 'application/json')
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
        return Response(data, status=status.HTTP_200_OK)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return Response(
            {"error": f"Error del servicio RUNT: {e.code}", "detalle": body},
            status=e.code if 400 <= e.code < 600 else status.HTTP_502_BAD_GATEWAY
        )
    except urllib.error.URLError as e:
        return Response(
            {"error": f"No se pudo conectar al servicio RUNT: {str(e.reason)}"},
            status=status.HTTP_502_BAD_GATEWAY
        )
    except Exception as e:
        return Response(
            {"error": f"Error inesperado al consultar RUNT: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('cotizador', 'view')])
def external_placa_runt(request):
    """
    Recibe una imagen de tarjeta de propiedad (multipart/form-data)
    y la reenvía al servicio externo de IA para extraer placa, tipo_documento y nro_documento.
    """
    imagen = request.FILES.get('imagen')
    if not imagen:
        return Response(
            {"error": "El campo 'imagen' es requerido."},
            status=status.HTTP_400_BAD_REQUEST
        )

    url = "http://190.120.231.117:8080/api/tarjeta_propiedad"

    try:
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

        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode('utf-8'))

        return Response(data, status=status.HTTP_200_OK)

    except urllib.error.HTTPError as e:
        body_resp = e.read().decode('utf-8', errors='replace')
        return Response(
            {"error": f"Error del servicio de IA: {e.code}", "detalle": body_resp},
            status=e.code if 400 <= e.code < 600 else status.HTTP_502_BAD_GATEWAY
        )
    except urllib.error.URLError as e:
        return Response(
            {"error": f"No se pudo conectar al servicio de IA: {str(e.reason)}"},
            status=status.HTTP_502_BAD_GATEWAY
        )
    except Exception as e:
        return Response(
            {"error": f"Error inesperado al procesar tarjeta de propiedad: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('cotizador', 'view')])
def external_vin(request):
    """
    Recibe una imagen de tarjeta de propiedad (multipart/form-data)
    y la reenvía al servicio externo de IA para extraer placa, tipo_documento y nro_documento.
    """
    imagen = request.FILES.get('imagen')
    if not imagen:
        return Response(
            {"error": "El campo 'imagen' es requerido."},
            status=status.HTTP_400_BAD_REQUEST
        )

    url = "http://190.120.231.117:8080/api/vin"

    try:
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

        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode('utf-8'))

        return Response(data, status=status.HTTP_200_OK)

    except urllib.error.HTTPError as e:
        body_resp = e.read().decode('utf-8', errors='replace')
        return Response(
            {"error": f"Error del servicio de IA: {e.code}", "detalle": body_resp},
            status=e.code if 400 <= e.code < 600 else status.HTTP_502_BAD_GATEWAY
        )
    except urllib.error.URLError as e:
        return Response(
            {"error": f"No se pudo conectar al servicio de IA: {str(e.reason)}"},
            status=status.HTTP_502_BAD_GATEWAY
        )
    except Exception as e:
        return Response(
            {"error": f"Error inesperado al procesar tarjeta de propiedad: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('cotizador', 'view')])
def api_falabella(request):
    placa = request.query_params.get('placa', None)

    if not placa:
        return Response(
            {"error": "Se requiere el parámetro 'placa'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Construir URL del servicio RUNT externo
    url = f"http://190.120.231.117:8080/api/previsora/{placa}"

    try:
        req = urllib.request.Request(url, method='GET')
        req.add_header('Accept', 'application/json')
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
        return Response(data, status=status.HTTP_200_OK)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return Response(
            {"error": f"Error del servicio placa: {e.code}", "detalle": body},
            status=e.code if 400 <= e.code < 600 else status.HTTP_502_BAD_GATEWAY
        )
    except urllib.error.URLError as e:
        return Response(
            {"error": f"No se pudo conectar al servicio placa: {str(e.reason)}"},
            status=status.HTTP_502_BAD_GATEWAY
        )
    except Exception as e:
        return Response(
            {"error": f"Error inesperado al consultar placa: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )