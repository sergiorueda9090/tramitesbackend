import json
import ast
from decimal import Decimal, InvalidOperation

from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import DatabaseError
from django.db.models import Q, Count, Prefetch
from django.utils import timezone
from datetime import datetime, timedelta

from clientes.models import Cliente, MedioComunicacion, TipoCliente, PrecioCliente
from sub_cuentas.models import SubCuenta
from tarifario_soat.models import TarifarioSoat
from .permissions import RolePermission, ModulePermission


def _validar_comision(comision_raw):
    """Valida y normaliza la comision (monto en COP). Obligatoria y >= 0.

    Devuelve (Decimal, None) si es valida, o (None, mensaje) si no lo es.
    """
    if comision_raw is None or comision_raw == '':
        return None, "La comision es requerida."
    try:
        comision = Decimal(str(comision_raw))
    except (InvalidOperation, ValueError, TypeError):
        return None, "La comision debe ser un valor numerico."
    if comision < 0:
        return None, "La comision no puede ser negativa."
    return comision, None


def _validar_codigo_tarifa(codigo_tarifa_id):
    """Valida codigo_tarifa (FK a TarifarioSoat): obligatoria + no eliminada."""
    if not codigo_tarifa_id:
        return None, "El codigo_tarifa es requerido."
    try:
        tarifa = TarifarioSoat.objects.get(pk=codigo_tarifa_id)
    except TarifarioSoat.DoesNotExist:
        return None, f"El codigo de tarifa con id {codigo_tarifa_id} no existe."
    if tarifa.is_deleted:
        return None, f"El codigo de tarifa {tarifa.codigo_tarifa} esta eliminado."
    return tarifa, None


def _validar_codigo_no_duplicado(cliente, codigo_tarifa_id, excluir_precio_pk=None):
    """Verifica que el cliente no tenga otro PrecioCliente activo con el mismo codigo_tarifa.

    Devuelve (True, None) si no hay duplicado, o (False, mensaje) si lo hay.
    Solo considera precios NO eliminados (soft-delete permite reusar codigos viejos).
    """
    qs = PrecioCliente.objects.filter(
        cliente=cliente,
        codigo_tarifa_id=codigo_tarifa_id,
        deleted_at__isnull=True,
    )
    if excluir_precio_pk is not None:
        qs = qs.exclude(pk=excluir_precio_pk)
    existente = qs.select_related('codigo_tarifa').first()
    if existente:
        codigo_str = existente.codigo_tarifa.codigo_tarifa if existente.codigo_tarifa else codigo_tarifa_id
        return False, (
            f"El cliente ya tiene el codigo de tarifa '{codigo_str}' asignado "
            f"(precio id {existente.id})."
        )
    return True, None


