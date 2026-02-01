"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path('admin/',             admin.site.urls),
    path('api/token/',         TokenObtainPairView.as_view(),   name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(),      name='token_refresh'),
    path('api/user/',          include('users.api.urls'),       name="user"),
    path('api/clientes/',      include('clientes.api.urls'),    name="clientes"),
    path('api/etiquetas/',     include('etiquetas.api.urls'),   name="etiquetas"),
    path('api/proveedores/',   include('proveedores.api.urls'),    name="proveedores"),
    path('api/cotizador/',     include('cotizador.api.urls'),   name="cotizador"),
    path('api/tarjetas/',      include('tarjetas.api.urls'),    name="tarjetas"),
    path('api/recepcion_pago/', include('recepcion_pago.api.urls'), name="recepcion_pago"),
    path('api/devoluciones/',  include('devoluciones.api.urls'), name="devoluciones"),
    path('api/cargos_no_registrados/', include('cargos_no_registrados.api.urls'), name="cargos_no_registrados"),
    path('api/ajuste_de_saldo/', include('ajuste_de_saldo.api.urls'), name="ajuste_de_saldo"),
    path('api/gastos/',             include('gastos.api.urls'),      name="gastos"),
    path('api/utilidad_ocasional/', include('utilidad_ocasional.api.urls'), name="utilidad_ocasional"),
]
