from rest_framework.permissions import BasePermission

class HasRolePermission(BasePermission):
    allowed_roles = None

    def has_permission(self, request, view):
        # Si no hay restricción, todos los autenticados pueden acceder
        if not self.allowed_roles:
            return True

        user_role = getattr(request.user, 'role', None)
        return user_role in self.allowed_roles


# Esta función devuelve una clase configurada
def RolePermission(roles):
    class CustomRolePermission(HasRolePermission):
        allowed_roles = roles
    return CustomRolePermission
2
