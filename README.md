# La Sala de Bygui

Web de cine: artículos, foro de debate, recomendador de películas y una sección secreta.
Construida con Django + plantillas DTL, pensada para desplegarse en Render con Supabase (Postgres) como base de datos.

**Estado actual: Fase 5 (completa) — las 5 fases del proyecto están entregadas:** estructura base y Supabase, autenticación con roles, tema visual editable, tablón de artículos, foro de debate, ruleta de recomendaciones (TMDb/OMDb), votaciones, Top Secret, donaciones, contacto, animación de proyector al entrar y despliegue en Render.

## Stack

- **Backend:** Python + Django. Panel de administración con **django-jazzmin** (aspecto propio de panel de control, restringido al rol Admin) y almacenamiento de imágenes en **Supabase Storage** (opcional, vía `django-storages`) para que sobrevivan a los redeploys.
- **Base de datos:** Supabase (Postgres) vía `DATABASE_URL`. En local, si no se configura, se usa SQLite automáticamente. **En producción (`DEBUG=False`) ese fallback está desactivado a propósito:** si `DATABASE_URL` falta ahí, la app no arranca (`ImproperlyConfigured`) en vez de caer en silencio a SQLite sobre el disco efímero de Render, que se borra en cada reinicio y perdería todo lo guardado.
- **Frontend:** plantillas de Django + CSS/JS vanilla. Alpine.js (vía CDN) para interacciones ligeras (toggle de respuesta en el foro, animación de la ruleta) y HTMX (vía CDN) para la búsqueda de películas y el voto sin recargar la página.
- **Editor de artículos:** CKEditor 5 (`django-ckeditor-5`).
- **Películas:** TMDb (búsqueda, portadas, sinopsis) + OMDb (nota IMDb).
- **Estáticos:** WhiteNoise (listo para producción; en local Django los sirve directamente).
- **Despliegue:** Render (plan free), vía `render.yaml`. Servidor de aplicación: gunicorn.
- **Idioma:** español (`LANGUAGE_CODE = 'es-es'`).

## Estructura de carpetas

```
bygui/
├── config/                # Settings, urls, wsgi/asgi
├── apps/
│   ├── accounts/           # Usuario personalizado, roles, login/registro, perfil
│   ├── core/                # Home, temas visuales (theme.css), configuración del sitio
│   ├── articles/            # Tablón de artículos (CRUD, tags, comentarios)
│   ├── forum/                # Foro de debate (hilos, árbol de comentarios, moderación)
│   ├── movies/                # Catálogo, ruleta (TMDb/OMDb) y votaciones
│   ├── secret/                # Top Secret: maletín Tarantino, código de acceso, lista personal
│   ├── social/                # Buscador de usuarios, amigos y mensajería privada
│   ├── games/                 # Frases célebres y Duelos
│   └── shop/                  # Tienda: escaparate de artículos
├── templates/               # base.html + plantillas por app
├── static/
│   ├── css/main.css         # Estilos estructurales (usan las variables de theme.css)
│   └── img/                 # Logo e iconos SVG
├── media/                    # Portadas de artículos e imágenes subidas desde el editor (no versionado)
├── docs/design-refs/        # Bocetos/mockups de referencia (no forman parte de la app)
├── requirements.txt
├── render.yaml               # Blueprint de despliegue en Render
├── .env.example
└── manage.py
```

## 1. Instalación local

Requisitos: Python 3.11+ (probado con 3.14).

```bash
py -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

copy .env.example .env       # Windows
# cp .env.example .env       # Linux/Mac
```

Edita `.env` si quieres apuntar a Supabase (ver sección 2); si dejas `DATABASE_URL` vacío, el proyecto usa SQLite local sin configuración adicional.

```bash
python manage.py migrate
python manage.py createsuperuser      # tu propio usuario Admin
python manage.py seed_content         # opcional: usuarios de ejemplo + artículos + hilos de foro + Top Secret
python manage.py seed_movies          # opcional pero recomendado: puebla el catálogo de películas desde TMDb/OMDb (necesita las API keys, ver sección 3)
python manage.py seed_series          # opcional: lo mismo pero para series
python manage.py runserver
```

Abre http://127.0.0.1:8000 — el panel de administración está en `/admin/`.

### Usuarios de ejemplo (`seed_demo`)

| Rol      | Email                          | Contraseña    |
|----------|---------------------------------|---------------|
| Admin    | admin@lasaladebygui.local       | Admin1234!    |
| Gestor   | gestor@lasaladebygui.local      | Gestor1234!   |
| Editor   | editor@lasaladebygui.local      | Editor1234!   |
| Lector   | lector@lasaladebygui.local      | Lector1234!   |
| Baneado  | baneado@lasaladebygui.local     | Baneado1234!  |

Son solo para pruebas locales — no ejecutes `seed_demo`/`seed_content` contra una base de datos de producción real. `seed_content` llama primero a `seed_demo` (por si no se había ejecutado) y luego crea 3 artículos, 2 hilos de foro y 4 películas de ejemplo en Top Secret, usando esos mismos usuarios como autores.

## 2. Configurar Supabase

1. Crea un proyecto en [supabase.com](https://supabase.com).
2. Ve a **Project Settings → Database → Connection string**, pestaña **URI**.
   Para Render (que no soporta IPv6 saliente en el plan free) usa el **Session pooler** o **Transaction pooler**, no la conexión directa.
3. Copia esa URL a `DATABASE_URL` en tu `.env`, con formato:
   ```
   DATABASE_URL=postgres://usuario:password@host:puerto/postgres
   ```
4. Ejecuta `python manage.py migrate` para crear las tablas en Supabase.

El proyecto usa el ORM y las migraciones estándar de Django; Supabase solo actúa como el Postgres gestionado.

## 3. Variables de entorno

Todas están documentadas en [.env.example](.env.example). Resumen:

| Variable | Para qué sirve |
|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta de Django. Genera una propia en producción. |
| `DEBUG` | `True` en local, `False` en producción. |
| `ALLOWED_HOSTS` | Dominios permitidos, separados por comas. |
| `DATABASE_URL` | Cadena de conexión de Supabase/Postgres. Vacío = SQLite local. |
| `EMAIL_*` | Configuración SMTP para verificación de email y contacto. En local, por defecto los emails se imprimen en la consola. |
| `REQUIRE_EMAIL_VERIFICATION` | Valor inicial de la opción "exigir verificación de email"; después se gestiona desde el admin (**Sitio → Configuración del sitio**). |
| `TMDB_API_KEY` / `OMDB_API_KEY` | Búsqueda/portadas/sinopsis (TMDb) y nota IMDb (OMDb) para el catálogo y la ruleta. Instrucciones abajo. |
| `SUPABASE_STORAGE_*` | Opcional: almacenamiento persistente de imágenes subidas (avatares, portadas...) en el Storage de Supabase. Vacío = disco local (no persistente en Render free). Instrucciones en la sección de despliegue. |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_CONTACT_EMAIL` | Claves de las notificaciones push (Web Push estándar). Genera un par nuevo con `python manage.py generate_vapid_keys`. Vacío = las notificaciones quedan desactivadas sin afectar al resto del sitio. |
| `RENDER_EXTERNAL_HOSTNAME` | La rellena Render automáticamente en producción. |

### Obtener las API keys de películas

- **TMDb:** crea una cuenta en https://www.themoviedb.org/, ve a *Configuración → API* y solicita una clave (uso gratuito, no comercial).
- **OMDb (nota IMDb):** solicita una clave gratuita en https://www.omdbapi.com/apikey.aspx (el plan gratuito permite 1000 peticiones/día). Se documenta esta elección porque IMDb no ofrece una API pública oficial; OMDb expone su nota (`imdbRating`) de forma gratuita para uso personal.

Sin estas dos claves, el catálogo de películas queda vacío (no hay fallback ni datos de ejemplo hardcodeados: todo viene de TMDb/OMDb).

## 4. Roles y permisos

### Registro (`/cuenta/registro/`)

Al crear la cuenta se pide **nombre de usuario** (además de email y contraseña) — es el nombre por el que te va a poder encontrar cualquiera en el buscador de Social (sección 10), así que no se genera solo a partir del email como antes. Se valida que sea único (sin distinguir mayúsculas/minúsculas) y que solo tenga letras, números, puntos, guiones y guiones bajos (`RegisterForm.clean_username`, `apps/accounts/forms.py`). Los usuarios creados por comandos de gestión (`seed_demo`, admins añadidos a mano sin indicar uno) siguen generándolo automáticamente a partir del email si se deja en blanco (`User._generate_username`).

El modelo de usuario (`apps.accounts.User`) tiene un campo `role` con 5 valores. El rol determina automáticamente `is_active`/`is_staff`/`is_superuser` al guardar el usuario:

| Rol | Acceso al `/admin/` | Puede hacer |
|---|---|---|
| **Admin** | Sí, control total (`is_superuser`) | Todo: gestionar usuarios, artículos y foro (de cualquier autor), configuración del sitio, tema visual, número de Bizum, email de contacto y el contenido de Top Secret (código de acceso y lista numerada). |
| **Gestor** | Sí (staff) — además tiene permisos Django sobre el **foro** (Hilos y Comentarios de foro), así que puede gestionarlo también desde `/admin/`, no solo desde la web pública. | Igual que Admin en moderación de contenido: editar/eliminar cualquier artículo, cerrar/eliminar cualquier hilo del foro y borrar cualquier comentario. No accede a ajustes globales de Django ni a la configuración del sitio. |
| **Editor** | Sí (staff), pero sin permisos Django asignados — hoy por hoy gestiona sus artículos desde la web pública, no desde `/admin/`. | Crear artículos; editar o eliminar únicamente los suyos. Participa en el foro como cualquier usuario logueado. |
| **Lector** | No | Rol por defecto al registrarse: leer y comentar artículos, abrir hilos y responder en el foro (con posibilidad de borrar sus propios comentarios), usar la ruleta y votar películas. |
| **Baneado** | No | Cuenta desactivada (`is_active=False`): no puede iniciar sesión. Es un rol, no un flag aparte — "banear" es cambiar el rol a `Baneado`, y "desbanear" es devolverlo a `Lector`. |

Gestión desde el admin: **Usuarios → Usuarios**. La columna *rol* es editable en línea desde el listado, y hay acciones masivas "Banear usuarios seleccionados" / "Desbanear usuarios seleccionados". Al guardar un usuario como Gestor, `User._sync_gestor_group()` lo añade automáticamente a un grupo Django "Gestor" con permisos sobre el foro (y lo quita si deja de serlo) — no hace falta tocar Grupos/Permisos a mano.

**El baneo es inmediato, no solo preventivo:** si el usuario baneado ya tenía una sesión abierta en el navegador, no hace falta esperar a que caduque — `User.save()` detecta la transición a `Baneado` y borra al momento sus sesiones activas (`User._kick_active_sessions()`, busca en `django.contrib.sessions.models.Session` cuáles tienen su `_auth_user_id`). En su siguiente petición, Django ya no lo reconoce como logueado. Esto se dispara tanto al editar el rol en línea desde el listado como al usar la acción masiva "Banear usuarios seleccionados", porque ambos caminos acaban llamando a `user.save()`.

### Menú de navegación

El desplegable de la cabecera empieza con **Sala principal** (enlaza a `/`) y sigue con: Artículos, Foro, Social (solo si has iniciado sesión), Películas, Juegos, Tienda, Top Secret y, al final, **Panel** — pero este último enlace a `/admin/` solo lo ve el **Admin** (`user.is_superuser`), no Gestor ni Editor.

**Volver al inicio sin abrir el desplegable:** justo al lado del botón "☰ Menú" (fuera del propio desplegable, así que siempre está visible) hay un enlace "Volver al menú" que lleva directamente a `/` — en cualquier página menos en la propia home (`templates/base.html`, `.nav-home-link` en `main.css`).

### El panel de administración (`/admin/`) — solo para el Admin

`/admin/` está restringido de verdad al rol Admin: Gestor y Editor son `is_staff` internamente (para tener permisos Django puntuales, como el Gestor con el foro — ver más abajo), pero **no pueden entrar a `/admin/` aunque escriban la URL a mano**. Esto se hace sobrescribiendo `admin.site.has_permission` en `apps/core/apps.py` (`CoreConfig.ready()`) para exigir `is_superuser` en vez del `is_staff` que usa Django por defecto; no afecta a los permisos Django reales de Gestor sobre el foro, solo a si puede entrar al panel a usarlos.

El panel usa **django-jazzmin** para un aspecto de panel de control "de verdad" (menú lateral con iconos por sección, tema propio) en vez del estilo de la propia web — es una herramienta de trabajo distinta de la web pública, así que deliberadamente no comparte su identidad visual. Se configura en `JAZZMIN_SETTINGS`/`JAZZMIN_UI_TWEAKS` (`config/settings.py`): orden de las secciones del menú, iconos por modelo, tema Bootswatch "flatly". Arriba del todo hay un botón bien visible "← Volver a la web" (`topmenu_links`) para salir del panel sin tener que usar el desplegable de usuario.

`static/css/admin_custom.css` (cargado vía `JAZZMIN_SETTINGS["custom_css"]`) son pequeños retoques sobre el tema de jazzmin/AdminLTE — por ahora, que el widget "Recent actions" del dashboard envuelva el texto largo (usernames/emails largos en `object_repr`) en vez de salirse de su tarjeta.

**Nota técnica — por qué los estáticos usan `CompressedStaticFilesStorage` y no `CompressedManifestStaticFilesStorage`:** jazzmin referencia `vendor/bootswatch` como un prefijo de ruta (para componer `<tema>/bootstrap.min.css` en JS), no como un archivo real. El storage "Manifest" de Django/whitenoise (el que añade un hash al nombre de cada archivo para que el navegador no cachee versiones viejas tras un deploy) intenta resolver esa ruta contra su manifiesto y no la encuentra, y **eso rompía todo `/admin/` con un 500** (`ValueError: Missing staticfiles manifest entry for 'vendor/bootswatch'`) en producción (`DEBUG=False`) — en local no se notaba porque con `DEBUG=True` se usa el storage simple, sin manifiesto. La variante sin manifiesto sigue comprimiendo los estáticos (gzip) pero no les añade hash al nombre; el único coste es que, tras desplegar un cambio de CSS/JS, quien tenga la página ya cacheada por el navegador puede necesitar refrescar sin caché (Ctrl+F5) para ver el cambio — no vuelvas a `CompressedManifestStaticFilesStorage` sin resolver antes este problema de jazzmin.

### Nombre coloreado por rango

En cualquier sitio donde aparece un nombre de usuario (cabecera, autoría de artículos, autoría de hilos y comentarios del foro), se pinta según su rol — así se distingue el rango de un vistazo. Se genera con el template tag `{% username_badge usuario %}` (`apps/accounts/templatetags/accounts_extras.py`) y los colores viven en `static/css/main.css`:

| Rol | Color |
|---|---|
| Admin | Rosa (`#EC4899`) |
| Gestor | Rojo (`#DC2626`) |
| Editor | Verde (`#16A34A`) |
| Lector | El color de texto normal del tema activo (no un blanco fijo: en el tema Vintage, de fondo claro, un blanco literal sería casi invisible) |

### Verificación de email

Es opcional y se activa/desactiva desde **Sitio → Configuración del sitio → "exigir verificación de email al registrarse"**. Cuando está activada, el registro sigue dejando entrar al usuario de inmediato (no se bloquea el login para evitar que un fallo de envío de email deje a alguien fuera de su cuenta), pero se le envía un email de confirmación y se marca `email_verified`. Esa marca se podrá usar en fases futuras para restringir acciones (comentar, votar, etc.).

### Recuperar contraseña

Desde `/cuenta/login/` hay un enlace "¿Olvidaste tu contraseña?" que usa las vistas estándar de Django (`PasswordResetView` y compañía) con plantillas propias a juego con el resto del sitio: pide el email, envía un enlace de un solo uso (caduca a los 3 días, por defecto de Django) y permite fijar una contraseña nueva. Por seguridad, pedir el reset para un email que no existe en la base de datos muestra el mismo mensaje que si sí existiera (no revela si una cuenta está registrada), y un usuario **Baneado** no recibe el email (su cuenta está inactiva).

### Perfil de usuario (`/cuenta/perfil/`)

Cada usuario puede subir una foto de perfil (`User.avatar`), visible en su propia página y en su perfil público junto a su nombre coloreado por rango. El tema visual **ya no se cambia aquí** — se movió al icono 🌙 de la cabecera (ver sección 5).

**Recorte de la foto de perfil:** al elegir una imagen se abre un editor de encuadre (`static/js/avatar_cropper.js`, sin dependencias externas) sobre un lienzo circular: se puede arrastrar la imagen para reposicionarla y hay una barra para hacer zoom. Al pulsar "Aplicar recorte" se dibuja la selección en un `<canvas>` oculto (480×480), se convierte a un `Blob`/`File` con `canvas.toBlob` y se inyecta en el campo de archivo real del formulario mediante `DataTransfer` — así el recorte ya se sube como si el usuario hubiera seleccionado directamente esa imagen cuadrada, sin tocar nada en el backend (`ProfileForm` sigue recibiendo un `ImageField` normal).

**Frase de perfil dinámica:** el antiguo campo de texto libre ("frase mítica de cine") se sustituyó por una frase que rota sola cada 6 segundos, tomada del mismo pool que usa el juego Frases célebres (`apps.games.models.MovieQuote`) — así el pool crece automáticamente si se añaden frases nuevas al juego, sin mantener dos listados. Se ve tanto en tu propio perfil como en el perfil público de cualquier otro usuario (`templates/partials/rotating_quote.html` + `static/js/rotating_quote.js`): cada carga de página empieza en una frase al azar y rota por todo el pool.

**🎬 Mis imprescindibles y ✨ Sugeridas** (`apps.accounts.models.FavoriteMovie`): dos botones en el propio perfil, cada uno lleva a su **página propia** (no pestañas en la misma pantalla) — `/cuenta/favoritas/essential/` y `/cuenta/favoritas/suggested/`. Ahí dentro, un único buscador con el mismo selector **Películas / Series / Ambas** que el catálogo — no dos cajas de búsqueda separadas, todo en una (el filtro de tipo es cliente, con Alpine, no recarga la página). **Sin límite de cuántas puedes añadir** en ninguno de los dos apartados. Reutiliza el catálogo de `apps.movies` (misma búsqueda en vivo contra TMDb que la tier list de Top Secret: escribes, salen resultados de los dos tipos a la vez, le das a "Añadir"). Cada tarjeta tiene botones ◀ ✕ ▶ para reordenarla dentro de su grupo (película/serie) y, pulsando el propio póster, se abre un cuadro para explicar **por qué está ahí** (`FavoriteMovie.note`, hasta 280 caracteres, con un 💬 de aviso si ya tiene una) — disponible tanto en Imprescindibles como en Sugeridas. Solo puedes editar las tuyas; en el perfil público de otro usuario (`/social/usuarios/<username>/favoritas/<categoría>/`) se ven en modo solo lectura, notas incluidas y visibles para cualquiera que entre.

**🔔 Notificaciones push:** el botón "Activar notificaciones" pide permiso al navegador y registra la suscripción (Web Push estándar, con claves VAPID — `apps.core.push`) para avisar de artículos nuevos, respuestas en el foro y mensajes en Social, incluso con la web cerrada (en Android/escritorio directamente; en iPhone, solo si la web está instalada como app — ver sección 11). Si el sitio no tiene configuradas `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`, el botón no aparece y el resto del sitio funciona igual.

Al final de la página hay un botón **"Cerrar sesión"**, además del que ya había en el desplegable de la cabecera.

## 5. Sistema de temas (`theme.css`)

Los colores, tipografías y espaciados **no están hardcodeados**: cada tema es una fila del modelo `Theme` (`apps.core.models.Theme`), y sus valores se sirven dinámicamente en `/theme.css` como variables CSS genéricas (`--color-accent`, `--color-bg`, `--font-heading`, etc.). El resto de los estilos, en `static/css/main.css`, consume esas variables — nunca un color a pelo — así que un tema nuevo no requiere tocar CSS ni plantillas.

Vienen 3 temas precargados (vía migración de datos, `apps/core/migrations/0002_seed_themes.py`):

| Tema | Estilo |
|---|---|
| **Cinephile** (por defecto) | Teal + ámbar sobre fondo oscuro. |
| **Noir** | Negro/gris carbón + rojo sangre, alto contraste, cine negro. |
| **Vintage** | Verde menta/salvia pastel con acentos crema y marrón, retro. |

**Selector en la cabecera:** el icono 🌙 (arriba, junto al logo) abre un desplegable con todos los temas disponibles. Al elegir uno se aplica al instante, sin recargar ni pasar por ningún botón "guardar" — funciona incluso sin haber iniciado sesión (se guarda en la sesión del navegador); si estás logueado, se guarda en tu cuenta y aparece la opción "Usar tema del sitio" para volver al tema activo global.

**Cómo se elige el tema que ve cada visitante** (`apps.core.models.get_effective_theme`):
1. Si el usuario ha iniciado sesión y eligió un tema desde el icono 🌙, se usa ese (guardado en su cuenta).
2. Si no ha iniciado sesión pero eligió uno desde el icono 🌙, se usa el guardado en su sesión de navegador.
3. Si no, se usa el "tema activo" del sitio (**Admin → Sitio → Configuración del sitio → tema activo**).
4. Si tampoco hay uno configurado, se cae a Cinephile por su slug, y como último recurso a los valores por defecto del modelo.

**Cambiar el tema de toda la web:** entra en `/admin/`, ve a **Sitio → Configuración del sitio** y cambia el campo *tema activo*. No hace falta tocar código ni volver a desplegar.

**Añadir un tema nuevo:** ve a **Sitio → Temas visuales → Añadir tema visual**, rellena colores (con selector de color nativo), tipografías y espaciados, y guarda. Aparecerá disponible tanto en el selector de "tema activo" del sitio como en el icono 🌙 de cualquier visitante. Cada tema define: fondo, superficie, bordes, texto primario/secundario, acento principal (+ hover + color de texto sobre él), acento secundario (+ hover + color de texto sobre él), y los estados de error/éxito.

Si un tema nuevo necesita una tipografía de Google Fonts que no esté entre las ya cargadas (Playfair Display, Bebas Neue, Special Elite, Inter), hay que añadir esa fuente al `<link>` de Google Fonts en `templates/base.html` — es el único caso que sí toca una plantilla.

## 6. Artículos y foro

### Tablón de artículos (`/articulos/`)

CRUD completo respetando los permisos de la tabla de roles anterior. El cuerpo se escribe con **CKEditor 5** (negrita, enlaces, listas, imágenes, tablas...); las imágenes que se suban desde el editor requieren `is_staff` (Admin/Gestor/Editor). Los tags se escriben como texto separado por comas y se crean sobre la marcha si no existen; al borrar un artículo, sus tags se borran también salvo que otro artículo los siga usando (así no se acumulan tags huérfanos, pero tampoco se rompe un tag compartido). Cada ficha de artículo enlaza además a los **5 últimos artículos** publicados (excluyéndose a sí misma), para no depender solo del listado para seguir navegando. Los comentarios al pie solo son visibles/escribibles por usuarios logueados; cualquiera puede leer los artículos sin cuenta. Publicar un artículo nuevo notifica por push (sección 11) a todos los usuarios suscritos, salvo al propio autor.

**Imágenes dentro del texto, no solo la portada:** desde la barra de CKEditor se puede insertar una imagen en cualquier punto del cuerpo (donde esté el cursor, o arrastrándola a otro punto del texto para moverla), cambiarle el tamaño (dropdown `resizeImage`: original/50%/75%, o arrastrando la esquina) y alinearla a la izquierda/centro/derecha (`imageStyle`); el tamaño del texto se controla con el desplegable "heading" (títulos H1/H2/H3 o texto normal). Alinear a un lado es lo que hace que el texto la rodee — eso lo da el CSS de `.richtext` (`config/settings.py::CKEDITOR_5_CONFIGS` + `.richtext .image-style-align-left/right` en `static/css/main.css`, con `float` y un margen alrededor); sin esas reglas CKEditor guarda la alineación pero no se vería ningún efecto visual en la web pública. En móvil las imágenes alineadas a un lado pasan a ocupar todo el ancho (no flotan) para no dejar columnas de texto demasiado estrechas.

**El propio editor ya se ve como la página final, sin pasos de vista previa aparte:** el área de edición de CKEditor (`.ck-content`) reutiliza el mismo fondo, color de texto, tipografía de títulos y estilos de imagen/cita que la página pública del artículo (mismas reglas de `.richtext` aplicadas también a `.ck-content` en `main.css`) — así, mientras escribes, mueves imágenes o cambias tamaños, ya estás viendo (aproximadamente) el resultado final, y puedes seguir ajustando todo lo que haga falta antes de pulsar "Publicar"/"Guardar cambios". El formulario de escribir/editar usa además el ancho completo (`wrap`, no `wrap--narrow`), y la caja de escritura en sí (`.ck-editor__editable`) se muestra como una "hoja" separada del fondo (ancho limitado, centrada, con sombra) con más aire por dentro — para que se sienta como escribir en un procesador de texto (Word/Docs) y no como rellenar un formulario estrecho. La barra de herramientas es una de "doc" de verdad (`config/settings.py::CKEDITOR_5_CONFIGS`): negrita/cursiva/subrayado/tachado, color de texto y de resaltado, alineación de párrafo, listas (con viñetas, numeradas y de tareas ☑), sangría, cita, tablas, línea horizontal, buscar y reemplazar, y **`insertImage`** en vez del antiguo botón de solo-subida — permite insertar una imagen (desde el ordenador o por URL) en cualquier punto del texto, entre dos frases cualesquiera, no solo al final. También incluye `mediaEmbed`: pegar un enlace de YouTube/Vimeo lo convierte automáticamente en un reproductor embebido.

**Portada con recorte interactivo:** en vez de un simple `<input type="file">` que luego se recortaba a lo bruto en la web pública (`object-fit: cover` cortando la imagen de cualquier manera), el campo "Portada" abre el mismo tipo de editor de recorte que ya existía para el avatar del perfil (`static/js/cover_cropper.js`, Alpine.js + `<canvas>`, sin librerías externas) — pero en formato panorámico 16:9 en vez de cuadrado, la misma proporción con la que se muestra la portada en la página del artículo. Arrastra para encuadrar y usa el deslizador para hacer zoom antes de aplicar el recorte; lo que ves ahí es exactamente lo que se sube y se publica, sin sorpresas.

### Foro de debate (`/foro/`)

Cualquier usuario logueado (no baneado) puede abrir un hilo o responder, a cualquier profundidad: los comentarios se guardan con un `parent` opcional y la vista arma el árbol completo en memoria (una sola consulta por hilo, sin problema N+1) antes de pintarlo de forma recursiva, indentado como en Reddit. En el listado (`/foro/`), toda la fila de cada hilo es clicable (no solo el título) — el título y los metadatos van dentro de un único `<a>` que ocupa toda la fila.

**Moderación (Gestor/Admin):** pueden cerrar un hilo (deja de admitir respuestas nuevas, ya publicadas se conservan) o eliminarlo por completo, y borrar cualquier comentario. El propio autor también puede borrar su comentario. Borrar un comentario es un **borrado lógico** (queda como "[comentario eliminado]") para no romper las respuestas que cuelguen de él; eliminar un hilo sí borra todo en cascada.

**Doble borrado (Gestor/Admin):** sobre un comentario que ya está en "[comentario eliminado]", un Gestor o Admin ve un segundo botón, "Eliminar definitivamente", que esta vez sí lo borra de la base de datos sin posibilidad de deshacerlo. El autor del comentario no tiene este segundo paso, solo el borrado lógico.

Responder a un hilo notifica por push (sección 11) a quien corresponda: al autor del comentario padre si es una respuesta anidada, o al autor del hilo si es una respuesta de primer nivel — nunca a ti mismo si te respondes a tu propio hilo/comentario.

### Imágenes y almacenamiento

Las portadas de artículo y las imágenes subidas desde CKEditor se guardan en `media/` (disco local). **En el plan free de Render el disco no es persistente entre despliegues/reinicios** — las imágenes subidas en producción pueden desaparecer al redeployar (ver la nota en la sección de despliegue, más abajo, con las opciones para evitarlo). Para desarrollo local no hay ningún problema.

## 7. Catálogo, ruleta y votaciones (`/peliculas/`)

### Catálogo local y las dos APIs

Cada película se cachea una sola vez en el modelo `Movie` (`apps.movies.models.Movie`), identificada por su `tmdb_id`: título, año, portada y sinopsis vienen de **TMDb**; la nota IMDb se resuelve una vez vía **OMDb** (a partir del `imdb_id` que TMDb expone en `external_ids`) y se guarda en `imdb_rating`. Ni la ruleta ni las votaciones vuelven a golpear las APIs externas para una película ya cacheada.

`python manage.py seed_movies` (opcional `--pages N`, por defecto 2) recorre "populares" y "mejor valoradas" de TMDb **y además tres franjas de `/discover/movie` por nota** (≤4, 4-6 y 6-7.5, cada una con un mínimo de votos para evitar títulos irrelevantes) para que el catálogo no quede sesgado hacia notas altas — si solo se usaran "populares"/"mejor valoradas", el Modo 1 de la ruleta se quedaría sin candidatas al elegir un rango de nota bajo. Resuelve la nota IMDb de cada película encontrada. Sin ejecutarlo, el catálogo empieza vacío y se va llenando según los usuarios añaden películas a su lista en el Modo 2.

Si ya habías ejecutado `seed_movies` antes de este cambio y notas huecos en ciertos rangos de nota, vuelve a ejecutarlo (es idempotente: no duplica lo que ya existe) para completar el catálogo con las franjas nuevas.

**Buscar en `/peliculas/` no se limita al catálogo local:** si buscas un título que no está cacheado todavía, la página también consulta TMDb en vivo y muestra esos resultados en una sección aparte ("Más resultados"); al abrir uno se cachea igual que cualquier otra (título, portada, sinopsis y nota IMDb) y a partir de ahí ya cuenta para el Modo 1 de la ruleta y las votaciones.

**Scroll infinito en vez de paginación con números:** con el catálogo creciendo (seed_movies puede dejarlo en varias decenas de películas), pasar página a página con "1 2 3 ... 16" dejó de ser representativo. En su lugar, `/peliculas/` carga un primer tramo (24 películas) y, al llegar al final con el scroll, un "sensor" invisible (`hx-trigger="revealed"` de HTMX) pide el siguiente tramo y lo añade a la cuadrícula sin recargar la página — así hasta que no queden más. La vista (`apps.movies.views.movie_list`) detecta si la petición es HTMX para devolver solo el fragmento de esa página (sin repetir la búsqueda en vivo a TMDb en cada tramo, que solo se hace en la carga inicial).

Los dos modos de la ruleta están agrupados, junto con "Frases célebres", en un apartado **Juegos** (`/juegos/`, enlazado en el desplegable de la cabecera) — ver sección 9.

### Ruleta — Modo 1 (`/peliculas/ruleta/nota/`)

El usuario elige una nota mínima y máxima (1-10; el formulario empieza abierto a todo el rango, 1-10, y se estrecha solo si el usuario lo cambia); se sortea al azar una película del catálogo dentro de ese rango, excluyendo las que ya se le mostraron a ese usuario en ese modo (`RouletteRatingSeen`). Al agotar el rango, hay que darle a "reiniciar" para volver a verlas.

### Ruleta — Modo 2 (`/peliculas/ruleta/lista/`)

Gira directamente sobre tus **Guardadas** (`apps.movies.models.SavedMovie`) — no hay una lista de candidatas aparte que mantener: guardar una película desde su ficha ya la hace elegible aquí, sin ningún paso extra. "Girar" elige al azar una guardada que no hayas visto todavía en este modo y la marca como vista (`RouletteSavedSeen`, mismo patrón que `RouletteRatingSeen` del Modo 1); "reiniciar" las vuelve a poner todas disponibles.

Ambos modos muestran el resultado con una animación de carteles rotando (tipo tragaperras) antes de fijarse en la película elegida, hecha con Alpine.js sobre las portadas ya cacheadas — sin llamadas adicionales a las APIs.

### Votaciones

Cualquier usuario logueado vota una película del 1 al 10 desde su ficha (`/peliculas/<id>/`); un segundo voto sobre la misma película sobreescribe el anterior (`unique_together` en `Vote` + `update_or_create`). Se muestra la media y el número de votos. El voto se envía por HTMX sin recargar la página. Hay también un botón **"Quitar nota"** (visible solo si ya has votado) que borra tu voto — al hacerlo, la película deja de aparecer en "Mis películas".

### Mis películas (`/peliculas/mias/`) y Guardadas (`/peliculas/guardadas/`)

Dos apartados separados, ambos enlazados desde la cabecera del catálogo (solo para usuarios logueados):

- **Mis películas:** solo lo que has votado, con tu nota.
- **Guardadas:** lo que has guardado desde la ficha de cualquier película (botón "Guardar película" / "✓ Guardada", `apps.movies.models.SavedMovie` — una fila única por usuario+película, pensado para marcar "quiero verla" sin necesidad de puntuarla todavía). Esta es la lista de la que tira el Modo 2 de la ruleta, de ahí que tenga su propio apartado en vez de ser una sección más dentro de "Mis películas". Tiene botones ▲/▼ para reordenarlas según su orden de importancia (`SavedMovie.order`).
  - **Listas** (`apps.movies.models.SavedMovieList`, ej. "Terror", "Para ver en familia"): creas las tuyas con "+ Nueva lista" y, en cada fila, un desplegable "🏷️ Listas" permite marcar/desmarcar en qué listas está esa guardada — **una misma guardada puede estar en varias a la vez** (`SavedMovie.sublists` es un ManyToMany, no una única FK); las que tiene asignadas se ven como etiquetas junto a la fila. Pensado para escalar a muchas listas (10+): el filtro de arriba y el desplegable de cada fila son colapsables (`<details>`) con scroll interno en vez de una fila de botones que se agolpen. Un filtro arriba de Guardadas (y de la ruleta Modo 2, mismo patrón `?list=<id>` o `?list=none`) permite ver solo "Todas", **"Sin listas"** (las que no están en ninguna) o una lista concreta. Borrar una lista no borra las películas, solo las deja fuera de ella.

### Series, además de películas

Todo el catálogo (búsqueda, ficha, guardadas, votaciones, imprescindibles/sugeridas del perfil) admite también series, no solo películas: `Movie.media_type` (`movie`/`tv`) distingue unas de otras — como los IDs de TMDb para películas y series son namespaces independientes, la unicidad real es la pareja `(tmdb_id, media_type)`, no `tmdb_id` a secas. En cada apartado hay un selector **Películas / Series / Ambas** que filtra tanto el catálogo local como la búsqueda en vivo contra TMDb (`/search/movie` o `/search/tv` según el caso); cambiar de tipo resetea el buscador de texto, no arrastra la búsqueda anterior de un tipo a otro. `python manage.py seed_series` (mismo patrón que `seed_movies`, sección "Instalación local") puebla el catálogo de series para que "Series" tenga contenido con el que scrollear desde el principio, en vez de aparecer vacío hasta que alguien busca y añade una a mano.

## 8. Top Secret, donaciones y contacto

### Top Secret — el maletín Tarantino (`/top-secret/`)

Acceso **independiente de las cuentas de usuario**: no hace falta estar registrado, solo conocer el código. Al entrar se muestra un maletín animado y un campo de código; si es correcto, se guarda un flag en la sesión (`request.session['top_secret_unlocked']`) que da acceso al resto de páginas de la sección hasta que se cierra sesión del navegador o se pulsa "Cerrar maletín".

El código **no se guarda en texto plano**: se hashea con el mismo mecanismo que las contraseñas de usuario (`django.contrib.auth.hashers`) en `TopSecretConfig.access_code_hash`. El código de fábrica es `8888`. Para cambiarlo: **Admin → Top Secret → Código de acceso**, campo "Nuevo código" — el admin nunca puede ver el código actual, solo fijar uno nuevo (igual que un campo de contraseña).

Dentro hay tres secciones, todas editables desde **Admin → Top Secret → Películas secretas** (cada entrada es un título + nota personal + comentario; opcionalmente se puede enlazar a una película del catálogo de `/peliculas/` para reutilizar su portada):

- **a) Selector numérico:** eliges un número de la lista y te devuelve la película asociada. **El número no se elige a mano: es la posición al ordenar todas por nota personal, de mayor a menor** (`SecretMovie._renumber_all`, se recalcula solo en cada guardado/borrado/cambio de nota — añadir una película con mejor nota desplaza a todas las que había debajo). Si dos entradas empatan a nota, se ordenan por el campo **"orden de desempate"** (0 por defecto): ahí es donde el admin puede decidir manualmente cuál va primero cuando la nota no basta para desempatar.
- **b) Buscador por nota:** un intervalo de nota *personal* (no la de IMDb ni la media de votos) y una recomendación al azar dentro de él. Cada entrada puede tener **géneros/subgénero** (`apps.secret.models.Genre`, tags de texto libre — se escriben separados por comas al editar la película en **Admin → Top Secret → Películas secretas**, campo "Géneros/subgéneros", y se crean sobre la marcha si no existen, igual que los tags de Artículos). En esta página aparecen como chips clicables: al pulsar uno se combina con el intervalo de nota, así que la recomendación al azar sale solo entre las películas de ese género y esa nota.
- **c) Lista completa:** todas las entradas, con su nota, géneros y comentario.
- **d) Otros** (`/top-secret/dentro/otros/`): agrupa la Tier list, el Tablón de fotos y el Calendario, apartados que no son "la lista numerada de Quentin" sino cosas aparte:
  - **Tier list:** un ranking de películas por niveles (`apps.secret.models.TierLevel` + `TierListEntry`). Los niveles **no son fijos**: nombre, color y orden se gestionan enteros desde la propia página del Tier List (un ✏️ junto a cada nivel abre un mini formulario de nombre+color; "+ Añadir nivel" crea uno nuevo al final; 🗑️ lo borra) — no hace falta tocar el admin para nada de esto, aunque también aparecen ahí (**Admin → Top Secret → Niveles de tier list**) por si se prefiere. Al borrar un nivel, sus películas no se pierden: vuelven a "Sin clasificar" (`on_delete=SET_NULL`). Añadir películas (buscador TMDb en vivo) y arrastrar y soltar (`static/js/tier_list.js`, drag-and-drop nativo del navegador, sin librerías) funciona igual que antes: cada entrada se coloca al final del nivel de destino, y las recién añadidas caen en **"Sin clasificar"** (fila con borde discontinuo, encima de los niveles reales) hasta que se arrastran a uno. Un botón **"Vaciar tier list"** (con confirmación) borra todas las entradas — no los niveles — para volver a empezar de cero.
  - **Tablón de fotos** (`/top-secret/dentro/tablon/`): a diferencia del resto de Top Secret, **esto sí se sube desde la propia web, no desde el admin** — cualquiera que haya entrado con el código puede subir una foto con una pequeña descripción (`apps.secret.models.SecretPhoto`). Si has iniciado sesión, puedes elegir con una casilla **"Publicar como anónimo"** si quieres que se guarde tu nombre (coloreado por rango) o no; sin cuenta, siempre se sube como "Anónimo" (no hay identidad que ocultar ni mostrar). Con estética de cine propia (carrete de 35mm: fondo oscuro, perforaciones arriba y abajo de cada foto, texto a máquina de escribir) en vez del tema visual activo del sitio, deliberadamente distinta para que se note que es "el cuarto oscuro" del maletín.
  - **Calendario** (`/top-secret/dentro/calendario/`, `apps.movies.models.ReleaseEvent`): qué película o serie toca cada fecha — **personal de cada usuario**: hace falta el código del maletín **y** haber iniciado sesión, y lo que añades no lo ve nadie más, ni siquiera otro con el mismo código. Se añade pulsando el número de un día del mes (revela una búsqueda en vivo ahí mismo, movie+series a la vez) en vez de un formulario fijo aparte; el 💬 del día deja además un comentario suelto sin ligarlo a ninguna película (`apps.movies.models.CalendarDayNote`). Cada evento muestra su portada y su título en la propia celda del día. El botón para conectar/desconectar **Google Calendar de verdad** (ver sección 11) vive aquí mismo, minimalista, arriba del mes — si lo tienes conectado, cada evento se crea solo en tu calendario (`ReleaseEvent.google_event_id`); si no, hay un botón para descargar su `.ics` a mano.

Nota: "Frases célebres" vivía antes aquí, como un juego más de Top Secret — se sacó al apartado **Juegos** (sección 9) para que jugarlo no dependa del código de acceso, y de paso a su propia app (`apps.games`) para que el admin la agrupe bajo "Juegos" en vez de bajo "Top Secret".

## 9. Juegos (`/juegos/`)

Apartado de acceso libre (ni cuenta ni código de Top Secret) que agrupa lo que antes estaba repartido entre el enlace "Ruleta" de la cabecera y la sección de Juegos de Top Secret — de ahí que ahora sea un único punto de entrada, enlazado como "Juegos" en el desplegable. Vive entero en `apps.games` (modelos, vistas, plantillas y el comando `seed_quotes`), app propia creada para esto: antes `MovieQuote` vivía en `apps.secret` (por eso aparecía bajo "Top Secret" en el admin) y las vistas en `apps.core` — la migración que las trasladó (`apps/secret/migrations/0007_delete_moviequote.py` + `apps/games/migrations/0001_initial.py`) usa `SeparateDatabaseAndState` para que sea solo un cambio de qué app "es dueña" del modelo, sin tocar ni un dato de la tabla física existente.

- **Ruleta** (`/peliculas/ruleta/`): los Modos 1 y 2 descritos en la sección 7.
- **Tu tier list** (`/juegos/tierlist/`, `apps.games.models.GameTierLevel` + `GameTierEntry`): un ranking **personal y privado** de cada usuario logueado — nada que ver con el Tier list de Top Secret (sección 8): ese es único y global, gestionado dentro del maletín; este es por cuenta, no se usa para duelos ni lo ve nadie más. Empieza con los niveles clásicos S/A/B/C/D (se crean solos la primera vez que entras), pero son **igual de editables** que los de Top Secret — nombre, color, añadir o borrar niveles, todo desde la propia página — solo que cada usuario tiene los suyos, sin compartir ninguno. Mismo patrón de búsqueda-y-añadir (TMDb en vivo) y arrastrar-y-soltar que el de Top Secret — de hecho comparten el mismo script (`static/js/tier_list.js`, generalizado con un atributo `data-tier-move-url-base` para apuntar a la vista de cada uno).
- **Frases célebres** (`/juegos/frases/`, **Admin → Juegos → Frases célebres**): la web muestra una frase de película y tres opciones (la correcta + dos incorrectas); aciertas y sigue la racha, fallas y se reinicia a 0. La racha en curso se guarda en la sesión del navegador; la **mejor racha** se guarda de forma permanente en la cuenta (`User.quote_streak_best`) si has iniciado sesión — y se muestra en tu página de perfil — o solo para esa sesión de navegador si entras sin cuenta. Al fallar se muestra una pantalla de fin de partida con la racha conseguida, un botón "Jugar de nuevo" y, si esa racha ha superado tu mejor marca anterior, un mensaje de felicitación.

  El pool de `seed_quotes` tiene **144 frases** (`apps/games/management/commands/seed_quotes.py`, con variedad de animación, terror, western y clásicos de todo tipo), revisadas para que sean completas (con el pronombre cuando la frase famosa lo lleva, ej. "Yo soy Iron Man." y no "Soy Iron Man.") y en castellano de verdad — sin dejar palabras sueltas en inglés colándose en medio de la frase (por eso, por ejemplo, la de *Duro de matar* se cambió por otra igual de reconocible). El comando también trae un pequeño mecanismo de corrección (`QUOTE_FIXES`): si una base de datos ya tenía sembradas versiones antiguas/incorrectas de alguna frase, `seed_quotes` las actualiza in situ la próxima vez que se ejecute (buscándolas por su texto anterior), en vez de dejarlas huérfanas junto a la versión corregida.

- **Duelos** (`/juegos/duelos/<username>/invitar/`, `/juegos/duelos/<id>/`, `apps.games.models.Duel`): reto 1 contra 1 **en directo** entre dos amigos (hace falta amistad aceptada en Social, sección 10), a elegir de entre varios juegos de trivia — Frases célebres, Trivial, Malas descripciones o Cuál tiene al actor/actriz (`Duel.game`, `apps.games.views.DUEL_GAMES` es el registro de qué modelo/campos usa cada uno; añadir un juego nuevo ahí es lo único que hace falta para que también se pueda retar a él). El punto de entrada es un botón **"🎮 Jugar con amigos"** al final de `/juegos/` (dentro de "🎯 Desafía a amigos"): eliges a quién retar y con qué juego de dos desplegables, y se manda la solicitud.
  - **Invitación con aceptación:** el duelo nace como `PENDING` — al amigo retado le llega automáticamente un **mensaje de Social** con el enlace directo (`apps.games.views.duel_invite` crea un `apps.social.models.Message`; el enlace sale clicable gracias al filtro `urlize` en `templates/social/conversation.html`). Hasta que no entra y pulsa "Aceptar" (o "Rechazar", que borra el duelo), no empieza la partida; mientras tanto, quien retó ve una pantalla de espera que se refresca sola cada 3s (`<meta http-equiv="refresh">`, sencillo y sin JavaScript).
  - **Misma pregunta, a la vez, hasta fallar:** no hay una tanda de tamaño fijo (no pone "pregunta X de 10") — igual que el modo en solitario, se juega hasta que alguien falla. `Duel.current_index` es **compartido**: los dos ven literalmente la misma pregunta al mismo tiempo, y `round_ids` va creciendo sobre la marcha (se añade una pregunta más del juego elegido cada vez que los dos aciertan la ronda actual) en vez de generarse entera de golpe. En cuanto uno responde, si acierta espera (pantalla que también se autorrefresca) a que el otro también responda esa ronda; cuando los dos han acertado, la ronda avanza para los dos a la vez. En el instante en que uno falla, el duelo termina ahí mismo **para los dos** (`challenger_lost`/`opponent_lost`) — no hace falta esperar a que el otro haga nada.
  - **Resultado, marcador y revancha:** al terminar se muestra "¡Has ganado!"/"Has perdido" según el resultado de quien mira la pantalla (`Duel.winner`). Ese resultado se apunta al instante en un marcador histórico por pareja de jugadores (`apps.games.models.DuelRecord`, victorias/derrotas/empates) — visible en el perfil público de un amigo ("⚔️ Duelos contra ti: ganaste X, perdiste Y"). El propio `Duel` **se borra** en cuanto cualquiera de los dos pulsa "Volver a Juegos" (`apps.games.views.duel_leave`, solo si ya ha terminado): el marcador ya quedó guardado aparte, así que no hace falta seguir acumulando duelos viejos en "Tus duelos". Un botón "Jugar de nuevo" pide revancha; hasta que **los dos** le dan, no se reinicia (`Duel.reset_for_rematch()`: nueva pregunta al azar del mismo juego, rachas y ronda a cero, mismo `Duel` reutilizado en vez de crear uno nuevo).

