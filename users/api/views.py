from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.contrib.auth.hashers import make_password
from django.db import DatabaseError
from users.models import User
from .permissions import RolePermission

from django.db.models import Q # Importar Q para búsquedas complejas
from datetime import datetime  # Importar datetime para manejar fechas

# Obtener usuario autenticado
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    try:
        user = request.user
        data = {
            "id"          : user.id,
            "username"    : user.username,
            "first_name"  : user.first_name,
            "last_name"   : user.last_name,
            "email"       : user.email,
            "role"        :"",
            "is_active"   : user.is_active,
            "is_staff"    : user.is_staff,
            "is_superuser": user.is_superuser,
            "last_login"  : user.last_login,
            "date_joined" : user.date_joined,
        }
        return Response(data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error retrieving user data: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

#Crear usuario
@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin'])])
def create_user(request):
    try:
        username    = request.data.get('username')
        password    = request.data.get('password')
        email       = request.data.get('email', '')
        first_name  = request.data.get('first_name', '')
        last_name   = request.data.get('last_name', '')
        role        = request.data.get('role', 'admin')
        is_active   = request.data.get('is_active', True)

        if is_active in [0, '0', 'false', 'False', False]:
            is_active = False
        else:
            is_active = True

        if not username or not password:
            return Response(
                {"error": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "Username already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=is_active,
            password=make_password(password)
        )

        data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
        }
        return Response(data, status=status.HTTP_201_CREATED)

    except DatabaseError as e:
        return Response(
            {"error": f"Database error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {"error": f"Unexpected error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin'])])
def list_users(request):
    try:
        # 1. Obtener todos los usuarios como un queryset
        users = User.objects.all()

        # 2. Aplicar FILTROS
        
        # --- Filtro de Buscador (Search) ---
        search_query = request.query_params.get('search', None)
        if search_query:
            # Filtra por username, email, first_name o last_name
            users = users.filter(
                Q(username__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query)
            )

        # --- Filtro por Rol (Role) ---
        role_filter = request.query_params.get('role', None)
        if role_filter:
            # Filtra usuarios por rol específico
            users = users.filter(role=role_filter)
            print(f"Filtrando por rol: {role_filter}")

        # --- Filtro por Estado (Status/is_active) ---
        status_filter = request.query_params.get('is_active', None)
        if status_filter is not None and status_filter != '':
            # Convertir '1' a True y '0' a False
            is_active_bool = status_filter == '1'
            users = users.filter(is_active=is_active_bool)  

        # --- Filtros de Fecha de Inicio y Fecha de Fin (Date Range) ---
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        if start_date_str:
            try:
                # Convertir la cadena a objeto datetime.date
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                # Filtra usuarios cuya fecha de unión sea mayor o igual a la fecha de inicio
                users = users.filter(date_joined__gte=start_date)
                print(f"Filtrando desde fecha: {start_date}")
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de inicio debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date_str:
            try:
                # Convertir la cadena a objeto datetime.date
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                # Filtra usuarios cuya fecha de unión sea menor o igual a la fecha de fin
                # Agregamos un día completo para incluir todo el día final
                from datetime import datetime, timedelta
                end_date_inclusive = datetime.combine(end_date, datetime.max.time())
                users = users.filter(date_joined__lte=end_date_inclusive)
                print(f"Filtrando hasta fecha: {end_date}")
            except ValueError:
                return Response(
                    {"error": "El formato de la fecha de fin debe ser YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 3. Contar total de usuarios después de aplicar filtros (antes de paginar)
        total_count = users.count()
        print(f"Total de usuarios después de filtros: {total_count}")
                
        # 4. Seleccionar los campos a devolver (values) y Ordenar
        # Se ordena por 'id' para asegurar un orden consistente antes de paginar
        users = users.order_by('-id').values(  # Cambiado a '-id' para mostrar los más recientes primero
            'id', 
            'username', 
            'email', 
            'first_name', 
            'last_name', 
            'role', 
            'is_active', 
            'date_joined'
        )

        # 5. Aplicar paginación manualmente
        page_size_param = request.query_params.get('page_size', 10)
        
        # Asegurarse de que page_size es un entero válido
        try:
            page_size_int = int(page_size_param)
        except (ValueError, TypeError):
            page_size_int = 10
        
        print(f"Tamaño de página solicitado: {page_size_int}")
        
        paginator = PageNumberPagination()
        paginator.page_size = page_size_int
        paginated_users = paginator.paginate_queryset(users, request)

        # Imprimir información de paginación
        print(f"Página actual: {request.query_params.get('page', 1)}")
        print(f"Usuarios en esta página: {len(paginated_users) if paginated_users else 0}")

        return paginator.get_paginated_response(paginated_users)

    except Exception as e:
        print(f"Error en list_users: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response(
            {"error": f"Error fetching users: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Obtener un usuario por ID (admin o contador)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin'])])
def get_user(request, pk):
    try:
        user = get_object_or_404(User, pk=pk)
        data = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
        }
        return Response(data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Error retrieving user: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Actualizar usuario (solo admin)
@api_view(['PUT'])
@permission_classes([IsAuthenticated, RolePermission(['admin'])])
def update_user(request, pk):
    try:
        user = get_object_or_404(User, pk=pk)
        user.username = request.data.get('username', user.username)
        user.first_name = request.data.get('first_name', user.first_name)
        user.last_name = request.data.get('last_name', user.last_name)
        user.email = request.data.get('email', user.email)
        user.role = request.data.get('role', user.role)
        password = request.data.get('password')
        is_active = request.data.get('is_active', user.is_active)
        #  AGREGAR ESTA LÍNEA - Actualizar is_active
        if is_active in [0, '0', 'false', 'False', False]:
            is_active = False
        else:
            is_active = True
        user.is_active = is_active

        if password:
            user.password = make_password(password)

        user.save()

        data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
        }
        return Response(data, status=status.HTTP_200_OK)

    except DatabaseError as e:
        return Response(
            {"error": f"Database error while updating user: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {"error": f"Unexpected error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Eliminar usuario (solo admin)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated, RolePermission(['admin'])])
def delete_user(request, pk):
    try:
        user = get_object_or_404(User, pk=pk)
        user.delete()
        return Response(
            {"message": "User deleted successfully"},
            status=status.HTTP_204_NO_CONTENT
        )
    except Exception as e:
        return Response(
            {"error": f"Error deleting user: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, RolePermission(['admin'])])
def toggle_status(request, pk):
    try:
        if pk is None:
            return Response(
                {"error": "User ID (pk) is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = get_object_or_404(User, pk=pk)
        user.is_active = not user.is_active
        user.save()

        data = {
            "id": user.id,
            "username": user.username,
            "is_active": user.is_active,
        }
        return Response(data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Error toggling user status: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )