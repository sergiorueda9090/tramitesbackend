"""
Lógica PURA (sin objetos DRF, sin `request`) para generar el link de pago de un
trámite contra los generadores externos (Previsora / Mundial).

La tarea Celery (`tramites/tasks.py`) NO tiene `request` ni puede devolver
objetos `Response`, por lo que la lógica vive aquí como funciones que devuelven
dicts/strings. Es la MISMA regla de negocio que el frontend
(`GenerarLinkDialog.jsx → proveedorRecomendado / DOC_TRAMITE_A_PREVISORA /
partirNombre`) y que las vistas del botón manual (`tramites/api/views.py`),
replicada en el backend para que la tarea pueda decidir sola.
"""
import json
import random
import urllib.request
import urllib.error

from django.db.models import Min, Max

from correos_aleatorios.models import CorreoAleatorio

# Hosts de los generadores externos (idénticos a tramites/api/views.py).
PREVISORA_URLPAGO = 'http://130.94.105.156:9515/api/urlpago'
MUNDIAL_URL       = 'https://soat-scraper.qf4cjg.easypanel.host/api/mundial'

# Mapeo tipo_documento del trámite (CC/CE/NIT/PAS) → código numérico Previsora.
# Mismo mapa que el frontend (DOC_TRAMITE_A_PREVISORA).
DOC_A_PREVISORA = {'CC': 1, 'CE': 2, 'TI': 3, 'PAS': 4, 'NIT': 5}


def _formatear_token(valor):
    """
    Normaliza un nombre/apellido para Previsora: concatena los compuestos
    ("de la cruz" → "delacruz"). Cadena vacía si no hay valor.
    """
    if not valor:
        return ''
    return ''.join(str(valor).split())


# Partículas que en español forman parte del apellido y se unen al token
# siguiente para formar un apellido compuesto ('de la cruz', 'del río').
PARTICULAS_APELLIDO = {
    'de', 'del', 'la', 'las', 'los', 'san', 'santa',
    'da', 'di', 'do', 'dos', 'van', 'von', 'mac', 'mc',
}


def _agrupar_unidades(tokens):
    """Agrupa los tokens en 'unidades': una partícula (de, la, del, ...) se une
    al token siguiente. 'MARIA DE LA CRUZ ROJAS' → ['MARIA', 'DE LA CRUZ', 'ROJAS']."""
    unidades, buffer = [], []
    for tok in tokens:
        buffer.append(tok)
        if tok.lower() not in PARTICULAS_APELLIDO:
            unidades.append(' '.join(buffer))
            buffer = []
    if buffer:  # partículas colgando al final → unir a la última unidad
        if unidades:
            unidades[-1] = unidades[-1] + ' ' + ' '.join(buffer)
        else:
            unidades.append(' '.join(buffer))
    return unidades


def partir_nombre(nombre_completo):
    """
    Divide un nombre completo en nombre/nombre2/apellido/apellido2.

    Detecta partículas de apellido compuestas ('de', 'la', 'del', 'los', ...):
    'MARIA DE LA CRUZ ROJAS' → apellidos 'DE LA CRUZ' + 'ROJAS' (no parte mal en
    'LA'/'CRUZ'). Sin partículas usa el conteo clásico (la última o las dos
    últimas unidades son apellidos). Misma lógica que el frontend (partirNombre).
    """
    tokens = str(nombre_completo or '').strip().split()
    if not tokens:
        return {'nombre': '', 'nombre2': '', 'apellido': '', 'apellido2': ''}

    unidades = _agrupar_unidades(tokens)
    n = len(unidades)
    if n == 1:
        return {'nombre': unidades[0], 'nombre2': '', 'apellido': '', 'apellido2': ''}

    # Si hay partícula, los apellidos empiezan en la primera unidad que la
    # contenga. Si no, los apellidos son la(s) última(s) unidad(es) por conteo.
    idx_particula = next(
        (i for i, u in enumerate(unidades)
         if any(p in PARTICULAS_APELLIDO for p in u.lower().split())),
        None,
    )
    if idx_particula is not None and 0 < idx_particula < n:
        corte = idx_particula
    elif n == 2:
        corte = 1
    else:
        corte = n - 2

    nombres = unidades[:corte]
    apellidos = unidades[corte:]
    if not nombres:  # salvaguarda: nunca dejar el nombre vacío
        nombres = [apellidos.pop(0)] if apellidos else ['']

    return {
        'nombre': nombres[0] if nombres else '',
        'nombre2': ' '.join(nombres[1:]),
        'apellido': apellidos[0] if apellidos else '',
        'apellido2': ' '.join(apellidos[1:]),
    }


def es_moto(tramite):
    grupo = (tramite.grupo_soat or '').upper()
    clase = (tramite.clase or '').upper()
    return grupo in ('MOTOS', 'CICLOMOTORES') or 'MOTO' in clase


