
"""Adaptador de notificaciones para Telegram y consola."""

import os
import requests
from dotenv import load_dotenv

from fenix.utils.errors import PermanentError, RetryableError


def notify(text: str) -> None:
    """
    Envía una notificación y verifica que Telegram la haya recibido.

    Args:
        text: Mensaje público que se enviará.

    Returns:
        None cuando el envío fue confirmado.

    Raises:
        RetryableError: Si ocurre un error temporal.
        PermanentError: Si existe un problema de configuración.
    """
    load_dotenv() 
    
    # Obtener el proveedor configurado
    mode = os.getenv("NOTIFY_PROVIDER", "console").strip().lower()

    # Modo de prueba por consola
    if mode == "console":
        print(text[:1000])
        return

    # Implementación de Telegram
    if mode == "telegram":

        # Obtener las credenciales del entorno
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            raise PermanentError(
                "Falta configurar las credenciales de Telegram"
            )

        if not isinstance(text, str) or not text.strip():
            raise PermanentError("El mensaje está vacío o no es válido")

        # Preparar la URL y los datos
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": text.strip()[:1000]
        }

        try:
            # Enviar el mensaje mediante HTTP POST
            response = requests.post(
                url,
                json=payload,
                timeout=(2, 5)
            )

        except requests.RequestException:
            # No mostrar la excepción original porque puede contener el token
            raise RetryableError(
                "Error temporal al conectar con Telegram"
            ) from None

        # Comprobar el estado HTTP
        if response.status_code in (408, 429) or response.status_code >= 500:
            raise RetryableError(
                f"Error temporal de Telegram: HTTP {response.status_code}"
            )

        if response.status_code < 200 or response.status_code >= 300:
            raise PermanentError(
                f"Telegram rechazó la solicitud: HTTP {response.status_code}"
            )

        # Verificar la respuesta JSON
        try:
            result = response.json()
        except ValueError:
            raise RetryableError(
                "Telegram devolvió una respuesta inválida"
            ) from None

        if not isinstance(result, dict) or result.get("ok") is not True:
            raise PermanentError(
                "Telegram no confirmó el envío del mensaje"
            )

        return

    # Proveedor desconocido
    raise PermanentError(
        "Proveedor inválido. Utilice console o telegram"
    )

if __name__ == "__main__":
    notify("¡Sistema Fénix conectado correctamente!")
