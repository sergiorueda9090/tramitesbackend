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


class HasModulePermission(BasePermission):
    """Valida permisos granulares por módulo."""
    module_code = None
    action = None  # 'view', 'create', 'edit', 'delete'

    def has_permission(self, request, view):
        user = request.user

        # SuperAdmin siempre tiene acceso total
        if getattr(user, 'role', None) == 'SuperAdmin':
            return True

        if not self.module_code or not self.action:
            return True

        # Importar aquí para evitar import circular
        from users.models import UserModulePermission

        try:
            perm = UserModulePermission.objects.get(
                user=user,
                module__code=self.module_code
            )
            return getattr(perm, f'can_{self.action}', False)
        except UserModulePermission.DoesNotExist:
            return False


def ModulePermission(module_code, action):
    """
    Retorna una clase de permiso configurada para un módulo y acción.
    module_code: código del módulo (ej: 'usuarios', 'clientes')
    action: 'view', 'create', 'edit', 'delete'
    """
    class CustomModulePermission(HasModulePermission):
        pass
    CustomModulePermission.module_code = module_code
    CustomModulePermission.action = action
    return CustomModulePermission
