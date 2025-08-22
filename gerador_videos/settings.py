"""
Django settings for gerador_videos project.
"""
from pathlib import Path
import os
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Configuração do Environ ---
# Lê as variáveis de ambiente do arquivo .env
env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))


# --- Configurações de Segurança ---
SECRET_KEY = env('SECRET_KEY', default='django-insecure-default-key-for-dev')
DEBUG = env.bool('DEBUG', default=True)

ALLOWED_HOSTS = [
    '.ngrok-free.app', # O ponto no início permite qualquer subdomínio do ngrok
    'localhost',
    '127.0.0.1',
]


# --- Aplicações e Middlewares ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'gerador_videos.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # 1. 'DIRS' deve ficar vazio para não competir com a busca nos apps.
        'DIRS': [],
        # 2. 'APP_DIRS': True é a configuração chave que faz essa estrutura funcionar.
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
# Esta é a forma correta e limpa de ler a configuração do seu arquivo .env
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
    os.path.join(BASE_DIR, 'static'),
]
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- Configurações de Autenticação ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
AUTH_USER_MODEL = 'core.Usuario'


# --- Configurações do Stripe ---
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY')
STRIPE_PRICE_ID = env('STRIPE_PRICE_ID') # <-- ADICIONE ESTA LINHA
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET')