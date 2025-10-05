import os
from celery import Celery

# Define o módulo de configurações do Django para o Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gerador_videos.settings')

# Cria a instância do Celery
app = Celery('gerador_videos')

# Carrega a configuração a partir do settings.py do Django
# O namespace='CELERY' significa que todas as configurações do Celery
# no settings.py devem começar com CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descobre e carrega automaticamente as tarefas dos aplicativos Django instalados
# (procurará por um arquivo tasks.py em cada app)
app.autodiscover_tasks()