def resolver_proveedor(tramite):
    """
    Devuelve 'previsora' | 'mundial' según la regla de negocio:
      - Moto con año (modelo) válido: modelo ≥ 2022 → previsora; ≤ 2021 → mundial.
      - No moto (o sin año): usar `entidad` del trámite; por defecto 'previsora'.
    """
    moto = es_moto(tramite)
    try:
        anio = int(tramite.modelo)
    except (TypeError, ValueError):
        anio = None
    if moto and anio is not None:
        return 'previsora' if anio >= 2022 else 'mundial'
    entidad = (tramite.entidad or '').upper()
    if entidad == 'MUNDIAL':
        return 'mundial'
    if entidad == 'PREVISORA':
        return 'previsora'
    return 'previsora'


def obtener_correo_aleatorio():
    """
    Devuelve un CorreoAleatorio activo (no eliminado) al azar, o None.

    Selección por PK aleatorio (usa el índice de clave primaria) en vez de
    ORDER BY RAND(): con cientos de miles de correos en el pool, `order_by('?')`
    hace un escaneo + sort completo (~1.3 s/llamada en 262k filas). Este método
    es de milisegundos. La distribución es uniforme si los PKs son densos; con
    huecos (soft-deletes) el sesgo es despreciable para este caso de uso.
    """
    qs = CorreoAleatorio.objects.filter(activo=True, deleted_at__isnull=True)
    # Rango de PKs sobre toda la tabla → MySQL resuelve MIN/MAX por índice (instantáneo).
    rango = CorreoAleatorio.objects.aggregate(lo=Min('id'), hi=Max('id'))
    lo, hi = rango['lo'], rango['hi']
    if lo is None:
        return None
    for _ in range(5):
        rid = random.randint(lo, hi)
        obj = qs.filter(id__gte=rid).order_by('id').first()
        if obj is not None:
            return obj
    # Fallback (si cayó en una cola de inactivos): primer activo por id.
    return qs.order_by('id').first()


def construir_payload(tramite, proveedor, correo):
    """Devuelve (url, payload) para el proveedor dado. Mismos campos que las
    vistas del botón manual."""
    if proveedor == 'previsora':
        partes = partir_nombre(tramite.nombre_completo)
        # Previsora espera SOLO `nombre` y `apellido` (NO nombre2/apellido2),
        # en MINÚSCULAS: el PRIMER nombre y el PRIMER apellido. La detección de
        # partículas en partir_nombre asegura que el "primer apellido" de un
        # compuesto sea 'de la cruz' y no 'la'.
        payload = {
            'placa': (tramite.placa or '').upper(),
            'tipodocumento': DOC_A_PREVISORA.get(tramite.tipo_documento, 1),
            'documento': tramite.numero_documento or '',
            'nombre': _formatear_token(partes['nombre']).lower(),
            'apellido': _formatear_token(partes['apellido']).lower(),
            'telefono': tramite.telefono or '',
            'correo': correo,
        }
        return PREVISORA_URLPAGO, payload
    # mundial
    payload = {
        'placa': (tramite.placa or '').upper(),
        'tipo_documento': tramite.tipo_documento or 'CC',
        'nro_documento': tramite.numero_documento or '',
        'telefono': tramite.telefono or '',
        'email': correo,
    }
    return MUNDIAL_URL, payload


def post_json_externo(url, payload, timeout=60):
    """POST JSON a un servicio externo. Devuelve (data, error_str). Sin objetos DRF."""
    body = json.dumps(payload).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8')), None
    except urllib.error.HTTPError as e:
        return None, f'HTTP {e.code}: {e.read().decode("utf-8", errors="replace")}'
    except urllib.error.URLError as e:
        return None, f'Conexión: {e.reason}'
    except Exception as e:
        return None, f'Inesperado: {e}'


def extraer_url_pago(data):
    """
    Extrae la URL del link de la respuesta del tercero, probando los nombres de
    campo conocidos tanto en la RAÍZ como anidados bajo 'data'.

    Previsora responde en la raíz: {"success": true, "urlPago": "https://..."}.
    Por eso hay que mirar `data['urlPago']` (raíz), no solo `data['data'][...]`.
    """
    if not isinstance(data, dict):
        return None
    CLAVES = ('urlPago', 'url', 'link', 'urlpago', 'linkPago', 'linkpago')
    # 1) anidado bajo 'data' (otros proveedores)
    d = data.get('data') if isinstance(data.get('data'), dict) else {}
    for k in CLAVES:
        if d.get(k):
            return d[k]
    # 2) en la raíz (Previsora: urlPago)
    for k in CLAVES:
        if data.get(k):
            return data[k]
    return None
