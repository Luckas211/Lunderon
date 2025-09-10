from django.core.management.base import BaseCommand
from core.models import VideoGerado
from django.utils import timezone
from datetime import timedelta
import os
from django.conf import settings

class Command(BaseCommand):
    help = 'Remove vídeos gerados há mais de 5 horas'

    def handle(self, *args, **kwargs):
        limite = timezone.now() - timedelta(hours=5)
        expirados = VideoGerado.objects.filter(criado_em__lt=limite)
        removidos = 0
        for video in expirados:
            if video.arquivo_final:
                caminho = os.path.join(settings.MEDIA_ROOT, str(video.arquivo_final))
                if os.path.exists(caminho):
                    try:
                        os.remove(caminho)
                        removidos += 1
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Erro ao remover {caminho}: {e}'))
            video.delete()
        self.stdout.write(self.style.SUCCESS(f'Vídeos expirados removidos: {removidos}'))
