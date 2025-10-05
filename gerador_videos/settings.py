"""
Django settings for gerador_videos project.
"""
from pathlib import Path
import os
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Configuração do Environ ---
env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# --- Configurações de Segurança ---
SECRET_KEY = env('SECRET_KEY', default='django-insecure-default-key-for-dev')
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])
SERVICE_URL = env('CLOUD_RUN_URL', default=None)
if SERVICE_URL:
    from urllib.parse import urlparse
    hostname = urlparse(SERVICE_URL).hostname
    if hostname:
        ALLOWED_HOSTS.append(hostname)

# --- Aplicações e Middlewares ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'storages',
    'django_celery_results', # Adicionado para o Celery
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.EmailVerificationMiddleware',
]

ROOT_URLCONF = 'gerador_videos.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

# --- Banco de Dados ---
DATABASES = {
    'default': env.db()
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
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'core', 'static'),
]
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
if DEBUG:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_STORAGE = 'core.storage.StaticStorage'

# --- Configurações de Autenticação ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
AUTH_USER_MODEL = 'core.Usuario'

# --- Configurações do Stripe ---
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY')
STRIPE_PRICE_ID = env('STRIPE_PRICE_ID')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='whsec_...')

APPEND_SLASH = True

# ================================================================
# CONFIGURAÇÕES DE E-MAIL
# ================================================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# --- Configurações do Cloudflare R2 ---
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL')
AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='auto')
AWS_DEFAULT_ACL = 'public-read'
AWS_QUERYSTRING_AUTH = False
CLOUDFLARE_R2_PUBLIC_URL = env('CLOUDFLARE_R2_PUBLIC_URL')

# --- Usar R2 para arquivos de mídia ---
DEFAULT_FILE_STORAGE = 'core.storage.MediaStorage'


# ================================================================
# CONFIGURAÇÕES DO CELERY
# ================================================================
# URL do Broker (Redis). Use uma variável de ambiente em produção.
# Exemplo para Cloud Memorystore: redis://:password@hostname:port/0
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')
# Backend para armazenar os resultados das tarefas no banco de dados Django
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE