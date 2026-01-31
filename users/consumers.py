import json
from channels.generic.websocket import AsyncWebsocketConsumer


class PresenceConsumer(AsyncWebsocketConsumer):
    # Almacena usuarios conectados en memoria (compartido entre instancias)
    connected_users = {}

    async def connect(self):
        """Se ejecuta cuando un cliente se conecta al WebSocket."""
        print("=" * 50)
        print("WEBSOCKET: Nueva conexion entrante")
        print(f"Channel name: {self.channel_name}")
        print(f"Scope: {self.scope.get('path')}")
        print("=" * 50)

        self.room_group_name = 'online_users'
        self.user_id = None

        # Unirse al grupo de usuarios en linea
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        print("WEBSOCKET: Conexion aceptada")

    async def disconnect(self, close_code):
        """Se ejecuta cuando un cliente se desconecta."""
        print("=" * 50)
        print(f"WEBSOCKET: Desconexion - codigo: {close_code}")
        print(f"User ID: {self.user_id}")
        print("=" * 50)

        if self.user_id and self.user_id in PresenceConsumer.connected_users:
            del PresenceConsumer.connected_users[self.user_id]
            print(f"WEBSOCKET: Usuario {self.user_id} removido de connected_users")

            # Notificar a todos que el usuario se desconecto
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_disconnected',
                    'user_id': self.user_id,
                }
            )

        # Salir del grupo
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f"WEBSOCKET: Usuarios conectados: {list(PresenceConsumer.connected_users.keys())}")

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
                await self.send(text_data=json.dumps({'type': 'pong'}))

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

        self.user_id = str(data.get('user_id'))
        print(f"User ID: {self.user_id}")

        user_data = {
            'id': self.user_id,
            'name': data.get('name', 'Usuario'),
            'avatar': data.get('avatar'),
            'color': data.get('color', '#1976d2'),
        }
        print(f"User data: {user_data}")

        # Guardar usuario en el diccionario
        PresenceConsumer.connected_users[self.user_id] = {
            'channel_name': self.channel_name,
            'user_data': user_data,
        }
        print(f"Usuarios conectados ahora: {list(PresenceConsumer.connected_users.keys())}")

        # Notificar a todos del nuevo usuario conectado
        print("WEBSOCKET: Notificando a todos del nuevo usuario...")
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_connected',
                'user': user_data,
            }
        )

        # Enviar lista actual de usuarios al que se acaba de conectar
        users_list = [
            u['user_data'] for u in PresenceConsumer.connected_users.values()
        ]
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
