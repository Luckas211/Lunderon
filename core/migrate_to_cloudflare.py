# migrate_to_cloudflare.py
import os
from django.core.files import File
from core.models import VideoBase, MusicaBase

def migrate_files_to_cloudflare():
    # Migrar vídeos
    for video in VideoBase.objects.all():
        if video.arquivo_video and not video.video_url:
            print(f"Migrando vídeo: {video.titulo}")
            # O próprio save() vai atualizar a URL
            video.save()
    
    # Migrar músicas
    for musica in MusicaBase.objects.all():
        if musica.arquivo_musica and not musica.musica_url:
            print(f"Migrando música: {musica.titulo}")
            musica.save()
    
    print("Migração concluída!")