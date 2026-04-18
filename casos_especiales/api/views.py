from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from ..models import CasoEspecial, CasoEspecialPagos
from .permissions import RolePermission, ModulePermission


def serialize_caso_especial(caso):
    """Convierte un objeto CasoEspecial a diccionario"""
    return {
        'id': caso.id,
        'usuario': {
            'id': caso.usuario.id,
            'name': f"{caso.usuario.first_name} {caso.usuario.last_name}".strip(),
        } if caso.usuario else None,
        'cliente': {
            'id': caso.cliente.id,
            'nombre': caso.cliente.nombre,
        } if caso.cliente else None,
        'etiqueta': {
            'id': caso.etiqueta.id,
            'nombre': caso.etiqueta.nombre,
            'color': caso.etiqueta.color,
        } if caso.etiqueta else None,
        'precio_cliente': {
            'id': caso.precio_cliente.id,
        } if caso.precio_cliente else None,
        'descripcion': caso.descripcion,
        'precio_lay': str(caso.precio_lay),
        'comision': str(caso.comision),
        'placa': caso.placa,
        'clindraje': caso.clindraje,
        'modelo': caso.modelo,
        'chasis': caso.chasis,
        'tipo_documento': caso.tipo_documento,
        'tipo_documento_display': caso.get_tipo_documento_display(),
        'numero_documento': caso.numero_documento,
        'nombre_completo': caso.nombre_completo,
        'telefono': caso.telefono,
        'correo': caso.correo,
        'direccion': caso.direccion,
        'caso_especial_estado': caso.caso_especial_estado,
        'tramite_estado': caso.tramite_estado,
        'confirmacion_estado': caso.confirmacion_estado,
        'cargar_pdf_estado': caso.cargar_pdf_estado,
        'created_at': caso.created_at,
        'updated_at': caso.updated_at,
        'deleted_at': caso.deleted_at,
    }


def serialize_pago(pago):
    """Convierte un objeto CasoEspecialPagos a diccionario"""
    return {
        'id': pago.id,
        'caso_especial_id': pago.caso_especial_id,
        'precio_lay': str(pago.precio_lay),
        'comision': str(pago.comision),
        'fecha_pago': pago.fecha_pago,
        'created_at': pago.created_at,
        'updated_at': pago.updated_at,
        'deleted_at': pago.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('casos_especiales', 'create')])
def create_caso_especial(request):
    """Crear un nuevo caso especial.

    Solo `cliente` es obligatorio. Los demás campos son opcionales para permitir
    guardado parcial desde el flujo del Cotizador cuando se detecta un caso especial.
    """
    try:
        if not request.data.get('cliente'):
            return Response(
                {"error": "El campo cliente es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        caso = CasoEspecial.objects.create(
            usuario=request.user,
            cliente_id=request.data.get('cliente'),
            etiqueta_id=request.data.get('etiqueta') or None,
            precio_cliente_id=request.data.get('precio_cliente') or None,
            descripcion=request.data.get('descripcion', '') or '',
            precio_lay=request.data.get('precio_lay') or None,
            comision=request.data.get('comision') or None,
            placa=request.data.get('placa', '') or '',
            clindraje=request.data.get('clindraje', '') or '',
            modelo=request.data.get('modelo', '') or '',
            chasis=request.data.get('chasis', '') or '',
            tipo_documento=request.data.get('tipo_documento', 'CC') or 'CC',
            numero_documento=request.data.get('numero_documento', '') or '',
            nombre_completo=request.data.get('nombre_completo', '') or '',
            telefono=request.data.get('telefono', '') or '',
            correo=request.data.get('correo', '') or '',
            direccion=request.data.get('direccion', '') or '',
        )

        return Response(serialize_caso_especial(caso), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('casos_especiales', 'view')])
