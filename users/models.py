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