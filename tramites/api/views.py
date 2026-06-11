from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q, Exists, OuterRef
from datetime import datetime
import urllib.request
import urllib.error
import json

from ..models import Tramite, ENTIDAD_POR_TIPO_VEHICULO
from correos_aleatorios.models import CorreoAleatorio
from .permissions import RolePermission, ModulePermission

# Hosts de los generadores externos de links de pago.
PREVISORA_URLPAGO = 'http://130.94.105.156:9515/api/urlpago'
MUNDIAL_URL       = 'https://soat-scraper.qf4cjg.easypanel.host/api/mundial'


def entidad_por_defecto(tipo_vehiculo):
    """Devuelve la entidad por defecto para un tipo de vehículo (primera opción
    del catálogo). Si tipo_vehiculo no está mapeado, devuelve ''."""
    opciones = ENTIDAD_POR_TIPO_VEHICULO.get(tipo_vehiculo or '', [])
    return opciones[0] if opciones else ''


def serialize_tramite(tramite):
    """Convierte un objeto Tramite a diccionario"""
    return {
        'id': tramite.id,
        'usuario': {
            'id': tramite.usuario.id,
            'name': f"{tramite.usuario.first_name} {tramite.usuario.last_name}".strip(),
        } if tramite.usuario else None,
        'cliente': {
            'id': tramite.cliente.id,
            'nombre': tramite.cliente.nombre,
        } if tramite.cliente else None,
        'etiqueta': {
            'id': tramite.etiqueta.id,
            'nombre': tramite.etiqueta.nombre,
            'color': tramite.etiqueta.color,
        } if tramite.etiqueta else None,
        'precio_cliente': {
            'id': tramite.precio_cliente.id,
        } if tramite.precio_cliente else None,
        'tarifario_soat': {
            'id': tramite.tarifario_soat.id,
            'codigo_tarifa': tramite.tarifario_soat.codigo_tarifa,
            'descripcion': tramite.tarifario_soat.descripcion,
            'valor': str(tramite.tarifario_soat.valor),
        } if tramite.tarifario_soat else None,

        'tipo_tramite': tramite.tipo_tramite,
        'tipo_tramite_display': tramite.get_tipo_tramite_display(),
        'tipo_vehiculo': tramite.tipo_vehiculo,
        'tipo_vehiculo_display': tramite.get_tipo_vehiculo_display() if tramite.tipo_vehiculo else '',
        'entidad': tramite.entidad,
        'entidad_display': tramite.get_entidad_display() if tramite.entidad else '',

        'grupo_soat': tramite.grupo_soat,
        'grupo_soat_display': tramite.get_grupo_soat_display() if tramite.grupo_soat else '',
        'grupo_clase_runt': tramite.grupo_clase_runt,
        'grupo_subcriterio': tramite.grupo_subcriterio,
        'modulo_pregunta1': tramite.modulo_pregunta1,
        'modulo_pregunta2': tramite.modulo_pregunta2,
        'tarifa_codigo': tramite.tarifa_codigo,
        'tarifa_manual': tramite.tarifa_manual,

        'precio_lay': str(tramite.precio_lay) if tramite.precio_lay is not None else None,
        'comision': str(tramite.comision) if tramite.comision is not None else None,

        'placa': tramite.placa,
        'clase': tramite.clase,
        'tipo_servicio': tramite.tipo_servicio,
        'marca': tramite.marca,
        'linea': tramite.linea,
        'modelo': tramite.modelo,
        'color': tramite.color,
        'cilindraje': tramite.cilindraje,
        'pasajeros_sentados': tramite.pasajeros_sentados,
        'capacidad_carga': tramite.capacidad_carga,
        'peso_bruto': tramite.peso_bruto,
        'chasis': tramite.chasis,
        'vin': tramite.vin,

        'tipo_documento': tramite.tipo_documento,
        'tipo_documento_display': tramite.get_tipo_documento_display(),
        'numero_documento': tramite.numero_documento,
        'nombre_completo': tramite.nombre_completo,
        'telefono': tramite.telefono,
        'correo': tramite.correo,
        'direccion': tramite.direccion,

        'tramite_estado': tramite.tramite_estado,
        'confirmacion_estado': tramite.confirmacion_estado,
        'cargar_pdf_estado': tramite.cargar_pdf_estado,

        'created_at': tramite.created_at,
        'updated_at': tramite.updated_at,
        'deleted_at': tramite.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('tramites', 'create')])
def create_tramite(request):
    """Crear un nuevo trámite.

    Solo `cliente` es obligatorio. Los demás campos son opcionales para permitir
    guardado desde el flujo del Cotizador (Step 7) al presionar "Enviar a Trámites".
    """
    try:
        if not request.data.get('cliente'):
            return Response(
                {"error": "El campo cliente es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        tramite = Tramite.objects.create(
            usuario=request.user,
            cliente_id=request.data.get('cliente'),
            etiqueta_id=request.data.get('etiqueta') or None,
            precio_cliente_id=request.data.get('precio_cliente') or None,
            tarifario_soat_id=request.data.get('tarifario_soat') or None,

            tipo_tramite=request.data.get('tipo_tramite', 'SOAT') or 'SOAT',
            tipo_vehiculo=request.data.get('tipo_vehiculo', '') or '',
            # Si el cliente no envía entidad, derivar la default del tipo_vehiculo.
            entidad=(request.data.get('entidad') or entidad_por_defecto(request.data.get('tipo_vehiculo', ''))),

            grupo_soat=request.data.get('grupo_soat', '') or '',
            grupo_clase_runt=request.data.get('grupo_clase_runt', '') or '',
            grupo_subcriterio=request.data.get('grupo_subcriterio', '') or '',
            modulo_pregunta1=request.data.get('modulo_pregunta1', '') or '',
            modulo_pregunta2=request.data.get('modulo_pregunta2', '') or '',
            tarifa_codigo=request.data.get('tarifa_codigo', '') or '',
            tarifa_manual=bool(request.data.get('tarifa_manual', False)),

            precio_lay=request.data.get('precio_lay') or None,
            comision=request.data.get('comision') or None,

            placa=request.data.get('placa', '') or '',
            clase=request.data.get('clase', '') or '',
            tipo_servicio=request.data.get('tipo_servicio', '') or '',
            marca=request.data.get('marca', '') or '',
            linea=request.data.get('linea', '') or '',
            modelo=request.data.get('modelo', '') or '',
            color=request.data.get('color', '') or '',
            cilindraje=request.data.get('cilindraje', '') or '',
            pasajeros_sentados=request.data.get('pasajeros_sentados', '') or '',
            capacidad_carga=request.data.get('capacidad_carga', '') or '',
            peso_bruto=request.data.get('peso_bruto', '') or '',
            chasis=request.data.get('chasis', '') or '',
            vin=request.data.get('vin', '') or '',

            tipo_documento=request.data.get('tipo_documento', 'CC') or 'CC',
            numero_documento=request.data.get('numero_documento', '') or '',
            nombre_completo=request.data.get('nombre_completo', '') or '',
            telefono=request.data.get('telefono', '') or '',
            correo=request.data.get('correo', '') or '',
            direccion=request.data.get('direccion', '') or '',
        )

        return Response(serialize_tramite(tramite), status=status.HTTP_201_CREATED)

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


_TIPO_DOC_MAP = {
    'C': 'CC',   # Cédula de Ciudadanía
    'E': 'CE',   # Cédula de Extranjería
    'N': 'NIT',  # NIT
    'P': 'PAS',  # Pasaporte
}


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('tramites', 'create')])
def crear_desde_base_de_datos(request):
    """Crea un Trámite a partir de un RegistroVehiculo de BaseDeDatos.

    Solo copia titular + vehículo. Los campos SOAT/financieros quedan vacíos:
    el usuario los completa después editando el trámite en su módulo. El
    registro de BaseDeDatos queda intacto (base maestra reutilizable).

    Dispara `tramite_added_event` para que el listado de Trámites se
    refresque en tiempo real en el resto de sesiones.

    Payload:
        registro_id: int (requerido) — id del RegistroVehiculo
    """
    from base_de_datos.models import RegistroVehiculo

    registro_id = request.data.get('registro_id')
    if not registro_id:
        return Response({"error": "registro_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        registro = get_object_or_404(RegistroVehiculo.objects, pk=registro_id)
        if registro.is_deleted:
            return Response(
                {"error": "El registro de Base de Datos fue eliminado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # tipo_documento: BaseDeDatos usa códigos 1 char ('C','E','N','P','T',...).
        # Trámites solo soporta CC/CE/NIT/PAS. Otros tipos caen a CC por defecto.
        tipo_documento_tramite = _TIPO_DOC_MAP.get(registro.tipo_documento, 'CC')

        tramite = Tramite.objects.create(
            usuario=request.user,
            cliente=registro.cliente,
            etiqueta=None,
            precio_cliente=None,
            tarifario_soat=None,

            tipo_tramite=registro.tipo_tramite or 'SOAT',
            tipo_vehiculo=registro.tipo_vehiculo or '',

            grupo_soat='',
            grupo_clase_runt='',
            grupo_subcriterio='',
            modulo_pregunta1='',
            modulo_pregunta2='',
            tarifa_codigo='',
            tarifa_manual=False,

            precio_lay=None,
            comision=None,

            placa=registro.placa or '',
            clase=registro.clase or '',
            tipo_servicio=registro.tipo_servicio or '',
            marca=registro.marca or '',
            linea=registro.linea or '',
            modelo=(registro.modelo or '')[:4],
            color=registro.color or '',
            cilindraje=(registro.cilindraje or '')[:10],
            pasajeros_sentados='',
            capacidad_carga='',
            peso_bruto='',
            chasis=(registro.num_chasis or '')[:50],
            vin=(registro.vin or '')[:50],

            tipo_documento=tipo_documento_tramite,
            numero_documento=registro.numero_documento or '',
            nombre_completo=registro.nombre_completo or '',
            telefono=registro.telefono or '',
            correo='',
            direccion='',
        )

        # Broadcast WS: el listado de Trámites se refresca en tiempo real
        # en cualquier otra sesión que lo esté viendo.
        try:
            from users.realtime import notify_view_sync
            notify_view_sync(
                view_id='tramites_list',
                event_type='tramite_added_event',
                payload={'tramite_id': tramite.id, 'reason': 'created_from_base_de_datos'},
            )
        except Exception as e:
            print(f"WARNING: notify_view_sync fallo: {e}")

        return Response(serialize_tramite(tramite), status=status.HTTP_201_CREATED)

    except DatabaseError as e:
        return Response({"error": f"Error de base de datos: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('tramites', 'view')])
def list_tramites(request):
    """Listar trámites con filtros y paginación"""
    try:
        tramites = Tramite.objects.select_related(
            'usuario', 'cliente', 'etiqueta', 'precio_cliente', 'tarifario_soat'
        ).all()

        # Excluir trámites que ya fueron enviados a pasarela (con una pasarela activa,
        # no soft-deleted). Si se soft-borra la pasarela, el trámite reaparece.
        # Se usa Exists para evitar el LEFT JOIN que provoca falsos positivos
        # cuando el trámite no tiene ninguna pasarela asociada.
        from pasarela_de_pago.models import PasarelaPago
        active_pasarela = PasarelaPago.objects.filter(
            tramite_origen=OuterRef('pk'),
            deleted_at__isnull=True,
        )
        tramites = tramites.annotate(_has_active_pasarela=Exists(active_pasarela)).filter(_has_active_pasarela=False)

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            tramites = tramites.filter(
                Q(placa__icontains=search_query) |
                Q(nombre_completo__icontains=search_query) |
                Q(numero_documento__icontains=search_query) |
                Q(chasis__icontains=search_query) |
                Q(vin__icontains=search_query)
            )

        # Filtro por cliente
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            tramites = tramites.filter(cliente_id=cliente_id)

        # Filtro por etiqueta
        etiqueta_id = request.query_params.get('etiqueta', None)
        if etiqueta_id:
            tramites = tramites.filter(etiqueta_id=etiqueta_id)

        # Filtro por tipo de trámite
        tipo_tramite = request.query_params.get('tipo_tramite', None)
        if tipo_tramite:
            tramites = tramites.filter(tipo_tramite=tipo_tramite)

        # Filtro por grupo SOAT
        grupo_soat = request.query_params.get('grupo_soat', None)
        if grupo_soat:
            tramites = tramites.filter(grupo_soat=grupo_soat)

        # Filtro por tarifa
        tarifa_codigo = request.query_params.get('tarifa_codigo', None)
        if tarifa_codigo:
            tramites = tramites.filter(tarifa_codigo=tarifa_codigo)

        # Filtro por estados
        tramite_estado = request.query_params.get('tramite_estado', None)
        if tramite_estado:
            tramites = tramites.filter(tramite_estado=tramite_estado)

        confirmacion_estado = request.query_params.get('confirmacion_estado', None)
        if confirmacion_estado:
            tramites = tramites.filter(confirmacion_estado=confirmacion_estado)

        cargar_pdf_estado = request.query_params.get('cargar_pdf_estado', None)
        if cargar_pdf_estado:
            tramites = tramites.filter(cargar_pdf_estado=cargar_pdf_estado)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                tramites = tramites.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                tramites = tramites.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            tramites = tramites.filter(deleted_at__isnull=True)

        # Ordenar
        tramites = tramites.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(tramites, request)

        data = [serialize_tramite(t) for t in paginated]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener trámites: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('tramites', 'view')])
def get_tramite(request, pk):
    """Obtener un trámite por ID"""
    try:
        tramite = get_object_or_404(
            Tramite.objects.select_related('usuario', 'cliente', 'etiqueta', 'precio_cliente', 'tarifario_soat'),
            pk=pk
        )
        return Response(serialize_tramite(tramite), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener trámite: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('tramites', 'edit')])
def update_tramite(request, pk):
    """Actualizar un trámite"""
    try:
        tramite = get_object_or_404(Tramite.objects, pk=pk)

        # FKs si se proporcionan
        if 'cliente' in request.data:
            tramite.cliente_id = request.data.get('cliente')
        if 'etiqueta' in request.data:
            tramite.etiqueta_id = request.data.get('etiqueta')
        if 'precio_cliente' in request.data:
            tramite.precio_cliente_id = request.data.get('precio_cliente')
        if 'tarifario_soat' in request.data:
            tramite.tarifario_soat_id = request.data.get('tarifario_soat')

        # Tipo
        tramite.tipo_tramite = request.data.get('tipo_tramite', tramite.tipo_tramite)
        tramite.tipo_vehiculo = request.data.get('tipo_vehiculo', tramite.tipo_vehiculo)
        tramite.entidad = request.data.get('entidad', tramite.entidad)

        # Árbol Grupo SOAT
        tramite.grupo_soat = request.data.get('grupo_soat', tramite.grupo_soat)
        tramite.grupo_clase_runt = request.data.get('grupo_clase_runt', tramite.grupo_clase_runt)
        tramite.grupo_subcriterio = request.data.get('grupo_subcriterio', tramite.grupo_subcriterio)
        tramite.modulo_pregunta1 = request.data.get('modulo_pregunta1', tramite.modulo_pregunta1)
        tramite.modulo_pregunta2 = request.data.get('modulo_pregunta2', tramite.modulo_pregunta2)
        tramite.tarifa_codigo = request.data.get('tarifa_codigo', tramite.tarifa_codigo)
        if 'tarifa_manual' in request.data:
            tramite.tarifa_manual = bool(request.data.get('tarifa_manual'))

        # Valores
        tramite.precio_lay = request.data.get('precio_lay', tramite.precio_lay)
        tramite.comision = request.data.get('comision', tramite.comision)

        # Vehículo
        tramite.placa = request.data.get('placa', tramite.placa)
        tramite.clase = request.data.get('clase', tramite.clase)
        tramite.tipo_servicio = request.data.get('tipo_servicio', tramite.tipo_servicio)
        tramite.marca = request.data.get('marca', tramite.marca)
        tramite.linea = request.data.get('linea', tramite.linea)
        tramite.modelo = request.data.get('modelo', tramite.modelo)
        tramite.color = request.data.get('color', tramite.color)
        tramite.cilindraje = request.data.get('cilindraje', tramite.cilindraje)
        tramite.pasajeros_sentados = request.data.get('pasajeros_sentados', tramite.pasajeros_sentados)
        tramite.capacidad_carga = request.data.get('capacidad_carga', tramite.capacidad_carga)
        tramite.peso_bruto = request.data.get('peso_bruto', tramite.peso_bruto)
        tramite.chasis = request.data.get('chasis', tramite.chasis)
        tramite.vin = request.data.get('vin', tramite.vin)

        # Titular
        tramite.tipo_documento = request.data.get('tipo_documento', tramite.tipo_documento)
        tramite.numero_documento = request.data.get('numero_documento', tramite.numero_documento)
        tramite.nombre_completo = request.data.get('nombre_completo', tramite.nombre_completo)
        tramite.telefono = request.data.get('telefono', tramite.telefono)
        tramite.correo = request.data.get('correo', tramite.correo)
        tramite.direccion = request.data.get('direccion', tramite.direccion)

        # Estados
        tramite.tramite_estado = request.data.get('tramite_estado', tramite.tramite_estado)
        tramite.confirmacion_estado = request.data.get('confirmacion_estado', tramite.confirmacion_estado)
        tramite.cargar_pdf_estado = request.data.get('cargar_pdf_estado', tramite.cargar_pdf_estado)

        tramite.save()

        return Response(serialize_tramite(tramite), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('tramites', 'delete')])
def delete_tramite(request, pk):
    """Eliminar un trámite (soft delete)"""
    try:
        tramite = get_object_or_404(Tramite.objects, pk=pk)
        tramite.soft_delete()
        return Response(
            {"message": "Trámite eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar trámite: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('tramites', 'delete')])
def restore_tramite(request, pk):
    """Restaurar un trámite eliminado"""
    try:
        tramite = get_object_or_404(Tramite.objects, pk=pk)
        if not tramite.is_deleted:
            return Response(
                {"error": "El trámite no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        tramite.restore()
        return Response(serialize_tramite(tramite), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar trámite: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('tramites', 'delete')])
def hard_delete_tramite(request, pk):
    """Eliminar permanentemente un trámite"""
    try:
        tramite = get_object_or_404(Tramite.objects, pk=pk)
        tramite.delete()
        return Response(
            {"message": "Trámite eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar trámite: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('tramites', 'view')])
def tramite_history(request, pk):
    """Obtener el historial de cambios de un trámite"""
    try:
        tramite = get_object_or_404(Tramite.objects, pk=pk)
        history = tramite.history.all()

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
                'grupo_soat': h.grupo_soat,
                'tarifa_codigo': h.tarifa_codigo,
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('tramites', 'edit')])
def cambiar_estado(request, pk):
    """
    Cambiar el estado del trámite al siguiente paso.

    Body: { "paso": "confirmacion" | "cargaro" }

    Flujo:
    - tramite(1) → confirmacion: tramite_estado=0, confirmacion_estado=1
    - confirmacion(1) → cargaro: confirmacion_estado=0, cargar_pdf_estado=1
    """
    try:
        tramite = get_object_or_404(Tramite.objects, pk=pk)
        paso = request.data.get('paso')

        if not paso:
            return Response(
                {"error": "El campo 'paso' es requerido. Opciones: confirmacion, cargaro"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if paso not in ESTADO_TRANSICIONES:
            return Response(
                {"error": f"Paso inválido: {paso}. Opciones: confirmacion, cargaro"},
                status=status.HTTP_400_BAD_REQUEST
            )

        transicion = ESTADO_TRANSICIONES[paso]
        campo_desde = transicion['desde']
        campo_hacia = transicion['hacia']

        # Verificar que el estado actual permita la transición
        if getattr(tramite, campo_desde) != '1':
            return Response(
                {"error": f"No se puede avanzar a {transicion['nombre']}. El estado anterior no está activo."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar que no se haya pasado ya a este estado
        if getattr(tramite, campo_hacia) == '1':
            return Response(
                {"error": f"El trámite ya está en estado {transicion['nombre']}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Realizar la transición
        setattr(tramite, campo_desde, '0')
        setattr(tramite, campo_hacia, '1')
        tramite.save()

        return Response({
            "message": f"Estado actualizado a {transicion['nombre']} correctamente",
            "tramite": serialize_tramite(tramite)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al cambiar estado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('tramites', 'edit')])
def revertir_estado(request, pk):
    """
    Revertir el estado del trámite al paso anterior.

    Body: { "paso": "tramite" | "confirmacion" }

    Flujo inverso:
    - confirmacion(1) → tramite: confirmacion_estado=0, tramite_estado=1
    - cargaro(1) → confirmacion: cargar_pdf_estado=0, confirmacion_estado=1
    """
    try:
        tramite = get_object_or_404(Tramite.objects, pk=pk)
        paso = request.data.get('paso')

        REVERTIR_TRANSICIONES = {
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
                {"error": "El campo 'paso' es requerido. Opciones: tramite, confirmacion"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if paso not in REVERTIR_TRANSICIONES:
            return Response(
                {"error": f"Paso inválido: {paso}. Opciones: tramite, confirmacion"},
                status=status.HTTP_400_BAD_REQUEST
            )

        transicion = REVERTIR_TRANSICIONES[paso]
        campo_desde = transicion['desde']
        campo_hacia = transicion['hacia']

        # Verificar que el estado actual permita la reversión
        if getattr(tramite, campo_desde) != '1':
            return Response(
                {"error": f"No se puede revertir a {transicion['nombre']}. El estado actual no lo permite."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Realizar la reversión
        setattr(tramite, campo_desde, '0')
        setattr(tramite, campo_hacia, '1')
        tramite.save()

        return Response({
            "message": f"Estado revertido a {transicion['nombre']} correctamente",
            "tramite": serialize_tramite(tramite)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al revertir estado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== GENERADORES DE LINKS DE PAGO ====================
# Generan el link de pago (Previsora / Mundial) para un trámite, usando un
# correo aleatorio del pool del módulo `correos_aleatorios`.

def _formatear_token(valor):
    """
    Normaliza un nombre/apellido para el generador de Previsora.
    Si es compuesto (tiene espacios, ej. "de la cruz") lo concatena en uno solo
    ("delacruz"). Devuelve cadena vacía si no hay valor.
    """
    if not valor:
        return ''
    return ''.join(str(valor).split())


def _obtener_correo_aleatorio():
    """Devuelve un CorreoAleatorio activo (no eliminado) al azar, o None."""
    return (
        CorreoAleatorio.objects
        .filter(activo=True, deleted_at__isnull=True)
        .order_by('?')
        .first()
    )


def _resolver_correo(request):
    """
    Resuelve el correo a usar: el explícito del request o uno aleatorio del pool.
    Devuelve (correo_str, correo_obj|None, error_response|None).
    """
    correo = request.data.get('correo') or request.data.get('email')
    if correo:
        return correo, None, None
    obj = _obtener_correo_aleatorio()
    if not obj:
        return None, None, Response(
            {"error": "No hay correos aleatorios disponibles. Agrega al menos uno activo en el módulo de Correos Aleatorios."},
            status=status.HTTP_400_BAD_REQUEST
        )
    return obj.correo, obj, None


def _post_json_externo(url, payload, timeout=30):
    """
    POST JSON a un servicio externo. Devuelve (data, error_response).
    Si error_response no es None, el caller debe retornarlo directamente.
    """
    body = json.dumps(payload).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))
        return data, None
    except urllib.error.HTTPError as e:
        detalle = e.read().decode('utf-8', errors='replace')
        return None, Response(
            {"error": f"Error del servicio externo: {e.code}", "detalle": detalle},
            status=e.code if 400 <= e.code < 600 else status.HTTP_502_BAD_GATEWAY
        )
    except urllib.error.URLError as e:
        return None, Response(
            {"error": f"No se pudo conectar al servicio externo: {str(e.reason)}"},
            status=status.HTTP_502_BAD_GATEWAY
        )
    except Exception as e:
        return None, Response(
            {"error": f"Error inesperado al generar el link: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('tramites', 'view')])
def generar_link_previsora(request):
    """
    Genera un link de pago de Previsora para un trámite.
    Toma un correo aleatorio del pool (o el provisto en `correo`) y normaliza
    nombres/apellidos compuestos. `nombre2` y `apellido2` son opcionales.
    """
    placa = request.data.get('placa')
    documento = request.data.get('documento') or request.data.get('numero_documento')
    if not placa or not documento:
        return Response({"error": "Los campos placa y documento son requeridos."}, status=status.HTTP_400_BAD_REQUEST)

    correo, correo_obj, err = _resolver_correo(request)
    if err:
        return err

    payload = {
        "placa": placa,
        "tipodocumento": request.data.get('tipodocumento', 1),
        "documento": documento,
        "nombre": _formatear_token(request.data.get('nombre', '')),
        "apellido": _formatear_token(request.data.get('apellido', '')),
        "telefono": request.data.get('telefono', ''),
        "correo": correo,
    }
    # Campos opcionales: solo se incluyen si vienen con valor.
    nombre2 = _formatear_token(request.data.get('nombre2', ''))
    if nombre2:
        payload["nombre2"] = nombre2
    apellido2 = _formatear_token(request.data.get('apellido2', ''))
    if apellido2:
        payload["apellido2"] = apellido2

    data, err = _post_json_externo(PREVISORA_URLPAGO, payload)
    if err:
        # Adjuntar el correo usado y el payload al error para evidenciar que SÍ
        # se envió un correo aleatorio del pool, aunque el servicio externo falle.
        if isinstance(getattr(err, 'data', None), dict):
            err.data['correo_usado'] = correo
            err.data['payload'] = payload
        return err

    if correo_obj:
        correo_obj.registrar_uso()

    return Response({"data": data, "correo_usado": correo, "payload": payload}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('tramites', 'view')])
def generar_link_mundial(request):
    """
    Genera un link de pago de Mundial para un trámite.
    Toma un correo aleatorio del pool (o el provisto en `email`).
    """
    placa = request.data.get('placa')
    nro_documento = request.data.get('nro_documento') or request.data.get('documento') or request.data.get('numero_documento')
    if not placa or not nro_documento:
        return Response({"error": "Los campos placa y nro_documento son requeridos."}, status=status.HTTP_400_BAD_REQUEST)

    correo, correo_obj, err = _resolver_correo(request)
    if err:
        return err

    payload = {
        "placa": placa,
        "tipo_documento": request.data.get('tipo_documento', 'CC'),
        "nro_documento": nro_documento,
        "telefono": request.data.get('telefono', ''),
        "email": correo,
    }

    data, err = _post_json_externo(MUNDIAL_URL, payload)
    if err:
        # Adjuntar el correo usado y el payload al error para evidenciar que SÍ
        # se envió un correo aleatorio del pool, aunque el servicio externo falle.
        if isinstance(getattr(err, 'data', None), dict):
            err.data['correo_usado'] = correo
            err.data['payload'] = payload
        return err

    if correo_obj:
        correo_obj.registrar_uso()

    return Response({"data": data, "correo_usado": correo, "payload": payload}, status=status.HTTP_200_OK)
