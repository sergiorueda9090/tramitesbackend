# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Scope: backend-only deep dive. The project-root `../CLAUDE.md` is authoritative for the cross-cutting picture (frontend + backend + module-permission registry). Read it first; this file documents backend internals that aren't worth duplicating there.

## Common Commands

```bash
# Activate the bundled virtualenv first (in tramitesbackend/env/)
source env/Scripts/activate      # Windows Git Bash
# source env/bin/activate        # Linux/Mac

python manage.py runserver                              # HTTP only, http://localhost:8000
daphne -b 0.0.0.0 -p 8000 backend.asgi:application      # Required for WebSocket (presence)
python manage.py makemigrations [app_name]
python manage.py migrate
python manage.py createsuperuser
python manage.py shell
python manage.py test [app_name]                        # See "Tests" note below
```

**Tests**: every app's `tests.py` is the empty Django stub (3 lines). There is currently no working test suite — `manage.py test` runs to completion but finds nothing. Treat the test command as scaffolding for when tests get written.

## Architecture

### App count and registration

25 feature apps in `INSTALLED_APPS` (`backend/settings.py:43–80`). The root `CLAUDE.md` lists them; do not maintain a duplicate table here. Two recently added apps — **`plan_de_cuentas`** and **`sub_cuentas`** — were registered after the module-permission migrations, so they have **no `Module` row** yet and cannot be gated with `ModulePermission` until a new `users/migrations/0015_add_*` migration is added.

### Per-app structure

```
[app_name]/
├── models.py          # Soft-delete + django-simple-history mixed directly into each model
├── api/
│   ├── urls.py        # URL routing under /api/[app_name]/
│   ├── views.py       # Function-based views — see "View pattern" below
│   ├── permissions.py # Local RolePermission + re-export of ModulePermission
│   └── serializers.py # 1-line stub for every app EXCEPT `users` — see "Serialization" below
└── migrations/
```

### View pattern (function-based, no DRF serializers)

Views are `@api_view`-decorated functions that read `request.data` directly, validate inline, build the response dict through a local `serialize_<model>(obj)` helper, and return `Response(...)`. There is no `ModelViewSet`, no `GenericAPIView`, no `Serializer.is_valid()` machinery in 24 of the 25 apps. Implication: **adding or renaming a field requires three coordinated edits in the same app** — the model, the `serialize_<model>()` helper, and every `create_*` / `update_*` / `*_history` view that mentions the field by name. Missing any one of these silently breaks the API response shape without raising.

The standard endpoint suite per app (root CLAUDE.md documents them) maps onto these function names by convention: `list_*`, `create_*`, `get_*_by_id`, `update_*`, `delete_*` (soft), `restore_*`, `hard_delete_*`, `history_*`.

### Serialization exception: `users`

`users/api/serializers.py` (33 lines) is the **only** real DRF serializer file in the project. It defines `ModuleSerializer` and `UserModulePermissionSerializer` (both used by `users/api/views.py` for listing modules/permissions) plus a `UserSerializer` that **is currently unused dead code** — note that it imports `django.contrib.auth.models.User`, not the project's custom `users.User` (`AbstractUser` subclass at `users/models.py:15`). Don't reuse `UserSerializer` without rewriting it against `users.models.User`.

### Two-layer authorization

Every protected view must combine **both** decorators:

```python
@api_view(['POST'])
@permission_classes([
    IsAuthenticated,
    RolePermission(['admin', 'SuperAdmin', 'contador']),
    ModulePermission('clientes', 'create'),
])
def create_cliente(request):
    ...
```

- `RolePermission` (defined identically in each app's `api/permissions.py` — duplicated code, not imported from a single source) gates by `User.role` ∈ {`SuperAdmin`, `admin`, `auxiliar`, `vendedor`, `contador`, `cliente`}.
- `ModulePermission(module_code, action)` is defined in `users/api/permissions.py` and **re-exported by every other app's `api/permissions.py`** (`from users.api.permissions import ModulePermission`). It looks up `UserModulePermission(user, module__code=module_code).can_<action>`. **`SuperAdmin` bypasses this check entirely** (`users/api/permissions.py:32`).
- Module registry is seeded by `users/migrations/0006_populate_modules.py` (16 codes) and extended by migrations `0007`–`0014` (8 more codes → 24 total). Three of those 24 (`dashboard`, `reportes`, `configuracion`) are frontend-only and have no corresponding Django app. The Django apps `api_app` and `base_de_datos` have no `Module` row — they're internal/utility and not gated.

When adding a new gated feature: add a `0015_add_<code>_module.py` migration that does `Module.objects.create(name=..., code=...)`, then reference it from the view with `ModulePermission('<code>', '<action>')`. See `aplicar_permisos.md` at the project root for shell recipes.

### Common model mixins

Every domain model carries the same three concerns inline (no shared abstract base class):

- **Soft delete**: `deleted_at = models.DateTimeField(null=True, blank=True)`, plus `soft_delete()` / `restore()` methods and an `is_deleted` property.
- **History**: `history = HistoricalRecords()` from django-simple-history (`HistoryRequestMiddleware` is in `MIDDLEWARE`, so audit rows capture the request user automatically).
- **Timestamps**: `created_at` / `updated_at`.

When introducing a new model, copy all three patterns — there is no abstract base to inherit from.

### Cuatro por mil tax

Computed at the model level on financial records (`RecepcionPago`, `Devolucion`, `GastoRelacion`, etc.) based on the linked `Tarjeta.cuatro_por_mil` flag:

```python
if tarjeta.cuatro_por_mil == '1':
    cuatro_por_mil = (Decimal(valor) * Decimal('4')) / Decimal('1000')
else:
    cuatro_por_mil = Decimal('0')
```

The flag is a `CharField`, not a boolean — string `'1'` means active. The dedicated `cuatro_por_mil` app stores per-period tax aggregates separately from this per-transaction computation; don't confuse the two.

### Auth and tokens

- JWT via `djangorestframework-simplejwt`: `POST /api/token/` (issue pair), `POST /api/token/refresh/` (refresh access).
- Access token lifetime: 24 hours. Refresh token lifetime: 7 days (`backend/settings.py`).
- `USERNAME_FIELD = 'email'` (`users/models.py:22`) — log in with email, not username.

### WebSocket (presence)

- Consumer: `users/consumers.py`.
- Routing: `users/routing.py` registers the `ws/presence/` path.
- Mount point: `backend/asgi.py` uses Channels' `AuthMiddlewareStack` + `AllowedHostsOriginValidator` (the same `ALLOWED_HOSTS` env var gates WS origins as HTTP — see `settings.py:34–38`).
- Redis backing: `localhost:6379` is required when running daphne. `runserver` won't serve `ws/`; use `daphne` during local WebSocket work.

### Config and uploads

- `.env` is loaded at startup by `python-dotenv` (`load_dotenv(BASE_DIR / '.env')` at `backend/settings.py:21`). Required keys: `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`. Optional: `ALLOWED_HOSTS` (comma-separated).
- MySQL is the only supported DB (driver: `mysqlclient`). Localhost default port 3306.
- User-uploaded files land in `tramitesbackend/media/` (e.g. `media/finalizados_tramites/`). Served by Django in DEBUG mode; not configured for static-storage backends.

## Key files

- `backend/settings.py` — `INSTALLED_APPS`, JWT lifetimes, Channels layer, DB, `.env` loader
- `backend/urls.py` — root URL routing (mounts each app's `api/urls.py`)
- `backend/asgi.py` — ASGI app, WebSocket routing entry point
- `users/api/permissions.py` — canonical `ModulePermission` and `HasRolePermission` source
- `users/models.py` — `User` (custom, email-based), `Module`, `UserModulePermission`
- `requirements.txt` — Python dependencies
