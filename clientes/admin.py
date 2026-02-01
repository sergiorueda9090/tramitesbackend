from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(SimpleHistoryAdmin):
    list_display = ['nombre', 'telefono', 'medio_comunicacion', 'created_by', 'created_at', 'is_deleted']
    list_filter = ['medio_comunicacion', 'created_at', 'deleted_at']
    search_fields = ['nombre', 'telefono', 'direccion']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    history_list_display = ['nombre', 'telefono', 'medio_comunicacion']

    def is_deleted(self, obj):
        return obj.is_deleted
    is_deleted.boolean = True
    is_deleted.short_description = 'Eliminado'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