def _validar_sub_cuenta(sub_cuenta_id):
    """Valida sub_cuenta obligatoria + no eliminada. NO se exige UNIQUE (varios
    clientes pueden compartir la misma sub-cuenta contable)."""
    if not sub_cuenta_id:
        return None, Response({"error": "La sub-cuenta es obligatoria."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        sub = SubCuenta.objects.get(pk=sub_cuenta_id)
    except SubCuenta.DoesNotExist:
        return None, Response({"error": "La sub-cuenta especificada no existe."}, status=status.HTTP_404_NOT_FOUND)
    if sub.is_deleted:
        return None, Response({"error": "La sub-cuenta especificada esta eliminada."}, status=status.HTTP_400_BAD_REQUEST)
    return sub, None


def serialize_precio(precio):
    """Convierte un objeto PrecioCliente a diccionario"""
    return {
        'id': precio.id,
        'comision': str(precio.comision) if precio.comision is not None else None,
        'codigo_tarifa': precio.codigo_tarifa_id,
        'codigo_tarifa_codigo': precio.codigo_tarifa.codigo_tarifa if precio.codigo_tarifa else None,
        'codigo_tarifa_descripcion': precio.codigo_tarifa.descripcion if precio.codigo_tarifa else None,
        'codigo_tarifa_valor': str(precio.codigo_tarifa.valor) if precio.codigo_tarifa else None,
        'created_at': precio.created_at,
        'updated_at': precio.updated_at,
    }


def serialize_cliente(cliente, include_precios=True, include_precios_info=False, precios_prefetched=False):
    """Convierte un objeto Cliente a diccionario"""
    data = {
        'id': cliente.id,
        'color': cliente.color,
        'nombre': cliente.nombre,
        'telefono': cliente.telefono,
        'email': cliente.email,
        'direccion': cliente.direccion,
        'usuario': cliente.usuario_id,
        'usuario_name': f"{cliente.usuario.first_name} {cliente.usuario.last_name}".strip() if cliente.usuario else None,
        'tipo_cliente': cliente.tipo_cliente,
        'tipo_cliente_display': cliente.get_tipo_cliente_display(),
        'medio_comunicacion': cliente.medio_comunicacion,
        'medio_comunicacion_display': cliente.get_medio_comunicacion_display(),
        'created_by': cliente.created_by_id,
        'created_by_name': f"{cliente.created_by.first_name} {cliente.created_by.last_name}".strip() if cliente.created_by else None,
        'sub_cuenta': cliente.sub_cuenta_id,
        'sub_cuenta_codigo': cliente.sub_cuenta.codigo if cliente.sub_cuenta else None,
        'sub_cuenta_nombre': cliente.sub_cuenta.nombre_sub_cuenta if cliente.sub_cuenta else None,
        'created_at': cliente.created_at,
        'updated_at': cliente.updated_at,
        'deleted_at': cliente.deleted_at,
    }
    if include_precios:
        # Si los precios ya están prefetcheados (filtrados), usar .all()
        if precios_prefetched:
            data['precios'] = [serialize_precio(p) for p in cliente.precios.all()]
        else:
            data['precios'] = [serialize_precio(p) for p in cliente.precios.filter(deleted_at__isnull=True)]
    if include_precios_info:
        # Usar la anotación si está disponible, sino calcular
        if hasattr(cliente, 'precios_count'):
            data['precios_count'] = cliente.precios_count
            data['tiene_precios'] = cliente.precios_count > 0
        else:
            count = cliente.precios.filter(deleted_at__isnull=True).count()
            data['precios_count'] = count
            data['tiene_precios'] = count > 0
    return data


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('clientes', 'create')])
def create_client(request):
    """Crear un nuevo cliente con sus precios"""
    try:
        nombre = request.data.get('nombre')
        if not nombre:
            return Response(
                {"error": "El nombre es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        color = request.data.get('color', '#1976d2')
        telefono = request.data.get('telefono', '')
        email = request.data.get('email', '') or None
        direccion = request.data.get('direccion', '')
        tipo_cliente = request.data.get('tipo_cliente', TipoCliente.PARTICULAR)
        medio_comunicacion = request.data.get('medio_comunicacion', MedioComunicacion.EMAIL)
        precios_data = request.data.get('precios', [])

        # Si precios_data viene como string (multipart/form-data), parsearlo
        if isinstance(precios_data, str):
            try:
                # Intentar primero con JSON estándar (comillas dobles)
                precios_data = json.loads(precios_data)
            except json.JSONDecodeError:
                try:
                    # Si falla, intentar con sintaxis Python (comillas simples)
                    precios_data = ast.literal_eval(precios_data)
                except (ValueError, SyntaxError):
                    return Response(
                        {"error": "El formato de precios es inválido."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

        # Validar tipo_cliente
        if tipo_cliente not in [c[0] for c in TipoCliente.choices]:
            return Response(
                {"error": f"Tipo de cliente debe ser: {', '.join([c[0] for c in TipoCliente.choices])}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar medio_comunicacion
        if medio_comunicacion not in [c[0] for c in MedioComunicacion.choices]:
            return Response(
                {"error": f"Medio de comunicacion debe ser: {', '.join([c[0] for c in MedioComunicacion.choices])}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        sub_cuenta, error_response = _validar_sub_cuenta(request.data.get('sub_cuenta'))
        if error_response:
            return error_response

        cliente = Cliente.objects.create(
            color=color,
            nombre=nombre,
            telefono=telefono,
            email=email,
            direccion=direccion,
            tipo_cliente=tipo_cliente,
            usuario=request.user,
            medio_comunicacion=medio_comunicacion,
            created_by=request.user,
            sub_cuenta=sub_cuenta,
        )

        # Crear precios asociados al cliente — validar duplicados intra-batch y vs BD
        codigos_vistos = set()
        for precio_data in precios_data:
            codigo_tarifa_id = precio_data.get('codigo_tarifa')

            if codigo_tarifa_id:
                tarifa, error_msg = _validar_codigo_tarifa(codigo_tarifa_id)
                if error_msg:
                    return Response({"error": f"Precio (tarifa {codigo_tarifa_id}): {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)
                comision, error_msg = _validar_comision(precio_data.get('comision'))
                if error_msg:
                    return Response({"error": f"Precio (tarifa {tarifa.codigo_tarifa}): {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)
                # Duplicado dentro del propio batch
                if codigo_tarifa_id in codigos_vistos:
                    return Response(
                        {"error": f"El codigo de tarifa '{tarifa.codigo_tarifa}' esta duplicado en la lista enviada."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                codigos_vistos.add(codigo_tarifa_id)
                # Duplicado vs BD (siempre nuevo cliente aqui, pero validacion defensiva)
                ok, err = _validar_codigo_no_duplicado(cliente, codigo_tarifa_id)
                if not ok:
                    return Response({"error": f"Precio (tarifa {tarifa.codigo_tarifa}): {err}"}, status=status.HTTP_400_BAD_REQUEST)
                PrecioCliente.objects.create(
                    cliente=cliente,
                    codigo_tarifa=tarifa,
                    comision=comision,
                )

        return Response(serialize_cliente(cliente), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'auxiliar', 'vendedor']), ModulePermission('clientes', 'view')])
def list_clients(request):
    """Listar clientes con filtros y paginación"""
    try:
        clientes = Cliente.objects.select_related('usuario', 'created_by', 'sub_cuenta').prefetch_related(
            Prefetch('precios', queryset=PrecioCliente.objects.select_related('codigo_tarifa').filter(deleted_at__isnull=True))
        ).annotate(
            precios_count=Count('precios', filter=Q(precios__deleted_at__isnull=True))
        )

        # Filtro de búsqueda
        search_query = request.query_params.get('search', None)
        if search_query:
            clientes = clientes.filter(
                Q(nombre__icontains=search_query) |
                Q(telefono__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(direccion__icontains=search_query)
            )

        # Filtro por medio de comunicación
        medio_filter = request.query_params.get('medio_comunicacion', None)
        if medio_filter:
            clientes = clientes.filter(medio_comunicacion=medio_filter)

        # Filtro por tipo de cliente
        tipo_cliente_filter = request.query_params.get('tipo_cliente', None)
        if tipo_cliente_filter:
            clientes = clientes.filter(tipo_cliente=tipo_cliente_filter)

        # Filtro por usuario asignado
        usuario_filter = request.query_params.get('usuario', None)
        if usuario_filter:
            clientes = clientes.filter(usuario_id=usuario_filter)

        # Filtro por fecha de creación
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                clientes = clientes.filter(created_at__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                clientes = clientes.filter(created_at__lte=end_date_inclusive)
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filtro para incluir eliminados
        include_deleted = request.query_params.get('include_deleted', None)
        if include_deleted != '1':
            clientes = clientes.filter(deleted_at__isnull=True)

        # Ordenar
        clientes = clientes.order_by('-created_at')

        # Paginación
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10

        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_clientes = paginator.paginate_queryset(clientes, request)

        data = [serialize_cliente(c, include_precios=True, include_precios_info=True, precios_prefetched=True) for c in paginated_clientes]
        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener clientes: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'auxiliar', 'vendedor']), ModulePermission('clientes', 'view')])
def top_clients(request):
    """Top N clientes mas consultados (frecuencia segun RegistroVehiculo del cotizador)."""
    try:
        try:
            limit = int(request.query_params.get('limit', 10))
        except (ValueError, TypeError):
            limit = 10
        limit = max(1, min(limit, 50))

        try:
            days = int(request.query_params.get('days', 90))
        except (ValueError, TypeError):
            days = 90

        registros_filter = Q(registros_vehiculo__deleted_at__isnull=True)
        if days > 0:
            cutoff = timezone.now() - timedelta(days=days)
            registros_filter &= Q(registros_vehiculo__created_at__gte=cutoff)

        clientes = (
            Cliente.objects
            .filter(deleted_at__isnull=True)
            .annotate(consultas=Count('registros_vehiculo', filter=registros_filter))
            .filter(consultas__gt=0)
            .order_by('-consultas', '-updated_at')[:limit]
        )

        data = [{
            'id': c.id,
            'color': c.color,
            'nombre': c.nombre,
            'telefono': c.telefono,
            'email': c.email,
            'tipo_cliente': c.tipo_cliente,
            'tipo_cliente_display': c.get_tipo_cliente_display(),
            'consultas': c.consultas,
        } for c in clientes]

        return Response(data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener clientes top: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'auxiliar', 'vendedor']), ModulePermission('clientes', 'view')])
def get_client(request, pk):
    """Obtener un cliente por ID"""
    try:
        cliente = get_object_or_404(Cliente.objects.select_related('usuario', 'created_by', 'sub_cuenta'), pk=pk)
        return Response(serialize_cliente(cliente), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al obtener cliente: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('clientes', 'edit')])
def update_client(request, pk):
    """Actualizar un cliente"""
    try:
        cliente           = get_object_or_404(Cliente.objects, pk=pk)

        cliente.nombre    = request.data.get('nombre', cliente.nombre)
        cliente.telefono  = request.data.get('telefono', cliente.telefono)
        if 'email' in request.data:
            cliente.email = request.data.get('email') or None
        cliente.direccion = request.data.get('direccion', cliente.direccion)
        cliente.color     = request.data.get('color', cliente.color)

        tipo_cliente = request.data.get('tipo_cliente', cliente.tipo_cliente)
        if tipo_cliente not in [c[0] for c in TipoCliente.choices]:
            return Response(
                {"error": f"Tipo de cliente debe ser: {', '.join([c[0] for c in TipoCliente.choices])}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        cliente.tipo_cliente = tipo_cliente

        medio_comunicacion = request.data.get('medio_comunicacion', cliente.medio_comunicacion)
        if medio_comunicacion not in [c[0] for c in MedioComunicacion.choices]:
            return Response(
                {"error": f"Medio de comunicación debe ser: {', '.join([c[0] for c in MedioComunicacion.choices])}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        cliente.medio_comunicacion = medio_comunicacion

        # Sub-cuenta: si llega, validar y actualizar (obligatoria; no se puede vaciar)
        if 'sub_cuenta' in request.data:
            sub_cuenta_id = request.data.get('sub_cuenta')
            if not sub_cuenta_id:
                return Response(
                    {"error": "La sub-cuenta es obligatoria; no puede quedar vacía."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sub_cuenta, error_response = _validar_sub_cuenta(sub_cuenta_id)
            if error_response:
                return error_response
            cliente.sub_cuenta = sub_cuenta

        cliente.save()

        # Manejar precios si se envían
        precios_data = request.data.get('precios', None)
        if precios_data is not None:
            # Si precios_data viene como string (multipart/form-data), parsearlo
            if isinstance(precios_data, str):
                try:
                    precios_data = json.loads(precios_data)
                except json.JSONDecodeError:
                    try:
                        precios_data = ast.literal_eval(precios_data)
                    except (ValueError, SyntaxError):
                        return Response(
                            {"error": "El formato de precios es inválido."},
                            status=status.HTTP_400_BAD_REQUEST
                        )

            # Validar duplicados intra-batch antes de procesar
            codigos_batch = {}  # codigo_tarifa_id -> posicion
            for idx, precio_data in enumerate(precios_data):
                ct_id = precio_data.get('codigo_tarifa')
                if ct_id:
                    if ct_id in codigos_batch:
                        prev_idx = codigos_batch[ct_id]
                        return Response(
                            {"error": f"El codigo de tarifa esta duplicado en la lista enviada (posiciones {prev_idx + 1} y {idx + 1}). Cada cliente debe tener codigos unicos."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    codigos_batch[ct_id] = idx

            for precio_data in precios_data:
                precio_id        = precio_data.get('id')
                codigo_tarifa_id = precio_data.get('codigo_tarifa')

                if precio_id:
                    # Actualizar precio existente
                    try:
                        precio = PrecioCliente.objects.get(pk=precio_id, cliente=cliente)
                        if 'comision' in precio_data:
                            comision, error_msg = _validar_comision(precio_data.get('comision'))
                            if error_msg:
                                return Response({"error": f"Precio #{precio_id}: {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)
                            precio.comision = comision
                        if codigo_tarifa_id:
                            tarifa, error_msg = _validar_codigo_tarifa(codigo_tarifa_id)
                            if error_msg:
                                return Response({"error": f"Precio #{precio_id}: {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)
                            # Validar no duplicado contra otros precios del cliente (excluyendo este mismo)
                            ok, err = _validar_codigo_no_duplicado(cliente, codigo_tarifa_id, excluir_precio_pk=precio.pk)
                            if not ok:
                                return Response({"error": f"Precio #{precio_id}: {err}"}, status=status.HTTP_400_BAD_REQUEST)
                            precio.codigo_tarifa = tarifa
                        precio.save()
                    except PrecioCliente.DoesNotExist:
                        pass
                else:
                    # Crear nuevo precio
                    if codigo_tarifa_id:
                        tarifa, error_msg = _validar_codigo_tarifa(codigo_tarifa_id)
                        if error_msg:
                            return Response({"error": f"Precio (tarifa {codigo_tarifa_id}): {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)
                        comision, error_msg = _validar_comision(precio_data.get('comision'))
                        if error_msg:
                            return Response({"error": f"Precio (tarifa {tarifa.codigo_tarifa}): {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)
                        # Validar no duplicado contra precios existentes del cliente
                        ok, err = _validar_codigo_no_duplicado(cliente, codigo_tarifa_id)
                        if not ok:
                            return Response({"error": f"Precio (tarifa {tarifa.codigo_tarifa}): {err}"}, status=status.HTTP_400_BAD_REQUEST)
                        PrecioCliente.objects.create(
                            cliente=cliente,
                            codigo_tarifa=tarifa,
                            comision=comision,
                        )

        return Response(serialize_cliente(cliente), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('clientes', 'delete')])
def delete_client(request, pk):
    """Eliminar un cliente (soft delete)"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        cliente.soft_delete()
        return Response(
            {"message": "Cliente eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cliente: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('clientes', 'delete')])
def restore_client(request, pk):
    """Restaurar un cliente eliminado"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        if not cliente.is_deleted:
            return Response(
                {"error": "El cliente no está eliminado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        cliente.restore()
        return Response(serialize_cliente(cliente), status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error al restaurar cliente: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('clientes', 'delete')])
def hard_delete_client(request, pk):
    """Eliminar permanentemente un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        cliente.delete()
        return Response(
            {"message": "Cliente eliminado permanentemente"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar cliente: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('clientes', 'view')])
def client_history(request, pk):
    """Obtener el historial de cambios de un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        history = cliente.history.all()

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
                    'username': h.history_user.username,
                    'name': f"{h.history_user.first_name} {h.history_user.last_name}".strip()
                } if h.history_user else None,
                'nombre': h.nombre,
                'telefono': h.telefono,
                'email': h.email,
                'direccion': h.direccion,
                'color': h.color,
                'tipo_cliente': h.tipo_cliente,
                'medio_comunicacion': h.medio_comunicacion,
            })

        return paginator.get_paginated_response(data)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener historial: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== PRECIOS CLIENTE ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('clientes', 'create')])
def add_precio_cliente(request, pk):
    """Agregar un precio a un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)

        codigo_tarifa_id = request.data.get('codigo_tarifa')

        tarifa, error_msg = _validar_codigo_tarifa(codigo_tarifa_id)
        if error_msg:
            return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)

        comision, error_msg = _validar_comision(request.data.get('comision'))
        if error_msg:
            return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)

        ok, err = _validar_codigo_no_duplicado(cliente, codigo_tarifa_id)
        if not ok:
            return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

        precio = PrecioCliente.objects.create(
            cliente=cliente,
            codigo_tarifa=tarifa,
            comision=comision,
        )

        return Response(serialize_precio(precio), status=status.HTTP_201_CREATED)

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
@permission_classes([IsAuthenticated, ModulePermission('clientes', 'view')])
def list_precios_cliente(request, pk):
    """Listar precios de un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        precios = cliente.precios.select_related('codigo_tarifa').filter(deleted_at__isnull=True)

        data = [serialize_precio(p) for p in precios]
        return Response(data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error al obtener precios: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('clientes', 'edit')])
def update_precio_cliente(request, pk, precio_pk):
    """Actualizar un precio de un cliente"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        precio  = get_object_or_404(PrecioCliente.objects.filter(cliente=cliente), pk=precio_pk)

        if 'comision' in request.data:
            comision, error_msg = _validar_comision(request.data.get('comision'))
            if error_msg:
                return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
            precio.comision = comision

        if 'codigo_tarifa' in request.data:
            codigo_tarifa_id = request.data.get('codigo_tarifa')
            tarifa, error_msg = _validar_codigo_tarifa(codigo_tarifa_id)
            if error_msg:
                return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
            ok, err = _validar_codigo_no_duplicado(cliente, codigo_tarifa_id, excluir_precio_pk=precio.pk)
            if not ok:
                return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)
            precio.codigo_tarifa = tarifa

        precio.save()

        return Response(serialize_precio(precio), status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin']), ModulePermission('clientes', 'delete')])
def delete_precio_cliente(request, pk, precio_pk):
    """Eliminar un precio de un cliente (soft delete)"""
    try:
        cliente = get_object_or_404(Cliente.objects, pk=pk)
        precio = get_object_or_404(PrecioCliente.objects.filter(cliente=cliente), pk=precio_pk)

        from django.utils import timezone
        precio.deleted_at = timezone.now()
        precio.save()

        return Response(
            {"message": "Precio eliminado correctamente"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"Error al eliminar precio: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
