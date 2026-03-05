from django.contrib import admin
from .models import Module, UserModulePermission


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')
    search_fields = ('name', 'code')


@admin.register(UserModulePermission)
class UserModulePermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'module', 'can_view', 'can_create', 'can_edit', 'can_delete')
    list_filter = ('module', 'can_view', 'can_create', 'can_edit', 'can_delete')
    search_fields = ('user__username', 'module__name')
