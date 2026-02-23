"""
Django settings for gerador_videos project.
"""
from pathlib import Path
import os
import environ
import dj_database_url  # BIBLIOTECA NECESSÁRIA PARA O NEONDB

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Configuração do Environ ---
env = environ.Env()
# Tenta ler o .env se ele existir
env_file = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_file):
    environ.Env.read_env(env_file)

# --- Configurações de Segurança ---
SECRET_KEY = env('SECRET_KEY', default='django-insecure-chave-padrao-dev')
DEBUG = env.bool('DEBUG', default=True)

# --- HOSTS PERMITIDOS (CRÍTICO PARA O TÚNEL) ---
# O '*' permite que o Cloudflare Tunnel acesse sem dar erro de Invalid Host
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', '0.0.0.0', '*'])

# --- ORIGENS CONFIÁVEIS (CRÍTICO PARA EVITAR ERRO CSRF 403) ---
# Isso permite que você faça login e envie formulários através do link do túnel
CSRF_TRUSTED_ORIGINS = [
    'https://*.trycloudflare.com',
    'http://*.trycloudflare.com',
    'https://127.0.0.1',
    'http://127.0.0.1',
    'http://localhost',
]

# --- Configurações de Segurança de Produção ---
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# --- Aplicações ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',                 # Seu app principal
    'storages',             # Para o Cloudflare R2
    'django_celery_results', # Para guardar resultados das tarefas no banco
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # WhiteNoise para arquivos estáticos
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.EmailVerificationMiddleware', # Seu middleware de verificação de email
]

ROOT_URLCONF = 'gerador_videos.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [], # O Django já procura dentro das pastas dos apps se APP_DIRS=True
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'gerador_videos.wsgi.application'

# --- Banco de Dados (NeonDB / PostgreSQL) ---
# Configuração robusta para aceitar tanto SQLite (dev) quanto Postgres (prod)
DATABASES = {
    'default': dj_database_url.config(
        default=env('DATABASE_URL', default='sqlite:///db.sqlite3'),
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True if 'postgresql' in env('DATABASE_URL', default='') else False
    )
}

# --- Validação de Senhas ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internacionalização ---
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# --- Arquivos Estáticos e de Mídia ---
STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'core', 'static')]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Configuração híbrida: Se tiver chaves R2, usa R2. Se não, usa local.
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID', default=None)

if AWS_ACCESS_KEY_ID:
    # --- MODO PRODUÇÃO/R2 ---
    AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL')
    AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='auto')
    AWS_DEFAULT_ACL = 'public-read'
    AWS_QUERYSTRING_AUTH = False
    
    # URL Pública para mídia
    CLOUDFLARE_R2_PUBLIC_URL = env('CLOUDFLARE_R2_PUBLIC_URL', default='')

    # Armazenamento de Mídia vai para o R2
    DEFAULT_FILE_STORAGE = 'core.storage.MediaStorage' 
    MEDIA_URL = f'{CLOUDFLARE_R2_PUBLIC_URL}/media/'

    # Estáticos continuam locais/whitenoise por performance
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
else:
    # --- MODO LOCAL ---
    print("⚠️  AVISO: Usando armazenamento local (Chaves R2 não encontradas)")
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# --- Autenticação ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
AUTH_USER_MODEL = 'core.Usuario'

# --- Stripe ---
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', default='')
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_PRICE_ID = env('STRIPE_PRICE_ID', default='')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='')

APPEND_SLASH = True

# --- E-mail ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# ================================================================
# CONFIGURAÇÕES DO CELERY (Redis / Upstash)
# ================================================================
# Aqui ele vai pegar a URL do Upstash direto do seu arquivo .env
# Se não achar, tenta conectar no localhost (fallback)
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')

# Armazena os resultados das tarefas no banco de dados Django (NeonDB)
# Isso é melhor que usar a memória do Redis
CELERY_RESULT_BACKEND = 'django-db'

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Configurações para tarefas longas de IA (evita timeouts prematuros)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60      # 30 minutos máximo
CELERY_TASK_SOFT_TIME_LIMIT = 28 * 60 # Aviso com 28 minutos
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1 # Reinicia o worker após cada vídeo para limpar RAM