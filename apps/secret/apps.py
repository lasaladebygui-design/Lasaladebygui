from django.apps import AppConfig


class SecretConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.secret"
    verbose_name = "Top Secret"
