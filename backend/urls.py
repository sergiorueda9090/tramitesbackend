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
from django.conf import settings
from django.conf.urls.static import static
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
    path('api/cotizador_rapido/', include('cotizador_rapido.api.urls'), name="cotizador_rapido"),
    path('api/correos_aleatorios/', include('correos_aleatorios.api.urls'), name="correos_aleatorios"),
    path('api/casos_especiales/', include('casos_especiales.api.urls'), name="casos_especiales"),
    path('api/tarjetas/',      include('tarjetas.api.urls'),    name="tarjetas"),
    path('api/recepcion_pago/', include('recepcion_pago.api.urls'), name="recepcion_pago"),
    path('api/devoluciones/',  include('devoluciones.api.urls'), name="devoluciones"),
    path('api/cargos_no_registrados/', include('cargos_no_registrados.api.urls'), name="cargos_no_registrados"),
    path('api/ajuste_de_saldo/', include('ajuste_de_saldo.api.urls'), name="ajuste_de_saldo"),
    path('api/gastos/',             include('gastos.api.urls'),      name="gastos"),
    path('api/tarifario_soat/',     include('tarifario_soat.api.urls'),     name="tarifario_soat"),
    path('api/utilidad_ocasional/', include('utilidad_ocasional.api.urls'), name="utilidad_ocasional"),
    path('api/tarifarios_soat/',     include('tarifario_soat.api.urls'),     name="tarifarios_soat"),
    path('api/base_de_datos/',       include('base_de_datos.api.urls'),     name="base_de_datos"),
    path('api/api_app/',             include('api_app.api.urls'),           name="api_app"),
    path('api/tramites/',            include('tramites.api.urls'),          name="tramites"),
    path('api/pasarela_de_pago/',    include('pasarela_de_pago.api.urls'),  name="pasarela_de_pago"),
    path('api/finalizados_tramites/', include('finalizados_tramites.api.urls'), name="finalizados_tramites"),
    path('api/gastos_categoria/',     include('gastos_categoria.api.urls'),     name="gastos_categoria"),
    path('api/cuatro_por_mil/',       include('cuatro_por_mil.api.urls'),       name="cuatro_por_mil"),
    path('api/utilidades/',           include('utilidades.api.urls'),           name="utilidades"),
    path('api/computador_ips/',       include('computador_ips.api.urls'),       name="computador_ips"),
    path('api/plan_de_cuentas/',      include('plan_de_cuentas.api.urls'),      name="plan_de_cuentas"),
    path('api/sub_cuentas/',          include('sub_cuentas.api.urls'),          name="sub_cuentas"),
    path('api/movimiento_contable/',  include('movimiento_contable.api.urls'),  name="movimiento_contable"),
]

# En dev, servir archivos de MEDIA_ROOT vía Django.
# Producción: configurar nginx/cloudfront/S3 para servir /media/.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
