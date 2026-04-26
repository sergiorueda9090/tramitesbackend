"""
Middleware de autenticacion JWT para Django Channels.

Lee el token del query string (?token=...) o del header Authorization,
lo valida con simplejwt y rellena scope['user'].

Si el token falta o es invalido, deja scope['user'] como AnonymousUser.
NO rechaza la conexion aqui — esa decision se toma en el consumer
(controlado por settings.PRESENCE_REQUIRE_AUTH).
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user_from_token(token_str):
    """Valida el token y retorna el User o AnonymousUser."""
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
        from django.contrib.auth import get_user_model

        UserModel = get_user_model()
        access = AccessToken(token_str)
        user_id = access.get('user_id')
        if not user_id:
            return AnonymousUser()
        return UserModel.objects.get(pk=user_id)
    except Exception:
        return AnonymousUser()


def _extract_token(scope):
    """Busca el token en query string '?token=' o en header Authorization Bearer."""
    query_string = scope.get('query_string', b'').decode()
    qs = parse_qs(query_string)
    token = qs.get('token', [None])[0]
    if token:
        return token

    headers = dict(scope.get('headers', []))
    auth_header = headers.get(b'authorization', b'').decode()
    if auth_header.lower().startswith('bearer '):
        return auth_header.split(' ', 1)[1].strip()

    return None


class JWTAuthMiddleware(BaseMiddleware):
    """Middleware Channels que autentica via JWT (simplejwt)."""

    async def __call__(self, scope, receive, send):
        token = _extract_token(scope)
        if token:
            scope['user'] = await _get_user_from_token(token)
        else:
            scope['user'] = AnonymousUser()
        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """Helper para envolver un router con el middleware JWT."""
    return JWTAuthMiddleware(inner)
