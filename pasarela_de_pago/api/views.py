from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q
from datetime import datetime

from ..models import PasarelaPago
from .permissions import RolePermission, ModulePermission


def serialize_pasarela(pasarela):
    """Convierte un objeto PasarelaPago a diccionario"""
    return {
        'id': pasarela.id,
        'tramite_origen': pasarela.tramite_origen_id,
        'usuario': {
            'id': pasarela.usuario.id,
            'name': f"{pasarela.usuario.first_name} {pasarela.usuario.last_name}".strip(),
        } if pasarela.usuario else None,
        'cliente': {
            'id': pasarela.cliente.id,
            'nombre': pasarela.cliente.nombre,
        } if pasarela.cliente else None,
        'etiqueta': {
            'id': pasarela.etiqueta.id,
            'nombre': pasarela.etiqueta.nombre,
            'color': pasarela.etiqueta.color,
        } if pasarela.etiqueta else None,
        'precio_cliente': {
            'id': pasarela.precio_cliente.id,
        } if pasarela.precio_cliente else None,
        'tarifario_soat': {
            'id': pasarela.tarifario_soat.id,
            'codigo_tarifa': pasarela.tarifario_soat.codigo_tarifa,
            'descripcion': pasarela.tarifario_soat.descripcion,
            'valor': str(pasarela.tarifario_soat.valor),
        } if pasarela.tarifario_soat else None,
        'tarjeta': {
            'id': pasarela.tarjeta.id,
            'numero': pasarela.tarjeta.numero,
            'titular': pasarela.tarjeta.titular,
            'cuatro_por_mil': pasarela.tarjeta.cuatro_por_mil,
        } if pasarela.tarjeta else None,

        'tipo_tramite': pasarela.tipo_tramite,
        'tipo_tramite_display': pasarela.get_tipo_tramite_display(),
        'tipo_vehiculo': pasarela.tipo_vehiculo,
        'tipo_vehiculo_display': pasarela.get_tipo_vehiculo_display() if pasarela.tipo_vehiculo else '',

        'grupo_soat': pasarela.grupo_soat,
        'grupo_soat_display': pasarela.get_grupo_soat_display() if pasarela.grupo_soat else '',
        'grupo_clase_runt': pasarela.grupo_clase_runt,
        'grupo_subcriterio': pasarela.grupo_subcriterio,
        'modulo_pregunta1': pasarela.modulo_pregunta1,
        'modulo_pregunta2': pasarela.modulo_pregunta2,
        'tarifa_codigo': pasarela.tarifa_codigo,
        'tarifa_manual': pasarela.tarifa_manual,

        'precio_lay': str(pasarela.precio_lay) if pasarela.precio_lay is not None else None,
        'comision': str(pasarela.comision) if pasarela.comision is not None else None,

        'placa': pasarela.placa,
        'clase': pasarela.clase,
        'tipo_servicio': pasarela.tipo_servicio,
        'marca': pasarela.marca,
        'linea': pasarela.linea,
        'modelo': pasarela.modelo,
        'color': pasarela.color,
        'cilindraje': pasarela.cilindraje,
        'pasajeros_sentados': pasarela.pasajeros_sentados,
        'capacidad_carga': pasarela.capacidad_carga,
        'peso_bruto': pasarela.peso_bruto,
        'chasis': pasarela.chasis,
        'vin': pasarela.vin,

        'tipo_documento': pasarela.tipo_documento,
        'tipo_documento_display': pasarela.get_tipo_documento_display(),
        'numero_documento': pasarela.numero_documento,
        'nombre_completo': pasarela.nombre_completo,
        'telefono': pasarela.telefono,
        'correo': pasarela.correo,
        'direccion': pasarela.direccion,

        'tramite_estado': pasarela.tramite_estado,
        'confirmacion_estado': pasarela.confirmacion_estado,
        'cargar_pdf_estado': pasarela.cargar_pdf_estado,

        'observacion': pasarela.observacion,

        'created_at': pasarela.created_at,
        'updated_at': pasarela.updated_at,
        'deleted_at': pasarela.deleted_at,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('pasarela_de_pago', 'create')])
def create_pasarela(request):
    """Crear un nuevo registro en pasarela de pago.

    Solo `cliente` es obligatorio. Los demás campos son opcionales para permitir
    el "Enviar a pasarela" desde el módulo de Trámites con snapshot completo.
    """
    try:
        if not request.data.get('cliente'):
            return Response(
                {"error": "El campo cliente es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        pasarela = PasarelaPago.objects.create(
            tramite_origen_id=request.data.get('tramite_origen') or None,
            usuario=request.user,
            cliente_id=request.data.get('cliente'),
            etiqueta_id=request.data.get('etiqueta') or None,
            precio_cliente_id=request.data.get('precio_cliente') or None,
            tarifario_soat_id=request.data.get('tarifario_soat') or None,
            tarjeta_id=request.data.get('tarjeta') or None,

            tipo_tramite=request.data.get('tipo_tramite', 'SOAT') or 'SOAT',
            tipo_vehiculo=request.data.get('tipo_vehiculo', '') or '',

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

            observacion=request.data.get('observacion', '') or '',
        )

        # Snapshot a finalizados_tramites cuando viene de un trámite.
        # Best-effort: si falla no rompe la creación de la pasarela.
        if pasarela.tramite_origen_id:
            try:
                from finalizados_tramites.models import TramiteFinalizado
                from django.utils import timezone as _tz
                from decimal import Decimal

                # Snapshot del 4x1000 al momento del cierre.
                # Aplica solo cuando la tarjeta tiene cuatro_por_mil='1'.
                aplica_4x1000 = bool(pasarela.tarjeta and pasarela.tarjeta.cuatro_por_mil == '1')
                base = (pasarela.precio_lay or Decimal('0')) + (pasarela.comision or Decimal('0'))
                cuatro_por_mil_valor = (base * Decimal('4') / Decimal('1000')) if aplica_4x1000 else Decimal('0')

                TramiteFinalizado.objects.create(
                    pasarela=pasarela,
                    tramite_origen_id_snapshot=pasarela.tramite_origen_id,
                    usuario=pasarela.tramite_origen.usuario if pasarela.tramite_origen else request.user,
                    usuario_que_confirma=request.user,
                    cliente=pasarela.cliente,
                    etiqueta=pasarela.etiqueta,
                    precio_cliente=pasarela.precio_cliente,
                    tarifario_soat=pasarela.tarifario_soat,
                    tarjeta=pasarela.tarjeta,
                    tipo_tramite=pasarela.tipo_tramite,
                    tipo_vehiculo=pasarela.tipo_vehiculo,
                    grupo_soat=pasarela.grupo_soat,
                    grupo_clase_runt=pasarela.grupo_clase_runt,
                    grupo_subcriterio=pasarela.grupo_subcriterio,
                    modulo_pregunta1=pasarela.modulo_pregunta1,
                    modulo_pregunta2=pasarela.modulo_pregunta2,
                    tarifa_codigo=pasarela.tarifa_codigo,
                    tarifa_manual=pasarela.tarifa_manual,
                    precio_lay=pasarela.precio_lay,
                    comision=pasarela.comision,
                    placa=pasarela.placa,
                    clase=pasarela.clase,
                    tipo_servicio=pasarela.tipo_servicio,
                    marca=pasarela.marca,
                    linea=pasarela.linea,
                    modelo=pasarela.modelo,
                    color=pasarela.color,
                    cilindraje=pasarela.cilindraje,
                    pasajeros_sentados=pasarela.pasajeros_sentados,
                    capacidad_carga=pasarela.capacidad_carga,
                    peso_bruto=pasarela.peso_bruto,
                    chasis=pasarela.chasis,
                    vin=pasarela.vin,
                    tipo_documento=pasarela.tipo_documento,
                    numero_documento=pasarela.numero_documento,
                    nombre_completo=pasarela.nombre_completo,
                    telefono=pasarela.telefono,
                    correo=pasarela.correo,
                    direccion=pasarela.direccion,
                    tramite_estado=pasarela.tramite_estado,
                    confirmacion_estado=pasarela.confirmacion_estado,
                    cargar_pdf_estado=pasarela.cargar_pdf_estado,
                    observacion=pasarela.observacion,
                    pago_confirmado_at=_tz.now(),
                    cuatro_por_mil_valor=cuatro_por_mil_valor,
                )
            except Exception as e:
                print(f"WARNING: TramiteFinalizado.create fallo: {e}")

        # Notificar en tiempo real:
        # 1) Lista de tramites: este tramite sale (fue enviado a pasarela).
        # 2) Lista de pasarela: aparece un nuevo registro.
        # Best effort: cualquier fallo aqui no debe romper la creacion.
        try:
            from users.realtime import notify_view_sync
            if pasarela.tramite_origen_id:
                notify_view_sync(
                    view_id='tramites_list',
                    event_type='tramite_removed_event',
                    payload={
                        'tramite_id': pasarela.tramite_origen_id,
                        'reason': 'sent_to_pasarela',
                    },
                )
            notify_view_sync(
                view_id='pasarela_de_pago_list',
                event_type='pasarela_added_event',
                payload={
                    'pasarela_id': pasarela.id,
                    'reason': 'created',
                },
            )
        except Exception as e:
            print(f"WARNING: notify_view_sync fallo: {e}")

        return Response(serialize_pasarela(pasarela), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('pasarela_de_pago', 'view')])