## 10. Social: buscador, amigos y mensajes (`/social/`)

`/social/` es la página central del apartado social (enlazada como "Social" en el desplegable de la cabecera), con dos cosas a la vez: un **buscador de usuarios por nombre** (`?q=...`, coincidencia parcial, para encontrar a cualquiera aunque nunca haya escrito en el foro) y la lista de **tus chats** (conversaciones existentes, con cuántos mensajes sin leer hay en cada una). En cada chat de la lista, su foto de perfil (en redondo, `.profile-avatar--sm`, con el mismo emoji de fallback 🎬 que el resto del sitio si no tiene) lleva al perfil público de esa persona (para ver su racha, el marcador de duelos contra ti, etc.) y el nombre lleva a la conversación — dos destinos distintos a propósito, ya que dentro de la propia conversación no hace falta ese enlace de nuevo.

Desde el buscador (o desde los nombres de autor del foro, que también enlazan al perfil) se llega al perfil público de cualquiera (`/social/usuarios/<username>/`), donde se puede enviar una solicitud de amistad. Si el otro usuario ya te había enviado una solicitud pendiente, aceptarla en ese momento os hace amigos directamente en vez de crear una segunda solicitud cruzada. `/social/amigos/` (enlazado desde la página Social, con un contador de solicitudes pendientes) lista solicitudes recibidas/enviadas y tus amigos actuales, con opción de eliminar la amistad.