def list_casos_especiales(request):
    """Listar casos especiales con filtros y paginación"""
    try:
        casos = CasoEspecial.objects.select_related(
            'usuario', 'cliente', 'etiqueta', 'precio_cliente'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            casos = casos.filter(
                Q(placa__icontains=search_query) |
                Q(nombre_completo__icontains=search_query) |
                Q(numero_documento__icontains=search_query) |
                Q(chasis__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            casos = casos.filter(cliente_id=cliente_id)

        # Filtro por etiqueta
        etiqueta_id = request.query_params.get('etiqueta', None)
        if etiqueta_id:
            casos = casos.filter(etiqueta_id=etiqueta_id)

        # Filtro por estados
        caso_especial_estado = request.query_params.get('caso_especial_estado', None)
        if caso_especial_estado:
            casos = casos.filter(caso_especial_estado=caso_especial_estado)

        tramite_estado = request.query_params.get('tramite_estado', None)
        if tramite_estado:
            casos = casos.filter(tramite_estado=tramite_estado)

        confirmacion_estado = request.query_params.get('confirmacion_estado', None)
        if confirmacion_estado:
            casos = casos.filter(confirmacion_estado=confirmacion_estado)

        cargar_pdf_estado = request.query_params.get('cargar_pdf_estado', None)
        if cargar_pdf_estado:
            casos = casos.filter(cargar_pdf_estado=cargar_pdf_estado)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                casos = casos.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                casos = casos.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            casos = casos.filter(deleted_at__isnull=True)

        # Ordenar
        casos = casos.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(casos, request)

        data = [serialize_caso_especial(c) for c in paginated]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener casos especiales: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('casos_especiales', 'view')])
def get_caso_especial(request, pk):
    """Obtener un caso especial por ID"""
    try:
        caso = get_object_or_404(
            CasoEspecial.objects.select_related('usuario', 'cliente', 'etiqueta', 'precio_cliente'),
            pk=pk
        )
        return Response(serialize_caso_especial(caso), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener caso especial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('casos_especiales', 'edit')])
def update_caso_especial(request, pk):
    """Actualizar un caso especial"""
    try:
        caso = get_object_or_404(CasoEspecial.objects, pk=pk)

        # Actualizar campos FK si se proporcionan
        if 'cliente' in request.data:
            caso.cliente_id = request.data.get('cliente')
        if 'etiqueta' in request.data:
            caso.etiqueta_id = request.data.get('etiqueta')
        if 'precio_cliente' in request.data:
            caso.precio_cliente_id = request.data.get('precio_cliente')

        # Actualizar campos de texto
        caso.descripcion = request.data.get('descripcion', caso.descripcion)
        caso.precio_lay = request.data.get('precio_lay', caso.precio_lay)
        caso.comision = request.data.get('comision', caso.comision)
        caso.placa = request.data.get('placa', caso.placa)
        caso.clindraje = request.data.get('clindraje', caso.clindraje)
        caso.modelo = request.data.get('modelo', caso.modelo)
        caso.chasis = request.data.get('chasis', caso.chasis)
        caso.tipo_documento = request.data.get('tipo_documento', caso.tipo_documento)
        caso.numero_documento = request.data.get('numero_documento', caso.numero_documento)
        caso.nombre_completo = request.data.get('nombre_completo', caso.nombre_completo)
        caso.telefono = request.data.get('telefono', caso.telefono)
        caso.correo = request.data.get('correo', caso.correo)
        caso.direccion = request.data.get('direccion', caso.direccion)

        # Actualizar estados
        caso.caso_especial_estado = request.data.get('caso_especial_estado', caso.caso_especial_estado)
        caso.tramite_estado = request.data.get('tramite_estado', caso.tramite_estado)
        caso.confirmacion_estado = request.data.get('confirmacion_estado', caso.confirmacion_estado)
        caso.cargar_pdf_estado = request.data.get('cargar_pdf_estado', caso.cargar_pdf_estado)

        caso.save()

        return Response(serialize_caso_especial(caso), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('casos_especiales', 'delete')])