def list_pasarelas(request):
    """Listar registros de pasarela con filtros y paginación"""
    try:
        pasarelas = PasarelaPago.objects.select_related(
            'usuario', 'cliente', 'etiqueta', 'precio_cliente', 'tarifario_soat', 'tramite_origen'
        ).all()

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            pasarelas = pasarelas.filter(
                Q(placa__icontains=search_query) |
                Q(nombre_completo__icontains=search_query) |
                Q(numero_documento__icontains=search_query) |
                Q(chasis__icontains=search_query) |
                Q(vin__icontains=search_query)
            )

        # Filtros
        cliente_id = request.query_params.get('cliente', None)
        if cliente_id:
            pasarelas = pasarelas.filter(cliente_id=cliente_id)

        etiqueta_id = request.query_params.get('etiqueta', None)
        if etiqueta_id:
            pasarelas = pasarelas.filter(etiqueta_id=etiqueta_id)

        tramite_origen = request.query_params.get('tramite_origen', None)
        if tramite_origen:
            pasarelas = pasarelas.filter(tramite_origen_id=tramite_origen)

        tipo_tramite = request.query_params.get('tipo_tramite', None)
        if tipo_tramite:
            pasarelas = pasarelas.filter(tipo_tramite=tipo_tramite)

        grupo_soat = request.query_params.get('grupo_soat', None)
        if grupo_soat:
            pasarelas = pasarelas.filter(grupo_soat=grupo_soat)

        tarifa_codigo = request.query_params.get('tarifa_codigo', None)
        if tarifa_codigo:
            pasarelas = pasarelas.filter(tarifa_codigo=tarifa_codigo)

        tramite_estado = request.query_params.get('tramite_estado', None)
        if tramite_estado:
            pasarelas = pasarelas.filter(tramite_estado=tramite_estado)

        confirmacion_estado = request.query_params.get('confirmacion_estado', None)
        if confirmacion_estado:
            pasarelas = pasarelas.filter(confirmacion_estado=confirmacion_estado)

        cargar_pdf_estado = request.query_params.get('cargar_pdf_estado', None)
        if cargar_pdf_estado:
            pasarelas = pasarelas.filter(cargar_pdf_estado=cargar_pdf_estado)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                pasarelas = pasarelas.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                pasarelas = pasarelas.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            pasarelas = pasarelas.filter(deleted_at__isnull=True)

        pasarelas = pasarelas.order_by('-created_at')

        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated = paginator.paginate_queryset(pasarelas, request)

        data = [serialize_pasarela(p) for p in paginated]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener registros de pasarela: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ModulePermission('pasarela_de_pago', 'view')])
def get_pasarela(request, pk):
    """Obtener un registro de pasarela por ID"""
    try:
        pasarela = get_object_or_404(
            PasarelaPago.objects.select_related('usuario', 'cliente', 'etiqueta', 'precio_cliente', 'tarifario_soat', 'tramite_origen'),
            pk=pk
        )
        return Response(serialize_pasarela(pasarela), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener registro de pasarela: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('pasarela_de_pago', 'edit')])
def update_pasarela(request, pk):
    """Actualizar un registro de pasarela"""
    try:
        pasarela = get_object_or_404(PasarelaPago.objects, pk=pk)

        # FKs si se proporcionan
        if 'tramite_origen' in request.data:
            pasarela.tramite_origen_id = request.data.get('tramite_origen') or None
        if 'cliente' in request.data:
            pasarela.cliente_id = request.data.get('cliente')
        if 'etiqueta' in request.data:
            pasarela.etiqueta_id = request.data.get('etiqueta')
        if 'precio_cliente' in request.data:
            pasarela.precio_cliente_id = request.data.get('precio_cliente')
        if 'tarifario_soat' in request.data:
            pasarela.tarifario_soat_id = request.data.get('tarifario_soat')
        if 'tarjeta' in request.data:
            pasarela.tarjeta_id = request.data.get('tarjeta') or None

        # Tipo
        pasarela.tipo_tramite = request.data.get('tipo_tramite', pasarela.tipo_tramite)
        pasarela.tipo_vehiculo = request.data.get('tipo_vehiculo', pasarela.tipo_vehiculo)

        # Árbol Grupo SOAT
        pasarela.grupo_soat = request.data.get('grupo_soat', pasarela.grupo_soat)
        pasarela.grupo_clase_runt = request.data.get('grupo_clase_runt', pasarela.grupo_clase_runt)
        pasarela.grupo_subcriterio = request.data.get('grupo_subcriterio', pasarela.grupo_subcriterio)
        pasarela.modulo_pregunta1 = request.data.get('modulo_pregunta1', pasarela.modulo_pregunta1)
        pasarela.modulo_pregunta2 = request.data.get('modulo_pregunta2', pasarela.modulo_pregunta2)
        pasarela.tarifa_codigo = request.data.get('tarifa_codigo', pasarela.tarifa_codigo)
        if 'tarifa_manual' in request.data:
            pasarela.tarifa_manual = bool(request.data.get('tarifa_manual'))

        # Valores
        pasarela.precio_lay = request.data.get('precio_lay', pasarela.precio_lay)
        pasarela.comision = request.data.get('comision', pasarela.comision)

        # Vehículo
        pasarela.placa = request.data.get('placa', pasarela.placa)
        pasarela.clase = request.data.get('clase', pasarela.clase)
        pasarela.tipo_servicio = request.data.get('tipo_servicio', pasarela.tipo_servicio)
        pasarela.marca = request.data.get('marca', pasarela.marca)
        pasarela.linea = request.data.get('linea', pasarela.linea)
        pasarela.modelo = request.data.get('modelo', pasarela.modelo)
        pasarela.color = request.data.get('color', pasarela.color)
        pasarela.cilindraje = request.data.get('cilindraje', pasarela.cilindraje)
        pasarela.pasajeros_sentados = request.data.get('pasajeros_sentados', pasarela.pasajeros_sentados)
        pasarela.capacidad_carga = request.data.get('capacidad_carga', pasarela.capacidad_carga)
        pasarela.peso_bruto = request.data.get('peso_bruto', pasarela.peso_bruto)
        pasarela.chasis = request.data.get('chasis', pasarela.chasis)
        pasarela.vin = request.data.get('vin', pasarela.vin)

        # Titular
        pasarela.tipo_documento = request.data.get('tipo_documento', pasarela.tipo_documento)
        pasarela.numero_documento = request.data.get('numero_documento', pasarela.numero_documento)
        pasarela.nombre_completo = request.data.get('nombre_completo', pasarela.nombre_completo)
        pasarela.telefono = request.data.get('telefono', pasarela.telefono)
        pasarela.correo = request.data.get('correo', pasarela.correo)
        pasarela.direccion = request.data.get('direccion', pasarela.direccion)

        # Estados
        pasarela.tramite_estado = request.data.get('tramite_estado', pasarela.tramite_estado)
        pasarela.confirmacion_estado = request.data.get('confirmacion_estado', pasarela.confirmacion_estado)
        pasarela.cargar_pdf_estado = request.data.get('cargar_pdf_estado', pasarela.cargar_pdf_estado)

        # Observación opcional
        pasarela.observacion = request.data.get('observacion', pasarela.observacion)

        pasarela.save()

        return Response(serialize_pasarela(pasarela), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('pasarela_de_pago', 'delete')])