La mensajería está **limitada a amigos**: solo se puede abrir o escribir en una conversación con alguien con quien ya existe una amistad aceptada (`apps.social.models.FriendRequest` con `accepted=True`); intentarlo con quien no es amigo da 404. Al abrir una conversación, los mensajes recibidos se marcan como leídos.

Cada mensaje propio tiene un enlace **"Editar"** (despliega un formulario en el sitio, sin JavaScript, con `<details>`/`<summary>`) y un botón **"Borrar"** directamente en la conversación; solo el autor del mensaje puede editarlo o borrarlo (`apps.social.views.message_edit`/`message_delete` comprueban `sender=request.user`, si no da 404). Enviar un mensaje notifica por push (sección 11) al destinatario.

### Tienda (`/tienda/`)

Escaparate puro: se muestran los artículos que ponga el admin (**Admin → Tienda → Artículos**: nombre, descripción, imagen, precio orientativo y un enlace externo opcional), sin carrito ni botón de compra de ningún tipo — es para enseñar cosas (merchandising, deseos...), no para venderlas. Vive en su propia app (`apps.shop`).

### Donaciones (`/donaciones/`)

Cartel estilo cine antiguo con el número de Bizum. El número no está hardcodeado: vive en `SiteConfig.bizum_number` (**Admin → Sitio → Configuración del sitio → Donaciones**) y por defecto trae el que se indicó en el encargo (684 127 181).

### Contacto (`/contacto/`)

Formulario (nombre, email, mensaje) que se envía por email a `SiteConfig.contact_email` (**Admin → Sitio → Configuración del sitio**). Anti-spam por **honeypot**: un campo (`website`) invisible por CSS que un usuario real nunca rellena; si llega relleno, se descarta el envío mostrando igualmente el mensaje de éxito (para no darle pistas a un bot de que fue detectado).

**Enlaces de contacto alternativos** (`apps.core.models.ContactLink`, **Admin → Sitio → Enlaces de contacto**): además del formulario por email, se pueden añadir tantos enlaces como se quiera a otras plataformas (Instagram, WhatsApp, Twitter/X, Telegram, Discord, Spotify...; "Otro" cubre cualquiera no listada). Cada uno tiene una plataforma (con su icono, un emoji — sin depender de ninguna librería de iconos), un texto a mostrar (ej. `@lasaladebygui`) y la URL a la que lleva al pulsarlo (perfil, `https://wa.me/34...`, `mailto:...`, etc.); se abren en pestaña nueva. Se muestran en `/contacto/` tanto si el email de contacto está configurado como si no, ya que son una vía aparte.

## 11. Instalar como aplicación (PWA)

La web se puede instalar como app (icono en el escritorio/pantalla de inicio, se abre en su propia ventana sin barra del navegador) gracias a un manifest (`static/manifest.json`, enlazado en `base.html`) y un service worker mínimo (`static/js/sw.js`, cachea el shell básico — CSS y el icono — para cumplir el requisito de instalabilidad, no pretende dar soporte offline completo del sitio).

**Importante — el service worker es "red primero, caché solo de respaldo" (`fetch` intenta la red y solo recurre a `caches.match` si falla), nunca al revés.** La primera versión era cache-first (`caches.match(...) || fetch(...)`) y eso hacía que, para quien ya tuviera el service worker instalado, `/` y `static/css/main.css` (los "shell assets") se quedaran congelados para siempre con la copia del primer día — **cualquier despliegue posterior era invisible para esos navegadores** aunque el servidor tuviera el código correcto (así se diagnosticó un caso real: la config de CKEditor en el servidor estaba perfectamente actualizada, comprobado con un endpoint de diagnóstico temporal, pero el navegador nunca llegaba a pedirla porque el service worker respondía desde una caché de hacía varios despliegues). Si esto se repite: súbele la versión a `CACHE_NAME` en `sw.js` (fuerza a que se trate como un archivo distinto y se reinstale) — y no vuelvas a un patrón cache-first para el HTML/CSS del shell sin un mecanismo de invalidación real. `pwa_install.js` también llama a `registration.update()` en cada carga para no depender de que el navegador revise solo (por defecto, hasta 24h) si hay una versión nueva del propio `sw.js`.

**El service worker se sirve en `/sw.js` (raíz), no en `/static/js/sw.js`:** el scope por defecto de un service worker es el directorio de su propia URL, así que si se sirviera desde `/static/js/` nunca podría controlar el resto del sitio. `apps.core.views.service_worker` (registrado en `config/urls.py`, fuera de cualquier prefijo de app) busca el archivo real con `django.contrib.staticfiles.finders.find` y lo sirve con el header `Service-Worker-Allowed: /`.

**El aviso de instalación no es invasivo** (`static/js/pwa_install.js`):
- Si el navegador detecta que ya está instalada (`display-mode: standalone` o `navigator.standalone` en iOS), no hace nada.
- Se muestra **como mucho una vez por sesión de navegador** (`sessionStorage`, se reinicia solo al cerrar la pestaña/navegador), y solo si el navegador ha disparado `beforeinstallprompt` (o sea, solo si de verdad se puede instalar). Si le das a "Ahora no", no vuelve a insistir hasta la próxima vez que entres.
- El banner (esquina inferior, con botones "Instalar" / "Ahora no") no bloquea nada de la página; al pulsar "Instalar" se lanza el diálogo nativo del navegador.

