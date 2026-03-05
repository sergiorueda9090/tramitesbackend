from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.

class Role(models.TextChoices):
    SUPERADMIN = 'SuperAdmin', 'Super Administrador'
    ADMIN      = 'admin', 'Administrador'
    AUXILIAR   = 'auxiliar', 'Auxiliar'
    VENDEDOR   = 'vendedor', 'Vendedor'
    CONTADOR   = 'contador', 'Contador'
    CLIENTE    = 'cliente', 'Cliente'


class User(AbstractUser):
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.ADMIN
    )
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    def __str__(self):
        return f"{self.username} ({self.role})"


class Module(models.Model):
    name = models.CharField(max_length=100)  # "Usuarios", "Clientes"
    code = models.CharField(max_length=50, unique=True)  # "usuarios", "clientes"

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UserModulePermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_permissions')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='user_permissions')
    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'module')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['module']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.module.name}"