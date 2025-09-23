from django.core.management.base import BaseCommand
from core.models import VideoGerado
from django.utils import timezone
from datetime import timedelta
from core.utils import delete_from_r2  # Importando a função de utils.py
from django.conf import settings

class Command(BaseCommand):
    help = 'Remove vídeos gerados do Cloudflare R2 e do banco de dados após 1 hora.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('Iniciando a rotina de limpeza de vídeos expirados...'))
        
        # Define o limite de tempo para 1 hora atrás, conforme a política de privacidade
        limite_tempo = timezone.now() - timedelta(hours=1)
        
        # Busca vídeos concluídos, que não sejam nulos e que foram criados antes do limite de tempo
        videos_expirados = VideoGerado.objects.filter(
            criado_em__lt=limite_tempo,
            arquivo_final__isnull=False
        ).exclude(arquivo_final__exact='')

        if not videos_expirados.exists():
            self.stdout.write(self.style.SUCCESS('Nenhum vídeo expirado para remover.'))
            return

        self.stdout.write(f'Encontrados {videos_expirados.count()} vídeos para remover.')
        
        removidos_com_sucesso = 0
        erros = 0

        for video in videos_expirados:
            self.stdout.write(f'Processando vídeo ID {video.id} (Object Key: {video.arquivo_final})...')
            
            # 1. Tenta apagar o arquivo do Cloudflare R2
            sucesso_delecao_r2 = delete_from_r2(video.arquivo_final)
            
            # 2. Se a deleção no R2 foi bem-sucedida, apaga o registro do banco
            if sucesso_delecao_r2:
                try:
                    video.delete()
                    self.stdout.write(self.style.SUCCESS(f'  -> Sucesso: Vídeo ID {video.id} removido do R2 e do banco de dados.'))
                    removidos_com_sucesso += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  -> Erro ao remover o vídeo ID {video.id} do banco de dados: {e}'))
                    erros += 1
            else:
                self.stdout.write(self.style.WARNING(f'  -> Falha: Não foi possível remover o vídeo ID {video.id} do R2. O registro no banco de dados será mantido por enquanto.'))
                erros += 1

        self.stdout.write(self.style.SUCCESS(f'\nLimpeza concluída.'))
        self.stdout.write(f'  - Vídeos removidos com sucesso: {removidos_com_sucesso}')
        self.stdout.write(f'  - Falhas ou erros: {erros}')