**Icono:** `static/img/pwa-icon-192.png` y `pwa-icon-512.png` se generan (redimensionados) a partir del logo real en `docs/design-refs/ChatGPT Image 25 jul 2026, 13_26_30.png`. Si en algún momento cambia el logo, basta con volver a exportar esos dos tamaños (192×192 y 512×512) a esos mismos archivos — no hace falta tocar `manifest.json` ni ningún otro código.

### Notificaciones push (artículo nuevo, respuestas del foro, mensajes)

Usa el estándar **Web Push** con claves **VAPID** (`pywebpush`), no Firebase ni ningún servicio de terceros — funciona directamente en Android/escritorio; en iPhone, solo si la web está instalada como app (limitación de Apple, no de esta implementación).

- **Claves:** genera un par nuevo con `python manage.py generate_vapid_keys` (comando en `apps/core/management/commands/`) y ponlas en `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`/`VAPID_CONTACT_EMAIL` (ver sección 3). Sin ellas, el botón "Activar notificaciones" del perfil no aparece y el resto del sitio sigue funcionando igual — no es un requisito para poder desplegar.
- **Suscripción:** el botón del perfil (`static/js/push_subscribe.js`) pide permiso al navegador, registra una suscripción con `PushManager.subscribe()` y la manda al backend (`accounts:push-subscribe`), que la guarda en `apps.accounts.models.PushSubscription` (una fila por dispositivo/navegador — un mismo usuario puede tener varias). Si el navegador no soporta Push API, el botón se oculta solo.
- **Envío:** `apps.core.push.send_push_to_user(s)` manda el push a todas las suscripciones de un usuario; si un endpoint ya no es válido (revocado/expirado, HTTP 404/410), la suscripción se borra sola en vez de quedarse ahí fallando para siempre. Se dispara desde tres sitios: publicar un artículo nuevo (a todos los suscritos menos el autor), responder en el foro (al autor del hilo o del comentario padre, según corresponda) y enviar un mensaje en Social (al destinatario).
- **Al llegar:** el service worker (`static/js/sw.js`) escucha `push` (muestra la notificación del sistema con `showNotification`) y `notificationclick` (al pulsarla, enfoca una pestaña ya abierta en esa URL o abre una nueva).

### Integración real con Google Calendar

A diferencia del botón .ics (descarga manual, una vez, sin seguir sincronizado), esto es una conexión de verdad vía **OAuth 2.0**: conectas tu cuenta de Google una vez y, a partir de ahí, cada evento que añadas a tu calendario personal de Top Secret (sección 8) se crea solo en tu Google Calendar — sin volver a tocar nada. El botón de conectar/desconectar vive en la propia página del calendario, arriba del mes — un único botón, con el mismo estilo que "Activar notificaciones" del perfil: mientras no estás conectado dice "Conectar con Google Calendar" y lleva al flujo de Google; una vez conectado se convierte en "Google Calendar conectado" y, al pulsarlo, desconecta. No vive en el perfil.

- **Sin librerías de Google:** en vez de `google-api-python-client` (pesada para lo poco que hace falta aquí), `apps/core/google_calendar.py` habla directamente por HTTP con los endpoints de OAuth2 y de la API de Calendar usando `requests` (ya es dependencia del proyecto).
- **Credenciales:** hacen falta `GOOGLE_OAUTH_CLIENT_ID` y `GOOGLE_OAUTH_CLIENT_SECRET` de un proyecto de Google Cloud propio (ver sección de despliegue, más abajo, para los pasos completos en la consola de Google). Vacías = el enlace "Conectar con Google Calendar" no aparece; el resto del calendario (incluido el .ics manual) sigue funcionando igual.
- **Conectar** (`accounts:google-calendar-connect`/`-callback`): pide el permiso `calendar.events` con `access_type=offline` y `prompt=consent` (así Google siempre devuelve un `refresh_token`, no solo la primera vez), y guarda la conexión en `apps.accounts.models.GoogleCalendarConnection` — un `access_token` que caduca (se renueva solo con el `refresh_token`, que no caduca salvo que el usuario revoque el acceso desde su cuenta de Google) y un `refresh_token`. El `state` del flujo OAuth se guarda en la sesión y se valida al volver, para que nadie pueda colarte una conexión que no pediste.
- **Al añadir/quitar un evento:** como el calendario es personal, la sincronización también lo es — se crea (o se borra) solo en **tu propio** Google Calendar, nunca en el de otro usuario. El id que le asigna Google se guarda directamente en `ReleaseEvent.google_event_id` (no hace falta un modelo aparte, porque el dueño del evento y el dueño de la conexión son siempre la misma persona).
- **Desconectar** (`accounts:google-calendar-disconnect`): borra la conexión y limpia el `google_event_id` de tus eventos (ya no sirve para nada sin conexión con la que borrarlos de Google si algún día los quitas del sitio) — las copias ya creadas en tu Google Calendar no se tocan, se quedan ahí como cualquier evento normal.

## 12. Animación de proyector al entrar

Al cargar la web (`templates/partials/intro.html` + `static/js/intro.js`) se muestra un proyector encendiéndose: parpadeo inicial, haz de luz que barre la pantalla, grano de película y las perforaciones del carrete desplazándose arriba y abajo, con un "clack" mecánico sintetizado por Web Audio API (si el navegador bloquea el autoplay de sonido sin interacción previa, simplemente no suena — la animación visual no depende de ello). Tras ~3,4s hace un fundido y desaparece, revelando la home.

- **Una vez por sesión de navegador:** se controla con `sessionStorage` (`bygui_intro_seen`), así que reaparece en una pestaña/ventana nueva pero no en cada navegación dentro de la misma.
- **Botón "Saltar intro"**, siempre visible durante la animación.
- **Configurable desde el admin:** **Sitio → Configuración del sitio → Animación de entrada → "mostrar animación de proyector al entrar"**. Desactivarla la quita de toda la web sin tocar código.
- Respeta `prefers-reduced-motion`: si el sistema operativo del visitante tiene activada la reducción de movimiento, se omiten el parpadeo, el barrido de luz y el sonido, y solo queda un fundido simple.

## 13. Despliegue en Render

El repositorio incluye `render.yaml` (Blueprint): Render lee ese archivo y crea el servicio con la configuración correcta sin tener que rellenar el formulario a mano.

