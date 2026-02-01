from rest_framework.permissions import BasePermission


class HasRolePermission(BasePermission):
    allowed_roles = None

    def has_permission(self, request, view):
        if not self.allowed_roles:
            return True
        user_role = getattr(request.user, 'role', None)
        return user_role in self.allowed_roles


def RolePermission(roles):
    """Función que devuelve una clase de permiso configurada con los roles permitidos"""
    class CustomRolePermission(HasRolePermission):
        allowed_roles = roles
    return CustomRolePermission
