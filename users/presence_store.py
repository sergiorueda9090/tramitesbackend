"""
Capa de almacenamiento de presencia en Redis.

Estructura de datos:
- Hash `presence:online`         -> {user_id: json(user_data)}
- Set  `presence:user:<id>:channels` -> {channel_name1, channel_name2, ...}

Multi-pestania: un mismo user_id puede tener varios canales activos. Solo
se considera "desconectado" cuando el set queda vacio.

TTL: cada entrada del hash expira automaticamente. El cliente debe
refrescar via ping (touch).
"""
import json
import os

from redis import asyncio as aioredis

# Reutilizamos host/puerto del CHANNEL_LAYERS (settings.py).
# Configurable via env var por si en otro entorno cambia.
_REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')
_REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
_REDIS_DB = int(os.getenv('REDIS_DB', '0'))

_HASH_KEY = 'presence:online'
_USER_CHANNELS_KEY = 'presence:user:{user_id}:channels'

# Presencia a nivel de celda (modulo + fila + columna).
# Hash por vista: {user_id: json({row_id, column, user_data, ts})}
_VIEW_CELLS_KEY = 'presence:view:{view_id}:cells'


def _ttl_seconds():
    """Lee el TTL desde settings (con fallback) en cada llamada para que sea testeable."""
    try:
        from django.conf import settings
        return int(getattr(settings, 'PRESENCE_TTL_SECONDS', 60))
    except Exception:
        return 60

_client = None


def _get_client():
    """Cliente Redis async lazy/singleton."""
    global _client
    if _client is None:
        _client = aioredis.Redis(
            host=_REDIS_HOST,
            port=_REDIS_PORT,
            db=_REDIS_DB,
            decode_responses=True,
        )
    return _client


async def add_channel(user_id, channel_name, user_data):
    """
    Registra que un canal pertenece a user_id.
    Devuelve True si es la primera conexion del usuario (alguien que entra
    "por primera vez"), False si ya tenia otra pestania abierta.
    """
    user_id = str(user_id)
    r = _get_client()
    set_key = _USER_CHANNELS_KEY.format(user_id=user_id)

    # ¿Ya habia canales para este usuario? -> no es el primer ingreso
    existing = await r.scard(set_key)
    is_first = existing == 0

    pipe = r.pipeline()
    pipe.sadd(set_key, channel_name)
    pipe.expire(set_key, _ttl_seconds())
    pipe.hset(_HASH_KEY, user_id, json.dumps(user_data))
    await pipe.execute()

    return is_first


async def remove_channel(user_id, channel_name):
    """
    Quita un canal del set del usuario. Si el set queda vacio, borra al
    usuario del hash y devuelve True (ultimo canal -> desconectado).
    Si todavia hay otras pestanias, devuelve False.
    """
    user_id = str(user_id)
    r = _get_client()
    set_key = _USER_CHANNELS_KEY.format(user_id=user_id)

    await r.srem(set_key, channel_name)
    remaining = await r.scard(set_key)

    if remaining == 0:
        pipe = r.pipeline()
        pipe.delete(set_key)
        pipe.hdel(_HASH_KEY, user_id)
        await pipe.execute()
        return True

    return False


async def touch(user_id):
    """Refresca el TTL del set de canales (llamado en cada ping)."""
    user_id = str(user_id)
    r = _get_client()
    set_key = _USER_CHANNELS_KEY.format(user_id=user_id)
    await r.expire(set_key, _ttl_seconds())


async def get_all_users():
    """
    Devuelve la lista de user_data de todos los usuarios online.
    Hace lazy-cleanup: si una entrada del hash ya no tiene set de canales
    (porque el TTL expiro), se purga.
    """
    await purge_stale()
    r = _get_client()
    raw = await r.hgetall(_HASH_KEY)
    users = []
    for value in raw.values():
        try:
            users.append(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            continue
    return users


async def purge_stale():
    """
    Recorre el hash y borra las entradas cuyo set de canales ya expiro.
    Devuelve la lista de user_ids purgados (utiles para emitir
    user_disconnected al grupo si se desea).
    """
    r = _get_client()
    raw = await r.hgetall(_HASH_KEY)
    purged = []
    for user_id in list(raw.keys()):
        set_key = _USER_CHANNELS_KEY.format(user_id=user_id)
        exists = await r.exists(set_key)
        if not exists:
            await r.hdel(_HASH_KEY, user_id)
            purged.append(user_id)
    return purged


async def clear_all():
    """Util para tests: limpia todo el estado de presencia."""
    r = _get_client()
    keys = await r.keys('presence:*')
    if keys:
        await r.delete(*keys)


# ---- Presencia por vista/celda (Google Sheets style) -----------------------------

async def set_cell_focus(view_id, user_id, row_id, column, user_data):
    """
    Registra que el usuario esta enfocado en (row_id, column) dentro de view_id.
    Sobrescribe cualquier celda anterior del mismo usuario en esa vista.
    Devuelve la celda anterior si existia (para emitir cell_blur), si no None.
    """
    user_id = str(user_id)
    r = _get_client()
    key = _VIEW_CELLS_KEY.format(view_id=view_id)

    previous_raw = await r.hget(key, user_id)
    previous = None
    if previous_raw:
        try:
            previous = json.loads(previous_raw)
        except (json.JSONDecodeError, TypeError):
            previous = None

    payload = {
        'user_id': user_id,
        'row_id': row_id,
        'column': column,
        'user': user_data,
    }

    pipe = r.pipeline()
    pipe.hset(key, user_id, json.dumps(payload))
    pipe.expire(key, _ttl_seconds())
    await pipe.execute()

    return previous


async def clear_cell_focus(view_id, user_id):
    """
    Quita la celda enfocada por user_id en view_id.
    Devuelve la celda que estaba enfocada (para emitir cell_blur), o None.
    """
    user_id = str(user_id)
    r = _get_client()
    key = _VIEW_CELLS_KEY.format(view_id=view_id)

    previous_raw = await r.hget(key, user_id)
    if not previous_raw:
        return None

    await r.hdel(key, user_id)

    try:
        return json.loads(previous_raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def get_cells(view_id):
    """Lista de todas las celdas enfocadas actualmente en view_id."""
    r = _get_client()
    key = _VIEW_CELLS_KEY.format(view_id=view_id)
    raw = await r.hgetall(key)
    cells = []
    for value in raw.values():
        try:
            cells.append(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            continue
    return cells


async def clear_user_from_all_views(user_id):
    """
    Llamado al desconectar al usuario: borra su entrada de TODAS las vistas
    en las que tuviera foco. Devuelve lista de (view_id, cell) afectados para
    notificar cell_blur a esos grupos.
    """
    user_id = str(user_id)
    r = _get_client()
    keys = await r.keys('presence:view:*:cells')
    affected = []
    for key in keys:
        cell_raw = await r.hget(key, user_id)
        if not cell_raw:
            continue
        try:
            cell = json.loads(cell_raw)
        except (json.JSONDecodeError, TypeError):
            cell = None
        await r.hdel(key, user_id)
        # extraer view_id de la clave 'presence:view:<view_id>:cells'
        parts = key.split(':')
        if len(parts) >= 4:
            view_id = parts[2]
            affected.append((view_id, cell))
    return affected