def delete_pasarela(request, pk):
    """Eliminar un registro de pasarela (soft delete) = "devolver a tramites"."""
    try:
        pasarela = get_object_or_404(PasarelaPago.objects, pk=pk)
        tramite_origen_id = pasarela.tramite_origen_id
        pasarela.soft_delete()

        # Notificar en tiempo real:
        # 1) Lista de pasarela: este registro sale.
        # 2) Lista de tramites: el tramite origen vuelve a aparecer.
        try:
            from users.realtime import notify_view_sync
            notify_view_sync(
                view_id='pasarela_de_pago_list',
                event_type='pasarela_removed_event',
                payload={'pasarela_id': pasarela.id, 'reason': 'soft_deleted'},
            )
            if tramite_origen_id:
                notify_view_sync(
                    view_id='tramites_list',
                    event_type='tramite_restored_event',
                    payload={'tramite_id': tramite_origen_id, 'reason': 'pasarela_returned'},
                )
        except Exception as e:
            print(f"WARNING: notify_view_sync fallo: {e}")

        return Response(
            {"message": "Registro de pasarela eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar registro de pasarela: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('pasarela_de_pago', 'delete')])
def restore_pasarela(request, pk):
    """Restaurar un registro de pasarela eliminado"""
    try:
        pasarela = get_object_or_404(PasarelaPago.objects, pk=pk)
        if not pasarela.is_deleted:
            return Response(
                {"error": "El registro no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        pasarela.restore()

        # Notificar: la pasarela vuelve a aparecer y el tramite sale del listado.
        try:
            from users.realtime import notify_view_sync
            notify_view_sync(
                view_id='pasarela_de_pago_list',
                event_type='pasarela_added_event',
                payload={'pasarela_id': pasarela.id, 'reason': 'restored'},
            )
            if pasarela.tramite_origen_id:
                notify_view_sync(
                    view_id='tramites_list',
                    event_type='tramite_removed_event',
                    payload={'tramite_id': pasarela.tramite_origen_id, 'reason': 'pasarela_restored'},
                )
        except Exception as e:
            print(f"WARNING: notify_view_sync fallo: {e}")

        return Response(serialize_pasarela(pasarela), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar registro de pasarela: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('pasarela_de_pago', 'delete')])
def hard_delete_pasarela(request, pk):
    """Eliminar permanentemente un registro de pasarela"""
    try:
        pasarela = get_object_or_404(PasarelaPago.objects, pk=pk)
        pasarela_id = pasarela.id
        pasarela.delete()

        # Notificar: la pasarela sale del listado.
        try:
            from users.realtime import notify_view_sync
            notify_view_sync(
                view_id='pasarela_de_pago_list',
                event_type='pasarela_removed_event',
                payload={'pasarela_id': pasarela_id, 'reason': 'hard_deleted'},
            )
        except Exception as e:
            print(f"WARNING: notify_view_sync fallo: {e}")

        return Response(
            {"message": "Registro de pasarela eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar registro de pasarela: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('pasarela_de_pago', 'view')])
def pasarela_history(request, pk):
    """Obtener el historial de cambios de un registro de pasarela"""
    try:
        pasarela = get_object_or_404(PasarelaPago.objects, pk=pk)
        history = pasarela.history.all()

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
                'observacion': h.observacion,
                'tarjeta_id': h.tarjeta_id,
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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'vendedor']), ModulePermission('pasarela_de_pago', 'edit')])
def cambiar_estado(request, pk):
    """
    Cambiar el estado de la pasarela al siguiente paso.

    Body: { "paso": "confirmacion" | "cargaro" }
    """
    try:
        pasarela = get_object_or_404(PasarelaPago.objects, pk=pk)
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

        if getattr(pasarela, campo_desde) != '1':
            return Response(
                {"error": f"No se puede avanzar a {transicion['nombre']}. El estado anterior no está activo."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if getattr(pasarela, campo_hacia) == '1':
            return Response(
                {"error": f"El registro ya está en estado {transicion['nombre']}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        setattr(pasarela, campo_desde, '0')
        setattr(pasarela, campo_hacia, '1')
        pasarela.save()

        return Response({
            "message": f"Estado actualizado a {transicion['nombre']} correctamente",
            "pasarela": serialize_pasarela(pasarela)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al cambiar estado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('pasarela_de_pago', 'edit')])
def revertir_estado(request, pk):
    """
    Revertir el estado de la pasarela al paso anterior.

    Body: { "paso": "tramite" | "confirmacion" }
    """
    try:
        pasarela = get_object_or_404(PasarelaPago.objects, pk=pk)
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

        if getattr(pasarela, campo_desde) != '1':
            return Response(
                {"error": f"No se puede revertir a {transicion['nombre']}. El estado actual no lo permite."},
                status=status.HTTP_400_BAD_REQUEST
            )

        setattr(pasarela, campo_desde, '0')
        setattr(pasarela, campo_hacia, '1')
        pasarela.save()

        return Response({
            "message": f"Estado revertido a {transicion['nombre']} correctamente",
            "pasarela": serialize_pasarela(pasarela)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al revertir estado: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