1. Sube el proyecto a un repositorio de GitHub (Render despliega desde ahí).
2. En [render.com](https://render.com), **New → Blueprint**, y selecciona el repositorio. Render detecta `render.yaml` automáticamente.
3. Antes de confirmar, Render pedirá valores para las variables marcadas como `sync: false` (no se generan solas ni se suben al repo):
   - `DATABASE_URL` — la cadena de conexión de Supabase (ver sección 2; usa el **Session pooler**, no la conexión directa).
   - `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` — credenciales de Gmail (ver más abajo cómo generar la contraseña de aplicación).
   - `TMDB_API_KEY`, `OMDB_API_KEY` — ver sección 3.
4. Despliega. El `buildCommand` instala dependencias y ejecuta `collectstatic`; el `startCommand` aplica `migrate`, ejecuta `bootstrap_production` (ver siguiente apartado) y arranca `gunicorn` en cada arranque del servicio.

`DJANGO_SECRET_KEY` se genera automáticamente (`generateValue: true`); `ALLOWED_HOSTS` no hace falta configurarlo a mano porque Render inyecta `RENDER_EXTERNAL_HOSTNAME` y `config/settings.py` ya lo añade automáticamente.

**Sobre `DEFAULT_FROM_EMAIL` (remitente de los correos):** no hace falta configurarla — si no se fija, se deriva automáticamente de `EMAIL_HOST_USER`. Esto es importante porque **Gmail no entrega bien los correos (verificación de cuenta, recuperar contraseña, contacto) si el remitente no coincide con la cuenta autenticada por SMTP**. Si en tu servicio ya existía una `DEFAULT_FROM_EMAIL` con un dominio distinto (por ejemplo, del `.env.example` original), es la causa más probable de que esos correos no llegaran — bórrala en **Environment** (o iguálala exactamente a `EMAIL_HOST_USER`) y guarda para que se redespliegue.

### Crear el primer Admin y poblar el catálogo (sin Shell)

El **plan free de Render no incluye acceso a Shell** (es de pago), así que `createsuperuser` y `seed_movies` no se pueden lanzar a mano ahí. En su lugar, `apps/core/management/commands/bootstrap_production.py` hace ambas cosas automáticamente en cada arranque del servicio, activadas solo por variables de entorno — se configuran desde el mismo panel de Render donde ya pusiste `DATABASE_URL`, sin terminal:

1. En tu servicio de Render → pestaña **Environment**, añade:
   - `DJANGO_SUPERUSER_EMAIL` = tu email de admin
   - `DJANGO_SUPERUSER_PASSWORD` = una contraseña segura
2. Guarda (Render redespliega solo). En ese arranque se crea el usuario Admin — pero **solo si todavía no existe ningún Admin**; en arranques posteriores no hace nada, así que es seguro dejar esas variables puestas indefinidamente (aunque por higiene puedes borrarlas después de confirmar que el admin se creó).
3. Para poblar el catálogo de **películas y series**, añade además `RUN_SEED_MOVIES` = `true`, guarda, espera al redeploy (ejecuta `seed_movies` y `seed_series` seguidos), y **quita esa variable** (o ponla en `false`) — a diferencia del admin, conviene no dejarla activada, porque volvería a llamar a TMDb/OMDb en cada arranque del servicio. Si el catálogo de series aparece vacío en producción (el buscador funciona pero "Series" no tiene nada que scrollear), es justo esto: el paso de seed nunca se ejecutó ahí — repite este punto para arreglarlo.
4. Para cargar las 36 frases de ejemplo del juego "Frases célebres" (Top Secret → Juegos), añade `RUN_SEED_QUOTES` = `true` y guarda. A diferencia de `RUN_SEED_MOVIES`, esta sí es segura de dejar activada para siempre si prefieres no volver a tocar las variables (no llama a ninguna API externa, y no duplica las frases si ya existen).
5. Entra en `https://<tu-servicio>.onrender.com/admin/` con el email/contraseña del paso 1.

Si en algún momento sí quieres ejecutar comandos sueltos (management commands que no estén cubiertos por este bootstrap), la alternativa sin pagar por Shell es lanzarlos desde tu propio ordenador apuntando temporalmente a la `DATABASE_URL` de producción (mismo Supabase, esté donde esté desplegada la app):
```bash
# PowerShell
$env:DATABASE_URL = "postgresql://...tu cadena de Supabase..."
python manage.py <comando>
```

### Generar la contraseña de aplicación de Gmail

Gmail no deja usar tu contraseña normal para SMTP. Para generar una contraseña de aplicación: activa la verificación en dos pasos en tu cuenta de Google, ve a **Gestionar tu cuenta de Google → Seguridad → Verificación en dos pasos → Contraseñas de aplicaciones**, genera una (16 caracteres, sin espacios) y usa esa como `EMAIL_HOST_PASSWORD` — nunca tu contraseña real.

### Crear las credenciales OAuth de Google Calendar

Solo hace falta si quieres el botón "Conectar con Google Calendar" del perfil (integración real, no el .ics manual — ver sección 11). Sin esto, todo lo demás del sitio sigue funcionando exactamente igual.

1. Ve a [console.cloud.google.com](https://console.cloud.google.com/) con tu cuenta de Google y crea un proyecto nuevo (o usa uno que ya tengas) — arriba a la izquierda, selector de proyecto → "Proyecto nuevo".
2. **APIs y servicios → Biblioteca**, busca "Google Calendar API" y dale a **Habilitar**.
3. **APIs y servicios → Pantalla de consentimiento de OAuth**: tipo "Externo" (a menos que uses Google Workspace), rellena el nombre de la app (ej. "La Sala de Bygui") y tu email de contacto. En "Scopes" no hace falta añadir nada a mano aquí. Mientras la pantalla de consentimiento esté en modo **"Prueba" (Testing)**, solo los emails que añadas como "Usuarios de prueba" en esa misma pantalla podrán conectar su cuenta (hasta 100) — para un sitio de comunidad pequeña esto es normalmente suficiente y evita el proceso de verificación de Google, que es largo y solo hace falta para apps públicas con muchos usuarios.
4. **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**. Tipo de aplicación: **Aplicación web**.
5. En **"URI de redirección autorizados"**, añade la URL exacta de tu callback — tiene que coincidir carácter por carácter con lo que la web le manda a Google:
   - Producción: `https://<tu-servicio>.onrender.com/cuenta/google-calendar/callback/`
   - Local (si quieres probarlo en desarrollo): `http://localhost:8000/cuenta/google-calendar/callback/`
6. Guarda y copia el **ID de cliente** y el **Secreto del cliente** que te da Google.
7. Ponlos como `GOOGLE_OAUTH_CLIENT_ID` y `GOOGLE_OAUTH_CLIENT_SECRET` en las variables de entorno de Render (**Environment**, igual que el resto) y/o en tu `.env` local. Guarda — Render redespliega solo.
8. Entra en tu perfil (`/cuenta/perfil/`) y prueba "📆 Conectar con Google Calendar".

### El plan free "duerme" — y cómo mitigarlo

Render **apaga el servicio tras ~15 minutos sin recibir tráfico**. La siguiente petición lo despierta, pero esa primera carga puede tardar 30-60 segundos (arranque en frío). Es una limitación del plan gratuito, no un fallo de la app.

Para mitigarlo (opcional): un monitor externo como [UptimeRobot](https://uptimerobot.com) que haga una petición HTTP a tu URL cada 5-10 minutos mantiene el servicio despierto en horas de uso. Configuración: crea una cuenta gratuita, **Add New Monitor** → tipo *HTTP(s)* → la URL de tu servicio en Render → intervalo de 5 minutos. Esto no evita el sleep de forma permanente (Render igualmente puede reiniciar el servicio periódicamente en el plan free), pero reduce mucho la frecuencia con la que un visitante real se encuentra con el arranque en frío.

### Imágenes subidas en producción: almacenamiento persistente (Supabase Storage)

El disco de Render free **no es persistente**: sin más, las portadas, avatares y fotos del tablón de Top Secret desaparecen en cada redeploy (el archivo se sube bien, pero al redesplegar el disco se resetea). Esto es aparte de que `/media/` se sirva o no — de hecho, `/media/` **siempre** se sirve (whitenoise solo cubre `STATIC_ROOT`; las imágenes subidas por usuarios se sirven con una ruta explícita en `config/urls.py` vía `django.views.static.serve`, añadida siempre y no solo con `DEBUG=True`) — el problema es que el archivo en sí ya no está en el disco.

**La solución persistente:** usar el Storage del mismo proyecto de Supabase que ya usas para la base de datos (tiene una API compatible con S3 y plan gratuito). Si rellenas estas variables de entorno, `STORAGES["default"]` en `config/settings.py` cambia automáticamente de disco local a Supabase Storage (vía `django-storages`); si las dejas vacías, sigue usando disco local (funciona en local y en Render, pero con la limitación de siempre):

1. En tu proyecto de Supabase: **Storage → New bucket**. **El nombre solo puede tener letras, números, guiones y guiones bajos — nada de espacios** (el protocolo S3 los rechaza; si el bucket ya existe con espacios en el nombre, crea uno nuevo con un nombre válido, p. ej. `media`, y usa ese). Márcalo **Public**.
2. **Storage → Settings** (o **Project Settings → Data API**, según la versión del panel) para ver la sección **S3 Connection**: ahí está el *endpoint* (algo como `https://<tu-proyecto>.storage.supabase.co/storage/v1/s3`) y la *región*.
3. En esa misma pantalla, **S3 Access Keys → New access key** genera un *access key id* y un *secret access key* (guarda el secreto en el momento: no se vuelve a mostrar).
4. Rellena en Render (**Environment**, igual que `DATABASE_URL`): `SUPABASE_STORAGE_ENDPOINT`, `SUPABASE_STORAGE_BUCKET` (el nombre del bucket del paso 1), `SUPABASE_STORAGE_ACCESS_KEY_ID`, `SUPABASE_STORAGE_SECRET_ACCESS_KEY` y `SUPABASE_STORAGE_REGION`. Guarda y espera al redeploy.
5. A partir de ese despliegue, las imágenes nuevas que se suban ya sobreviven a los redeploys. **Las que ya se hubieran subido antes de configurar esto siguen perdidas** (había que volver a subirlas de todas formas tras cada redeploy) — vuelve a subir tu avatar, portadas, etc. una vez, y a partir de ahí quedan fijas.

Si no configuras esto, todo sigue funcionando igual que hasta ahora (disco local), solo que con la limitación de que las imágenes no sobreviven a un redeploy.

**Nota técnica (por qué hace falta `custom_domain`):** marcar el bucket como "Public" en Supabase no lo hace accesible por la URL del endpoint S3 (`.../storage/v1/s3/...`) — esa ruta exige petición firmada siempre, sea el bucket público o no. Los archivos públicos se sirven por una URL completamente distinta, la nativa de Supabase: `https://<project-ref>.supabase.co/storage/v1/object/public/<bucket>/<ruta>`. `config/settings.py` calcula ese dominio automáticamente a partir de `SUPABASE_STORAGE_ENDPOINT` y `SUPABASE_STORAGE_BUCKET` (parámetro `custom_domain` de `django-storages`), así que no hay que configurarlo aparte — pero si en el futuro cambias de proveedor S3-compatible, este detalle es específico de Supabase y puede no aplicar igual.

## Comandos útiles

```bash
python manage.py makemigrations   # tras cambiar modelos
python manage.py migrate
python manage.py seed_demo        # usuarios de ejemplo (uno por rol)
python manage.py seed_content     # seed_demo + artículos, hilos de foro, películas de Top Secret y frases célebres de ejemplo
python manage.py seed_movies      # catálogo de películas desde TMDb/OMDb (--pages N, por defecto 2)
python manage.py seed_series      # lo mismo pero para series
python manage.py seed_quotes      # frases de ejemplo para "Frases célebres" (seguro en producción, no crea usuarios)
python manage.py generate_vapid_keys  # genera un par de claves nuevo para las notificaciones push
python manage.py createsuperuser
python manage.py collectstatic    # antes de desplegar
```