def delete_caso_especial(request, pk):
    """Eliminar un caso especial (soft delete)"""
    try:
        caso = get_object_or_404(CasoEspecial.objects, pk=pk)
        caso.soft_delete()
        return Response(
            {"message": "Caso especial eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar caso especial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('casos_especiales', 'delete')])
def restore_caso_especial(request, pk):
    """Restaurar un caso especial eliminado"""
    try:
        caso = get_object_or_404(CasoEspecial.objects, pk=pk)
        if not caso.is_deleted:
            return Response(
                {"error": "El caso especial no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        caso.restore()
        return Response(serialize_caso_especial(caso), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar caso especial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('casos_especiales', 'delete')])
def hard_delete_caso_especial(request, pk):
    """Eliminar permanentemente un caso especial"""
    try:
        caso = get_object_or_404(CasoEspecial.objects, pk=pk)
        caso.delete()
        return Response(
            {"message": "Caso especial eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar caso especial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('casos_especiales', 'view')])
def caso_especial_history(request, pk):
    """Obtener el historial de cambios de un caso especial"""
    try:
        caso = get_object_or_404(CasoEspecial.objects, pk=pk)
        history = caso.history.all()

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
                'caso_especial_estado': h.caso_especial_estado,
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
        'desde': 'caso_especial_estado',
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('casos_especiales', 'edit')])
def cambiar_estado(request, pk):
    """
    Cambiar el estado del caso especial al siguiente paso.

    Body: { "paso": "tramite" | "confirmacion" | "cargaro" }

    Flujo:
    - caso_especial(1) → tramite: caso_especial_estado=0, tramite_estado=1
    - tramite(1) → confirmacion: tramite_estado=0, confirmacion_estado=1
    - confirmacion(1) → cargaro: confirmacion_estado=0, cargar_pdf_estado=1
    """
    try:
        caso = get_object_or_404(CasoEspecial.objects, pk=pk)
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
        if getattr(caso, campo_desde) != '1':
            return Response(
                {"error": f"No se puede avanzar a {transicion['nombre']}. El estado anterior no está activo."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar que no se haya pasado ya a este estado
        if getattr(caso, campo_hacia) == '1':
            return Response(
                {"error": f"El caso especial ya está en estado {transicion['nombre']}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Realizar la transición
        setattr(caso, campo_desde, '0')
        setattr(caso, campo_hacia, '1')
        caso.save()

        return Response({
            "message": f"Estado actualizado a {transicion['nombre']} correctamente",
            "caso_especial": serialize_caso_especial(caso)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al cambiar estado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('casos_especiales', 'edit')])
def revertir_estado(request, pk):
    """
    Revertir el estado del caso especial al paso anterior.

    Body: { "paso": "caso_especial" | "tramite" | "confirmacion" }

    Flujo inverso:
    - tramite(1) → caso_especial: tramite_estado=0, caso_especial_estado=1
    - confirmacion(1) → tramite: confirmacion_estado=0, tramite_estado=1
    - cargaro(1) → confirmacion: cargar_pdf_estado=0, confirmacion_estado=1
    """
    try:
        caso = get_object_or_404(CasoEspecial.objects, pk=pk)
        paso = request.data.get('paso')

        REVERTIR_TRANSICIONES = {
            'caso_especial': {
                'desde': 'tramite_estado',
                'hacia': 'caso_especial_estado',
                'nombre': 'Caso Especial'
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
                {"error": "El campo 'paso' es requerido. Opciones: caso_especial, tramite, confirmacion"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if paso not in REVERTIR_TRANSICIONES:
            return Response(
                {"error": f"Paso inválido: {paso}. Opciones: caso_especial, tramite, confirmacion"},
                status=status.HTTP_400_BAD_REQUEST
            )

        transicion = REVERTIR_TRANSICIONES[paso]
        campo_desde = transicion['desde']
        campo_hacia = transicion['hacia']

        # Verificar que el estado actual permita la reversión
        if getattr(caso, campo_desde) != '1':
            return Response(
                {"error": f"No se puede revertir a {transicion['nombre']}. El estado actual no lo permite."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Realizar la reversión
        setattr(caso, campo_desde, '0')
        setattr(caso, campo_hacia, '1')
        caso.save()

        return Response({
            "message": f"Estado revertido a {transicion['nombre']} correctamente",
            "caso_especial": serialize_caso_especial(caso)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al revertir estado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== PAGOS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('casos_especiales', 'create')])
def create_pago(request, caso_especial_pk):
    """Crear un nuevo pago para un caso especial"""
    try:
        caso = get_object_or_404(CasoEspecial.objects, pk=caso_especial_pk)

        required_fields = ['precio_lay', 'comision', 'fecha_pago']
        for field in required_fields:
            if not request.data.get(field):
                return Response(
                    {"error": f"El campo {field} es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        pago = CasoEspecialPagos.objects.create(
            caso_especial=caso,
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
@permission_classes([IsAuthenticated, ModulePermission('casos_especiales', 'view')])
def list_pagos(request, caso_especial_pk):
    """Listar pagos de un caso especial"""
    try:
        caso = get_object_or_404(CasoEspecial.objects, pk=caso_especial_pk)
        pagos = CasoEspecialPagos.objects.filter(caso_especial=caso, deleted_at__isnull=True)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador']), ModulePermission('casos_especiales', 'edit')])
def update_pago(request, pk):
    """Actualizar un pago"""
    try:
        pago = get_object_or_404(CasoEspecialPagos.objects, pk=pk)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('casos_especiales', 'delete')])
def delete_pago(request, pk):
    """Eliminar un pago (soft delete)"""
    try:
        pago = get_object_or_404(CasoEspecialPagos.objects, pk=pk)
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
