"""
Creación de un TramiteFinalizado a partir de una PasarelaPago.

Lógica compartida por:
  - finalizados_tramites.api.views.crear_desde_pasarela (botón manual en Pasarela)
  - pasarela_de_pago.api.views.confirmar_pago_pasarela (auto al marcar "Pago exitoso")

Hace el snapshot completo + soft-delete de la pasarela en una transacción. NO
emite eventos WS ni valida permisos: eso es responsabilidad del caller.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import TramiteFinalizado


def crear_finalizado_desde_pasarela(pasarela, usuario_que_confirma=None,
                                    observacion_override=None, tarjeta_override=None):
    """Crea el TramiteFinalizado (snapshot) desde `pasarela` y soft-borra la
    pasarela. Devuelve el TramiteFinalizado creado."""
    tarjeta_final = tarjeta_override or pasarela.tarjeta

    # Snapshot del 4x1000 al momento del cierre.
    aplica_4x1000 = bool(tarjeta_final and tarjeta_final.cuatro_por_mil == '1')
    base = (pasarela.precio_lay or Decimal('0')) + (pasarela.comision or Decimal('0'))
    cuatro_por_mil_valor = (base * Decimal('4') / Decimal('1000')) if aplica_4x1000 else Decimal('0')

    with transaction.atomic():
        finalizado = TramiteFinalizado.objects.create(
            pasarela=pasarela,
            tramite_origen_id_snapshot=pasarela.tramite_origen_id,
            usuario=pasarela.tramite_origen.usuario if pasarela.tramite_origen else pasarela.usuario,
            usuario_que_confirma=usuario_que_confirma,
            cliente=pasarela.cliente,
            etiqueta=pasarela.etiqueta,
            precio_cliente=pasarela.precio_cliente,
            tarifario_soat=pasarela.tarifario_soat,
            tarjeta=tarjeta_final,
            tipo_tramite=pasarela.tipo_tramite,
            tipo_vehiculo=pasarela.tipo_vehiculo,
            entidad=pasarela.entidad,
            grupo_soat=pasarela.grupo_soat,
            grupo_clase_runt=pasarela.grupo_clase_runt,
            grupo_subcriterio=pasarela.grupo_subcriterio,
            modulo_pregunta1=pasarela.modulo_pregunta1,
            modulo_pregunta2=pasarela.modulo_pregunta2,
            tarifa_codigo=pasarela.tarifa_codigo,
            tarifa_manual=pasarela.tarifa_manual,
            precio_lay=pasarela.precio_lay,
            comision=pasarela.comision,
            placa=pasarela.placa,
            clase=pasarela.clase,
            tipo_servicio=pasarela.tipo_servicio,
            marca=pasarela.marca,
            linea=pasarela.linea,
            modelo=pasarela.modelo,
            color=pasarela.color,
            cilindraje=pasarela.cilindraje,
            pasajeros_sentados=pasarela.pasajeros_sentados,
            capacidad_carga=pasarela.capacidad_carga,
            peso_bruto=pasarela.peso_bruto,
            chasis=pasarela.chasis,
            vin=pasarela.vin,
            tipo_documento=pasarela.tipo_documento,
            numero_documento=pasarela.numero_documento,
            nombre_completo=pasarela.nombre_completo,
            telefono=pasarela.telefono,
            correo=pasarela.correo,
            direccion=pasarela.direccion,
            tramite_estado=pasarela.tramite_estado,
            confirmacion_estado=pasarela.confirmacion_estado,
            cargar_pdf_estado=pasarela.cargar_pdf_estado,
            observacion=observacion_override if observacion_override is not None else pasarela.observacion,
            comprobante_pago=pasarela.comprobante_pago,
            link_pago=pasarela.link_pago,
            pago_confirmado_at=timezone.now(),
            cuatro_por_mil_valor=cuatro_por_mil_valor,
        )
        pasarela.soft_delete()

    return finalizado
