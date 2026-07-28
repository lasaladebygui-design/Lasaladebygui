from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    label = 'core'
    verbose_name = 'Sitio'

    def ready(self):
        # Gestor y Editor son is_staff (para permisos puntuales dentro del
        # propio /admin/, p. ej. el foro), pero /admin/ en sí debe ser cosa
        # solo del Admin — is_superuser, que el modelo User solo concede al
        # rol Admin (ver User.save()).
        from django.contrib import admin

        def has_permission(request):
            return bool(request.user and request.user.is_active and request.user.is_superuser)

        admin.site.has_permission = has_permission
