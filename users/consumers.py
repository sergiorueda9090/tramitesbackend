import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from users import presence_store


class PresenceConsumer(AsyncWebsocketConsumer):
    # Fallback en memoria (solo se usa si PRESENCE_USE_REDIS=False).
    connected_users = {}

    @staticmethod
    def _use_redis():
        return getattr(settings, 'PRESENCE_USE_REDIS', True)

    async def connect(self):
        """Se ejecuta cuando un cliente se conecta al WebSocket."""
        scope_user = self.scope.get('user')
        is_anon = getattr(scope_user, 'is_anonymous', True)
        print("=" * 50)
        print("WEBSOCKET: Nueva conexion entrante")
        print(f"Channel name: {self.channel_name}")
        print(f"Scope: {self.scope.get('path')}")
        print(f"Scope user: {scope_user} (anonymous={is_anon})")
        print("=" * 50)

        # Rechazar conexiones anonimas si el flag esta activo
        if getattr(settings, 'PRESENCE_REQUIRE_AUTH', True) and is_anon:
            print("WEBSOCKET: Rechazando conexion anonima (PRESENCE_REQUIRE_AUTH=True)")
            await self.close(code=4001)
            return

        self.room_group_name = 'online_users'
        self.user_id = None
        # Vistas (modulos) en las que este canal esta suscrito para presencia de celda
        self.subscribed_views = set()
        # Datos de usuario para emitir en eventos de celda
        self._cached_user_data = None

        # Unirse al grupo de usuarios en linea
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        print(f"WEBSOCKET: Conexion aceptada (use_redis={self._use_redis()})")

    async def disconnect(self, close_code):
        """Se ejecuta cuando un cliente se desconecta."""
        print("=" * 50)
        print(f"WEBSOCKET: Desconexion - codigo: {close_code}")
        print(f"User ID: {self.user_id}")
        print("=" * 50)

        if self.user_id:
            was_last_channel = await self._remove_user_channel(self.user_id, self.channel_name)
            if was_last_channel:
                print(f"WEBSOCKET: Ultimo canal de {self.user_id}, notificando desconexion")
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_disconnected',
                        'user_id': self.user_id,
                    }
                )
                # Limpiar foco de celda en todas las vistas y notificar a esos grupos
                if self._use_redis():
                    affected = await presence_store.clear_user_from_all_views(self.user_id)
                    for view_id, cell in affected:
                        await self.channel_layer.group_send(
                            self._view_group(view_id),
                            {
                                'type': 'cell_blur_event',
                                'view_id': view_id,
                                'user_id': self.user_id,
                                'row_id': cell.get('row_id') if cell else None,
                                'column': cell.get('column') if cell else None,
                            }
                        )
            else:
                print(f"WEBSOCKET: {self.user_id} aun tiene otras pestanas abiertas, sin notificar")

        # Salir de todos los grupos a los que estaba suscrito
        for view_id in list(self.subscribed_views):
            await self.channel_layer.group_discard(
                self._view_group(view_id),
                self.channel_name
            )
        self.subscribed_views.clear()

        # Salir del grupo principal
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Se ejecuta cuando se recibe un mensaje del cliente."""
        print("=" * 50)
        print(f"WEBSOCKET: Mensaje recibido: {text_data}")
        print("=" * 50)

        try:
            data = json.loads(text_data)
            action = data.get('action')
            print(f"WEBSOCKET: Action: {action}")

            if action == 'join':
                await self.handle_join(data)
            elif action == 'ping':
                print("WEBSOCKET: Ping recibido, enviando pong")
                if self.user_id and self._use_redis():
                    await presence_store.touch(self.user_id)
                await self.send(text_data=json.dumps({'type': 'pong'}))
            elif action == 'subscribe_view':
                await self.handle_subscribe_view(data)
            elif action == 'unsubscribe_view':
                await self.handle_unsubscribe_view(data)
            elif action == 'cell_focus':
                await self.handle_cell_focus(data)
            elif action == 'cell_blur':
                await self.handle_cell_blur(data)

        except json.JSONDecodeError as e:
            print(f"WEBSOCKET ERROR: JSON decode error: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))

    async def handle_join(self, data):
        """Maneja cuando un usuario se une."""
        print("=" * 50)
        print("WEBSOCKET: Procesando JOIN")
        print(f"Data recibida: {data}")

        # Si hay usuario autenticado en el scope, su ID manda sobre lo que envie el cliente
        scope_user = self.scope.get('user')
        if scope_user is not None and not getattr(scope_user, 'is_anonymous', True):
            self.user_id = str(scope_user.id)
            print(f"User ID (desde JWT): {self.user_id}")
        else:
            self.user_id = str(data.get('user_id'))
            print(f"User ID (desde payload): {self.user_id}")

        user_data = {
            'id': self.user_id,
            'name': data.get('name', 'Usuario'),
            'avatar': data.get('avatar'),
            'color': data.get('color', '#1976d2'),
        }
        # Cachear para emitirlos en eventos de celda sin necesidad de re-resolver
        self._cached_user_data = user_data
        print(f"User data: {user_data}")

        is_first_channel = await self._add_user_channel(self.user_id, self.channel_name, user_data)

        # Lazy purge: detectar usuarios cuyo TTL expiro y notificar su desconexion al grupo
        if self._use_redis():
            purged = await presence_store.purge_stale()
            for stale_id in purged:
                if stale_id == self.user_id:
                    continue
                print(f"WEBSOCKET: TTL expirado para {stale_id}, emitiendo user_disconnected")
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_disconnected',
                        'user_id': stale_id,
                    }
                )

        # Notificar al grupo SOLO si es la primera pestania del usuario
        if is_first_channel:
            print(f"WEBSOCKET: Primera pestania de {self.user_id}, notificando user_connected")
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_connected',
                    'user': user_data,
                }
            )
        else:
            print(f"WEBSOCKET: {self.user_id} ya estaba conectado en otra pestania, no se renotifica")

        # Enviar lista actual de usuarios al que se acaba de conectar
        users_list = await self._get_users_list()
        print(f"WEBSOCKET: Enviando lista de usuarios: {users_list}")
        await self.send(text_data=json.dumps({
            'type': 'users_list',
            'users': users_list,
        }))
        print("WEBSOCKET: JOIN completado")
        print("=" * 50)

    async def user_connected(self, event):
        """Envia notificacion de usuario conectado a todos en el grupo."""
        print(f"WEBSOCKET: Enviando user_connected a {self.channel_name}: {event['user']}")
        await self.send(text_data=json.dumps({
            'type': 'user_connected',
            'user': event['user'],
        }))

    async def user_disconnected(self, event):
        """Envia notificacion de usuario desconectado a todos en el grupo."""
        print(f"WEBSOCKET: Enviando user_disconnected a {self.channel_name}: {event['user_id']}")
        await self.send(text_data=json.dumps({
            'type': 'user_disconnected',
            'user_id': event['user_id'],
        }))

    # ---- Presencia por vista / celda (Google Sheets style) --------------------------

    @staticmethod
    def _view_group(view_id):
        """Nombre del grupo de Channels para una vista (modulo) concreta."""
        # Channels limita el nombre a [a-z0-9_-]; sanitizamos por si acaso
        safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(view_id))
        return f'view_{safe}'

    async def handle_subscribe_view(self, data):
        """Cliente entra a un modulo (ej: tramites_list). Se suscribe al grupo
        y recibe el snapshot de celdas actualmente enfocadas en esa vista."""
        view_id = data.get('view_id')
        if not view_id:
            return

        group = self._view_group(view_id)
        await self.channel_layer.group_add(group, self.channel_name)
        self.subscribed_views.add(view_id)
        print(f"WEBSOCKET: {self.user_id} suscrito a vista '{view_id}'")

        # Snapshot inicial: enviar al cliente las celdas que ya estan enfocadas
        cells = []
        if self._use_redis():
            cells = await presence_store.get_cells(view_id)
        await self.send(text_data=json.dumps({
            'type': 'cells_snapshot',
            'view_id': view_id,
            'cells': cells,
        }))

    async def handle_unsubscribe_view(self, data):
        """Cliente sale de un modulo. Se da de baja del grupo y libera su celda
        si tenia una enfocada en esa vista."""
        view_id = data.get('view_id')
        if not view_id:
            return

        group = self._view_group(view_id)
        await self.channel_layer.group_discard(group, self.channel_name)
        self.subscribed_views.discard(view_id)
        print(f"WEBSOCKET: {self.user_id} dejo vista '{view_id}'")

        # Si tenia una celda enfocada, liberarla y notificar
        if self.user_id and self._use_redis():
            previous = await presence_store.clear_cell_focus(view_id, self.user_id)
            if previous:
                await self.channel_layer.group_send(
                    group,
                    {
                        'type': 'cell_blur_event',
                        'view_id': view_id,
                        'user_id': self.user_id,
                        'row_id': previous.get('row_id'),
                        'column': previous.get('column'),
                    }
                )

    async def handle_cell_focus(self, data):
        """Cliente reporta que esta enfocado en una celda concreta."""
        view_id = data.get('view_id')
        row_id = data.get('row_id')
        column = data.get('column')

        # Fallback: si self.user_id aun no se establecio (JOIN tardio),
        # tomarlo del scope (autenticado por el middleware JWT).
        if not self.user_id:
            scope_user = self.scope.get('user')
            if scope_user is not None and not getattr(scope_user, 'is_anonymous', True):
                self.user_id = str(scope_user.id)

        if not view_id or row_id is None or not column or not self.user_id:
            print(f"WEBSOCKET: cell_focus IGNORADO (view_id={view_id}, row_id={row_id}, column={column}, user_id={self.user_id})")
            return

        print(f"WEBSOCKET: cell_focus user={self.user_id} view={view_id} row={row_id} col={column}")

        user_data = self._get_user_data()
        group = self._view_group(view_id)

        if self._use_redis():
            previous = await presence_store.set_cell_focus(
                view_id, self.user_id, row_id, column, user_data
            )
            # Si el usuario tenia otra celda enfocada, emitir cell_blur sobre la anterior
            if previous and (previous.get('row_id') != row_id or previous.get('column') != column):
                await self.channel_layer.group_send(
                    group,
                    {
                        'type': 'cell_blur_event',
                        'view_id': view_id,
                        'user_id': self.user_id,
                        'row_id': previous.get('row_id'),
                        'column': previous.get('column'),
                    }
                )

        # Emitir cell_focus al grupo
        await self.channel_layer.group_send(
            group,
            {
                'type': 'cell_focus_event',
                'view_id': view_id,
                'user_id': self.user_id,
                'row_id': row_id,
                'column': column,
                'user': user_data,
            }
        )

    async def handle_cell_blur(self, data):
        """Cliente reporta que dejo de estar enfocado (sin entrar a otra celda)."""
        view_id = data.get('view_id')
        if not view_id or not self.user_id:
            return

        group = self._view_group(view_id)

        previous = None
        if self._use_redis():
            previous = await presence_store.clear_cell_focus(view_id, self.user_id)

        if previous:
            await self.channel_layer.group_send(
                group,
                {
                    'type': 'cell_blur_event',
                    'view_id': view_id,
                    'user_id': self.user_id,
                    'row_id': previous.get('row_id'),
                    'column': previous.get('column'),
                }
            )

    # Eventos del channel_layer hacia el cliente

    async def cell_focus_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'cell_focus',
            'view_id': event['view_id'],
            'user_id': event['user_id'],
            'row_id': event['row_id'],
            'column': event['column'],
            'user': event['user'],
        }))

    async def cell_blur_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'cell_blur',
            'view_id': event['view_id'],
            'user_id': event['user_id'],
            'row_id': event.get('row_id'),
            'column': event.get('column'),
        }))

    # ---- Eventos de cambios de datos en una vista ----------------------------------

    async def tramite_removed_event(self, event):
        """Notifica que un tramite ya no debe aparecer en el listado."""
        await self.send(text_data=json.dumps({
            'type': 'tramite_removed',
            'view_id': 'tramites_list',
            'tramite_id': event.get('tramite_id'),
            'reason': event.get('reason', ''),
        }))

    async def tramite_restored_event(self, event):
        """Notifica que un tramite vuelve a aparecer en el listado
        (ej: la pasarela asociada fue devuelta/eliminada)."""
        await self.send(text_data=json.dumps({
            'type': 'tramite_restored',
            'view_id': 'tramites_list',
            'tramite_id': event.get('tramite_id'),
            'reason': event.get('reason', ''),
        }))

    async def pasarela_added_event(self, event):
        """Notifica que un nuevo registro de pasarela debe aparecer."""
        await self.send(text_data=json.dumps({
            'type': 'pasarela_added',
            'view_id': 'pasarela_de_pago_list',
            'pasarela_id': event.get('pasarela_id'),
            'reason': event.get('reason', ''),
        }))

    async def pasarela_removed_event(self, event):
        """Notifica que un registro de pasarela ya no debe aparecer."""
        await self.send(text_data=json.dumps({
            'type': 'pasarela_removed',
            'view_id': 'pasarela_de_pago_list',
            'pasarela_id': event.get('pasarela_id'),
            'reason': event.get('reason', ''),
        }))

    def _get_user_data(self):
        """Datos publicos del usuario para emitir en eventos de celda."""
        if self._cached_user_data:
            return self._cached_user_data
        scope_user = self.scope.get('user')
        name = ''
        if scope_user is not None and not getattr(scope_user, 'is_anonymous', True):
            name = (
                f"{getattr(scope_user, 'first_name', '') or ''} "
                f"{getattr(scope_user, 'last_name', '') or ''}"
            ).strip() or getattr(scope_user, 'username', '') or 'Usuario'
        return {'id': self.user_id, 'name': name or 'Usuario', 'avatar': None, 'color': None}

    # ---- Capa de almacenamiento (Redis o memoria) ------------------------------------

    async def _add_user_channel(self, user_id, channel_name, user_data):
        """Devuelve True si es la primera pestania del usuario."""
        if self._use_redis():
            return await presence_store.add_channel(user_id, channel_name, user_data)

        existing = PresenceConsumer.connected_users.get(user_id)
        if existing is None:
            PresenceConsumer.connected_users[user_id] = {
                'channels': {channel_name},
                'user_data': user_data,
            }
            return True

        existing['channels'].add(channel_name)
        existing['user_data'] = user_data
        return False

    async def _remove_user_channel(self, user_id, channel_name):
        """Devuelve True si era el ultimo canal del usuario."""
        if self._use_redis():
            return await presence_store.remove_channel(user_id, channel_name)

        entry = PresenceConsumer.connected_users.get(user_id)
        if not entry:
            return False
        channels = entry.get('channels')
        if not channels:
            return False
        channels.discard(channel_name)
        if not channels:
            del PresenceConsumer.connected_users[user_id]
            return True
        return False

    async def _get_users_list(self):
        if self._use_redis():
            return await presence_store.get_all_users()
        return [u['user_data'] for u in PresenceConsumer.connected_users.values()]
