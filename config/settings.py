"""
Configuración de Django para La Sala de Bygui.

Fase 1: estructura base, conexión a Supabase (Postgres) vía DATABASE_URL,
autenticación con roles y theme.css editable desde el panel admin.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    REQUIRE_EMAIL_VERIFICATION=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

# --- Seguridad / entorno ---------------------------------------------------

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-only-change-me",
)

DEBUG = env("DEBUG")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default=None)
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# A partir de ALLOWED_HOSTS entero, no solo del hostname de Render: si el
# sitio también se sirve desde un dominio propio (añadido a ALLOWED_HOSTS
# por variable de entorno), sin esto los POST desde ese dominio —el login
# incluido— fallan con "La verificación CSRF ha fallado" aunque el GET de
# la misma página cargue bien (403 en vez de "host no permitido").
CSRF_TRUSTED_ORIGINS = [
    f"https://{host}" for host in ALLOWED_HOSTS if host not in ("localhost", "127.0.0.1")
]

# Render siempre define RENDER_EXTERNAL_HOSTNAME (no hace falta configurarlo
# a mano): sirve para detectar "esto es un despliegue real" incluso si
# alguien ha dejado DEBUG=True puesto por error en el panel — sin esto, un
# DEBUG=True accidental en Render se saltaría en silencio los "falla alto y
# claro" de más abajo (DATABASE_URL, Supabase Storage) y volveríamos a
# perder datos/imágenes sin ningún aviso.
IS_REAL_DEPLOY = bool(RENDER_EXTERNAL_HOSTNAME) or not DEBUG

# --- Apps --------------------------------------------------------------

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_ckeditor_5",
    "apps.core",
    "apps.accounts",
    "apps.articles",
    "apps.forum",
    "apps.movies",
    "apps.secret",
    "apps.social",
    "apps.games",
    "apps.shop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de datos (Supabase / Postgres vía DATABASE_URL) ------------------
# En local, si no defines DATABASE_URL en .env, se usa SQLite automáticamente.
# En producción (DEBUG=False) NO se permite ese mismo fallback silencioso:
# si DATABASE_URL faltara ahí, la app usaría SQLite sobre el disco efímero
# de Render, que se borra en cada reinicio/despliegue — perdiendo todo lo
# guardado (p. ej. los eventos del calendario) sin ningún aviso. Mejor que
# el despliegue falle alto y claro a que pierda datos en silencio.

_database_url = env("DATABASE_URL", default="")
if not _database_url:
    if IS_REAL_DEPLOY:
        raise ImproperlyConfigured(
            "DATABASE_URL no está configurada. En producción es obligatoria "
            "(si no, la app perdería todos los datos en cada reinicio al usar "
            "SQLite sobre disco efímero). Configúrala en el panel de Render."
        )
    _database_url = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {"default": env.db_url_config(_database_url)}
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"]["OPTIONS"] = {"sslmode": env("DB_SSLMODE", default="require")}

# --- Usuarios / autenticación -----------------------------------------

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailBackend",
    "apps.accounts.backends.AdminBackupPasswordBackend",
]

# Contraseña de respaldo para Admin (ver AdminBackupPasswordBackend) — vacía
# por defecto (desactivada). Se pone solo como variable de entorno en Render,
# nunca aquí, para no dejarla fija en el histórico de git.
ADMIN_BACKUP_PASSWORD = env("ADMIN_BACKUP_PASSWORD", default="")

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"

# Sesión larga: una vez iniciada sesión, no vuelve a pedirla mientras se siga
# usando el sitio de vez en cuando (cada visita alarga otro año la caducidad,
# por SESSION_SAVE_EVERY_REQUEST) — pensado para el panel de admin, que si
# no pide credenciales cada pocos días.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365  # 1 año
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
LOGOUT_REDIRECT_URL = "core:home"

REQUIRE_EMAIL_VERIFICATION_DEFAULT = env("REQUIRE_EMAIL_VERIFICATION")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internacionalización -----------------------------------------------

LANGUAGE_CODE = "es-es"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

# --- Estáticos (whitenoise) ---------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Media (portadas de artículos, avatares, fotos del tablón, imágenes
# insertadas en el cuerpo de un artículo vía CKEditor...) -------------------
# En el plan free de Render el disco no es persistente entre despliegues: sin
# esto, las imágenes subidas desaparecían en cada redeploy (se veían al
# momento y luego "no se habían publicado" nunca más). Si se rellenan las
# variables de Supabase Storage (mismo proyecto que ya se usa para la base de
# datos — su Storage expone una API compatible con S3), se usa eso en vez del
# disco local. En producción (DEBUG=False) NO se permite el fallback
# silencioso a disco local, por el mismo motivo que con DATABASE_URL: mejor
# que el despliegue falle alto y claro a que las imágenes se pierdan sin
# ningún aviso.

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

SUPABASE_STORAGE_ENDPOINT = env("SUPABASE_STORAGE_ENDPOINT", default="")
SUPABASE_STORAGE_BUCKET = env("SUPABASE_STORAGE_BUCKET", default="")
SUPABASE_STORAGE_ACCESS_KEY_ID = env("SUPABASE_STORAGE_ACCESS_KEY_ID", default="")
SUPABASE_STORAGE_SECRET_ACCESS_KEY = env("SUPABASE_STORAGE_SECRET_ACCESS_KEY", default="")
SUPABASE_STORAGE_REGION = env("SUPABASE_STORAGE_REGION", default="us-east-1")

USE_SUPABASE_STORAGE = bool(
    SUPABASE_STORAGE_ENDPOINT and SUPABASE_STORAGE_BUCKET and SUPABASE_STORAGE_ACCESS_KEY_ID
)

if not USE_SUPABASE_STORAGE and IS_REAL_DEPLOY:
    raise ImproperlyConfigured(
        "Faltan las variables de Supabase Storage (SUPABASE_STORAGE_ENDPOINT/"
        "BUCKET/ACCESS_KEY_ID). En producción son obligatorias (si no, las "
        "imágenes subidas se perderían en cada reinicio al usar disco "
        "efímero). Configúralas en el panel de Render."
    )

if USE_SUPABASE_STORAGE:
    from .storage import supabase_public_domain

    _supabase_public_domain = supabase_public_domain(SUPABASE_STORAGE_ENDPOINT, SUPABASE_STORAGE_BUCKET)

STORAGES = {
    "default": (
        {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": SUPABASE_STORAGE_ACCESS_KEY_ID,
                "secret_key": SUPABASE_STORAGE_SECRET_ACCESS_KEY,
                "bucket_name": SUPABASE_STORAGE_BUCKET,
                "endpoint_url": SUPABASE_STORAGE_ENDPOINT,
                "region_name": SUPABASE_STORAGE_REGION,
                "custom_domain": _supabase_public_domain,
                "querystring_auth": False,
                # Evita que dos archivos con el mismo nombre (p. ej. todos los
                # avatares recortados se llaman "avatar.jpg") se pisen entre
                # sí: Django añade un sufijo aleatorio como ya hacía en disco.
                "file_overwrite": False,
                "addressing_style": "path",
            },
        }
        if USE_SUPABASE_STORAGE
        else {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    ),
    # Fotos del tablón de Top Secret: a diferencia de "default" (avatares,
    # portadas de artículos... pensados para ser públicos), estas NO deben
    # tener una URL pública y permanente — solo quien tiene el código y
    # acceso a ese tablón concreto puede verlas (ver apps/secret/views.py,
    # photo_serve). Por eso "querystring_auth" va a True aquí (URL firmada,
    # caduca en un minuto) y no se usa "custom_domain" (el dominio público
    # de Supabase ignora la firma).
    "secret_photos": (
        {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": SUPABASE_STORAGE_ACCESS_KEY_ID,
                "secret_key": SUPABASE_STORAGE_SECRET_ACCESS_KEY,
                "bucket_name": SUPABASE_STORAGE_BUCKET,
                "endpoint_url": SUPABASE_STORAGE_ENDPOINT,
                "region_name": SUPABASE_STORAGE_REGION,
                "querystring_auth": True,
                "querystring_expire": 60,
                "file_overwrite": False,
                "addressing_style": "path",
            },
        }
        if USE_SUPABASE_STORAGE
        else {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    ),
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            # django-jazzmin referencia "vendor/bootswatch" como prefijo de
            # ruta (para componer <tema>/bootstrap.min.css), no como un
            # archivo real — el storage "Manifest" de Django/whitenoise
            # intenta resolverlo contra el manifiesto y revienta con
            # ValueError: Missing staticfiles manifest entry. La variante
            # sin manifiesto (solo comprime, no hashea nombres de archivo)
            # evita el crash; el coste es no invalidar caché de navegador
            # por nombre de archivo tras cada deploy.
            else "whitenoise.storage.CompressedStaticFilesStorage"
        )
    },
}

# --- Editor de artículos (CKEditor 5) --------------------------------------

CKEDITOR_5_FILE_UPLOAD_PERMISSION = "staff"
CKEDITOR_5_CONFIGS = {
    "default": {
        # El plugin "Autosave" (activo por defecto) añade un aviso nativo del
        # navegador ("los cambios pueden no haberse guardado") al intentar
        # salir con algo pendiente — molesto porque aquí el guardado real es
        # el botón "Publicar"/"Guardar cambios" del formulario, no autosave.
        "removePlugins": ["Autosave"],
        # Barra de herramientas "de doc": no solo negrita/cursiva/subrayado,
        # también color de texto y resaltado, listas con casillas, sangría,
        # imagen (subida o por URL, se puede insertar entre dos frases
        # cualesquiera, no solo al final), vídeo embebido (pegar un enlace
        # de YouTube/Vimeo lo convierte en reproductor) y línea horizontal.
        "toolbar": [
            "undo", "redo", "|",
            "heading", "|",
            "bold", "italic", "underline", "strikethrough", "|",
            "fontColor", "fontBackgroundColor", "highlight", "removeFormat", "|",
            "alignment", "|",
            "bulletedList", "numberedList", "todoList", "|",
            "outdent", "indent", "|",
            "link", "blockQuote", "insertImage", "insertTable", "mediaEmbed", "horizontalLine", "|",
            "specialCharacters", "findAndReplace",
        ],
        "image": {
            "toolbar": [
                "imageTextAlternative", "|",
                "imageStyle:alignLeft", "imageStyle:alignCenter", "imageStyle:alignRight", "|",
                "resizeImage",
            ],
            "styles": ["alignLeft", "alignCenter", "alignRight"],
            # Permite arrastrar/elegir un tamaño de la imagen (50/75/100%)
            # además de colocarla a la izquierda/centro/derecha — el estilo
            # alineado a un lado es lo que hace que el texto la rodee (ver
            # `.richtext .image-style-align-left/right` en main.css).
            #
            # OJO: la opción "original" de CKEditor5 se representa oficialmente
            # con `value: None` (JSON null) — pero el script de arranque de
            # django-ckeditor-5 parsea esta config con un reviver que hace
            # `valor.toString()` sin comprobar null, así que ese único `None`
            # tira abajo TODO el editor nada más cargar la página (crash en
            # `createEditors`, "Cannot read properties of null (reading
            # 'toString')") — nunca lo pongas en esta config. Por eso aquí se
            # usa "100" (texto) en vez de None para la opción "original".
            "resizeOptions": [
                {"name": "resizeImage:100", "value": "100", "icon": "original"},
                {"name": "resizeImage:50", "value": "50", "icon": "medium"},
                {"name": "resizeImage:75", "value": "75", "icon": "large"},
            ],
            "resizeUnit": "%",
        },
        "table": {
            "contentToolbar": ["tableColumn", "tableRow", "mergeTableCells"],
        },
    },
}

# --- Email (verificación de cuenta, recuperar contraseña, contacto) --------

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)

# Si en un despliegue real EMAIL_BACKEND queda puesto a SMTP pero faltan las
# credenciales, los correos (verificación, recuperar contraseña, contacto)
# fallarían o se quedarían sin enviar de forma confusa. Mismo criterio que
# con DATABASE_URL y Supabase Storage: mejor que falle alto y claro en el
# arranque a que "no lleguen" los correos sin ninguna pista de por qué.
if IS_REAL_DEPLOY and EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
    if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
        raise ImproperlyConfigured(
            "EMAIL_BACKEND está puesto a SMTP pero faltan EMAIL_HOST_USER/"
            "EMAIL_HOST_PASSWORD. Sin ellos no llega ningún correo (ni "
            "verificación, ni recuperar contraseña, ni el formulario de "
            "contacto). Configúralas en el panel de Render — si usas Gmail "
            "con verificación en dos pasos, EMAIL_HOST_PASSWORD debe ser una "
            "\"contraseña de aplicación\", no la contraseña normal de la cuenta."
        )

# Gmail rechaza o no entrega bien los correos si el remitente ("From") no
# coincide con la cuenta autenticada por SMTP. Por eso, si DEFAULT_FROM_EMAIL
# no se fija explícitamente (o se deja vacío), se deriva de EMAIL_HOST_USER
# en vez de usar un dominio distinto que no está verificado en esa cuenta de
# Gmail. `or` cubre tanto la variable ausente como presente-pero-vacía.
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="") or (
    f"La Sala de Bygui <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "La Sala de Bygui <no-reply@lasaladebygui.local>"
)

# --- APIs externas (usadas a partir de la Fase 3) ------------------------

TMDB_API_KEY = env("TMDB_API_KEY", default="")
OMDB_API_KEY = env("OMDB_API_KEY", default="")

# --- Notificaciones push (Web Push / VAPID) -------------------------------
# Se generan una sola vez con `python manage.py generate_vapid_keys` y se
# guardan como variables de entorno (nunca en el código). Si faltan, el
# sitio sigue funcionando con normalidad — simplemente no se envía ningún
# push (apps.core.push.send_push_to_user no hace nada sin credenciales).
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", default="")
# El PEM se guarda en una variable de entorno como una sola línea con "\n"
# literales (así lo imprime generate_vapid_keys); aquí se convierten de
# vuelta a saltos de línea reales, que es lo que espera el formato PEM.
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="").replace("\\n", "\n")
VAPID_CONTACT_EMAIL = env("VAPID_CONTACT_EMAIL", default="contacto@lasaladebygui.local")

# --- Integración real con Google Calendar (OAuth) --------------------------
# Vacías = el botón "Conectar con Google Calendar" del perfil no aparece y
# el resto del sitio sigue funcionando igual (los eventos del calendario de
# Top Secret se siguen pudiendo descargar como .ics de todas formas). Hacen
# falta un proyecto en Google Cloud y unas credenciales OAuth "Aplicación
# web" — ver README, sección de despliegue.
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")
GOOGLE_OAUTH_CLIENT_SECRET = env("GOOGLE_OAUTH_CLIENT_SECRET", default="")

# --- Identidad del sitio --------------------------------------------------

SITE_NAME = "La Sala de Bygui"

if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Panel de administración (django-jazzmin) ----------------------------
# Deliberadamente NO usa el tema visual de la propia web (theme.css): es un
# panel de control "de verdad", con su propio aspecto profesional, para que
# quede claro que es una herramienta distinta de la web pública. El acceso
# ya está restringido a Admin (is_superuser) en apps/core/apps.py — Jazzmin
# solo cambia el aspecto, no los permisos.

JAZZMIN_SETTINGS = {
    "site_title": "Panel — La Sala de Bygui",
    "site_header": "La Sala de Bygui",
    "site_brand": "Panel de control",
    "welcome_sign": "Panel de administración de La Sala de Bygui",
    "copyright": "La Sala de Bygui",
    "show_sidebar": True,
    "navigation_expanded": True,
    "changeform_format": "horizontal_tabs",
    # Botón bien visible para volver a la web pública (además del enlace
    # "Ver sitio" que Django ya pone en el desplegable de usuario).
    "topmenu_links": [
        {"name": "← Volver a la web", "url": "core:home", "new_window": False},
    ],
    "custom_css": "css/admin_custom.css",
    # Bloques del menú lateral, en este orden: Artículos, Foro, Películas,
    # Amigos y mensajes, Juegos, Tienda, Top Secret, Usuarios, Sitio y por
    # último Autenticación (Django). Dentro de cada bloque, los propios
    # modelos se ordenan con las entradas "app_label.ModelName" más abajo
    # en esta misma lista.
    "order_with_respect_to": [
        "articles", "articles.Article", "articles.Tag", "articles.ArticleView", "articles.ArticleComment",
        "forum", "forum.Thread", "forum.ThreadComment", "forum.ThreadRead",
        "movies", "movies.Movie", "movies.SavedMovie", "movies.SavedMovieList",
        "movies.Vote", "movies.RouletteRatingSeen", "movies.RouletteSavedSeen",
        "social",
        # Juegos, agrupados por tipo — igual que en el propio hub de
        # Juegos (/juegos/): primero los de un jugador (racha), luego el
        # test de personalidad, luego las herramientas compartidas
        # (tier list, Candidatos al Oscar), y por último los duelos.
        "games",
        "games.MovieQuote", "games.TriviaQuestion", "games.TrueFalseStatement",
        "games.PersonalityCharacter", "games.PersonalityQuestion",
        "games.GameTierLevel", "games.GameTierEntry",
        "games.OscarCategory", "games.OscarCandidate", "games.OscarVote",
        "games.Duel", "games.DuelRecord",
        "shop",
        "secret", "secret.SecretMovie", "secret.Genre",
        "secret.TierListEntry", "secret.TierLevel",
        "secret.SecretPhoto", "secret.PhotoBoardMember",
        "secret.ReleaseEvent", "secret.CalendarDayNote",
        "secret.TopSecretConfig",
        "accounts",
        "core",
        "auth",
    ],
    "icons": {
        "accounts.User": "fas fa-user",
        "auth.Group": "fas fa-users-cog",
        "articles.Article": "fas fa-newspaper",
        "articles.Tag": "fas fa-tags",
        "forum.Thread": "fas fa-comments",
        "forum.ThreadComment": "fas fa-comment-dots",
        "movies.Movie": "fas fa-film",
        "movies.Vote": "fas fa-star",
        "movies.SavedMovie": "fas fa-bookmark",
        "games.MovieQuote": "fas fa-quote-right",
        "games.Duel": "fas fa-swords",
        "shop.Product": "fas fa-store",
        "secret.TopSecretConfig": "fas fa-key",
        "secret.SecretMovie": "fas fa-user-secret",
        "secret.TierListEntry": "fas fa-layer-group",
        "secret.SecretPhoto": "fas fa-images",
        "secret.Genre": "fas fa-icons",
        "social.FriendRequest": "fas fa-user-friends",
        "social.Message": "fas fa-envelope",
        "core.SiteConfig": "fas fa-sliders-h",
        "core.Theme": "fas fa-palette",
        "core.ContactLink": "fas fa-share-alt",
    },
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
}

JAZZMIN_UI_TWEAKS = {
    "theme": "flatly",
    "default_theme_mode": "auto",
    "navbar_fixed": True,
    "layout_boxed": False,
    "sidebar_fixed": True,
}
