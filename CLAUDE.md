# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Django REST Framework backend for managing mobility-related financial transactions, client management, and operational workflows. Built with Django 4.2, JWT authentication, WebSocket support via Channels, and MySQL database.

## Common Commands

```bash
# Development server
python manage.py runserver

# ASGI server with WebSocket support
daphne -b 0.0.0.0 -p 8000 backend.asgi:application

# Database migrations
python manage.py makemigrations [app_name]
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Django shell
python manage.py shell
```

## Architecture

### App Structure Pattern

All 12 apps follow this consistent structure:
```
[app_name]/
├── models.py          # Django models with soft-delete & history
├── api/
│   ├── urls.py        # URL routing
│   ├── views.py       # Function-based API views
│   ├── permissions.py # RolePermission class
│   └── serializers.py # (optional)
└── migrations/
```

### Core Apps

| App | Purpose | Key Models |
|-----|---------|------------|
| `users` | Authentication, roles, WebSocket presence | `User` (custom, email-based) |
| `clientes` | Client management | `Cliente`, `PrecioCliente` |
| `tarjetas` | Payment cards | `Tarjeta` (cuatro_por_mil flag) |
| `recepcion_pago` | Payment collection | `RecepcionPago` |
| `devoluciones` | Refunds/returns | `Devolucion` |
| `gastos` | Expenses | `Gasto`, `GastoRelacion` |
| `cargos_no_registrados` | Unregistered charges | `CargoNoRegistrado` |
| `ajuste_de_saldo` | Balance adjustments | `AjusteDeSaldo` |
| `cotizador` | Quotations | `Cotizador`, `CotizadorPagos` |
| `etiquetas` | Tags/labels | `Etiqueta` |
| `proveedores` | Suppliers | `Proveedor` |
| `utilidad_ocasional` | Occasional income | `UtilidadOcasional` |

### Common Model Patterns

All models implement:
- **Soft delete**: `deleted_at` field with `soft_delete()`, `restore()`, `is_deleted` property
- **Audit trail**: `history = HistoricalRecords()` from django-simple-history
- **Timestamps**: `created_at`, `updated_at`

### Cuatro Por Mil Calculation

Financial models (RecepcionPago, Devolucion, GastoRelacion, etc.) calculate tax based on card status:
```python
def calcular_cuatro_por_mil(valor, tarjeta):
    if tarjeta.cuatro_por_mil == '1':  # Active
        return (Decimal(valor) * Decimal('4')) / Decimal('1000')
    return Decimal('0')  # Exempt
```

### API View Pattern

Function-based views with consistent structure:
```python
@api_view(['POST'])
@permission_classes([IsAuthenticated, RolePermission(['admin', 'SuperAdmin', 'contador'])])
def create_something(request):
    # Validate required fields
    # Validate foreign keys exist and not deleted
    # Calculate derived fields (cuatro_por_mil, total)
    # Create object
    # Return serialized response
```

### User Roles

Defined in `users/models.py`:
- `SuperAdmin`, `admin`, `auxiliar`, `vendedor`, `contador`, `cliente`

Use `RolePermission(['role1', 'role2'])` in views to restrict access.

### API URL Pattern

All apps expose endpoints at `/api/[app_name]/`:
- `GET /list/` - Paginated list with filters
- `POST /create/` - Create new
- `GET /<id>/` - Get by ID
- `PUT /<id>/update/` - Update
- `DELETE /<id>/delete/` - Soft delete
- `POST /<id>/restore/` - Restore deleted
- `DELETE /<id>/hard-delete/` - Permanent delete
- `GET /<id>/history/` - Change history

### Authentication

JWT via `djangorestframework-simplejwt`:
- `POST /api/token/` - Get token pair
- `POST /api/token/refresh/` - Refresh access token
- Access token: 24 hours, Refresh token: 7 days

### WebSocket

Presence tracking at `/ws/presence/` using Channels + Redis.
Consumer in `users/consumers.py`.

## Database

MySQL configured via `.env`:
- Host: localhost:3306
- Database: movilidad

## Key Configuration Files

- `backend/settings.py` - Django settings, JWT config, Channels
- `backend/urls.py` - Root URL routing
- `backend/asgi.py` - ASGI with WebSocket routing
- `requirements.txt` - Python dependencies
- `.env` - Database credentials
