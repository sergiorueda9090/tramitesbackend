"""
Subida del comprobante de pago a S3.

Reutiliza el mismo patrón boto3 + settings AWS_* que `finalizados_tramites`.
La imagen se sube al bucket `AWS_S3_COMPROBANTES_BUCKET` y se devuelve la URL
del objeto, que se guarda en `PasarelaPago.comprobante_pago`.
"""
import mimetypes
import uuid

from django.conf import settings


def subir_comprobante_a_s3(archivo, pasarela_id):
    """
    Sube `archivo` (UploadedFile de Django) a S3 y devuelve (url, error).
    Si error no es None, el caller no debe marcar el pago como exitoso.
    """
    bucket = getattr(settings, 'AWS_S3_COMPROBANTES_BUCKET', '') or ''
    if not bucket:
        return None, 'AWS_S3_COMPROBANTES_BUCKET no está configurado.'

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return None, "Falta la dependencia 'boto3' en el backend para subir a S3."

    region = getattr(settings, 'AWS_S3_REGION', 'us-east-1') or 'us-east-1'
    prefijo = getattr(settings, 'AWS_S3_COMPROBANTES_PREFIX', 'comprobantes/') or ''

    # Key único: comprobantes/pasarela_<id>_<uuid>.<ext>
    nombre = getattr(archivo, 'name', '') or 'comprobante'
    ext = ('.' + nombre.rsplit('.', 1)[1].lower()) if '.' in nombre else ''
    key = f"{prefijo}pasarela_{pasarela_id}_{uuid.uuid4().hex}{ext}"

    content_type = (
        getattr(archivo, 'content_type', None)
        or mimetypes.guess_type(nombre)[0]
        or 'application/octet-stream'
    )

    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', '') or None,
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', '') or None,
            region_name=region,
        )
        try:
            archivo.seek(0)
        except Exception:
            pass
        s3.upload_fileobj(archivo, bucket, key, ExtraArgs={'ContentType': content_type})
    except (BotoCoreError, ClientError) as e:
        return None, str(e)
    except Exception as e:
        return None, f'Inesperado: {e}'

    url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    return url, None


def generar_url_presignada(url_objeto, expires=3600):
    """
    Genera una URL prefirmada (GET temporal) para un objeto S3 dado su URL
    pública. Necesaria porque el bucket es privado. Devuelve (url, error).
    """
    if not url_objeto:
        return None, 'No hay URL de objeto.'
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
        from urllib.parse import urlparse, unquote
    except ImportError:
        return None, "Falta la dependencia 'boto3' en el backend."

    p = urlparse(url_objeto)
    # host: <bucket>.s3.<region>.amazonaws.com  → bucket = lo previo a '.s3'
    bucket = p.netloc.split('.s3')[0]
    key = unquote(p.path.lstrip('/'))
    if not bucket or not key:
        return None, 'URL de objeto S3 inválida.'

    region = getattr(settings, 'AWS_S3_REGION', 'us-east-1') or 'us-east-1'
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', '') or None,
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', '') or None,
            region_name=region,
        )
        url = s3.generate_presigned_url('get_object', Params={'Bucket': bucket, 'Key': key}, ExpiresIn=expires)
    except (BotoCoreError, ClientError) as e:
        return None, str(e)
    except Exception as e:
        return None, f'Inesperado: {e}'

    return url, None
