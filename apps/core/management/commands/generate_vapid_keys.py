import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management.base import BaseCommand
from py_vapid import Vapid02


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class Command(BaseCommand):
    help = (
        "Genera un par de claves VAPID nuevas para las notificaciones push y las "
        "imprime listas para pegar en las variables de entorno (VAPID_PUBLIC_KEY, "
        "VAPID_PRIVATE_KEY). Se genera una sola vez por sitio — no lo repitas en "
        "cada deploy o las suscripciones ya guardadas dejarán de funcionar."
    )

    def handle(self, *args, **options):
        vapid = Vapid02()
        vapid.generate_keys()

        public_raw = vapid.public_key.public_bytes(
            encoding=Encoding.X962, format=PublicFormat.UncompressedPoint,
        )
        private_pem = vapid.private_pem().decode()

        self.stdout.write(self.style.SUCCESS("VAPID_PUBLIC_KEY=") + _b64url(public_raw))
        self.stdout.write(self.style.SUCCESS("VAPID_PRIVATE_KEY=") + private_pem.replace("\n", "\\n"))
        self.stdout.write("")
        self.stdout.write(
            "Copia esas dos líneas en tu .env (local) y en las variables de entorno "
            "de Render (producción). El valor de VAPID_PRIVATE_KEY lleva \\n literales "
            "en vez de saltos de línea reales para que quepa en una sola línea de .env."
        )
