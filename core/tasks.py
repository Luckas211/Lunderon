from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def task_processar_geracao_video(self, video_gerado_id, data, user_id, assinatura_id, limite_testes_config=0):
    """
    Tarefa Celery para processar a geração de vídeo em segundo plano.
    """
    # CORREÇÃO: Importamos a função aqui dentro, e não no topo do arquivo.
    from .views import processar_geracao_video

    try:
        logger.info(f"Iniciando task_processar_geracao_video para o ID: {video_gerado_id}")
        # A lógica pesada é chamada aqui
        processar_geracao_video(video_gerado_id, data, user_id, assinatura_id, limite_testes_config)
        logger.info(f"task_processar_geracao_video para o ID: {video_gerado_id} concluída com sucesso.")
    except Exception as e:
        logger.error(f"ERRO na task_processar_geracao_video para o ID {video_gerado_id}: {e}", exc_info=True)
        # Tenta novamente em 60 segundos, no máximo 3 vezes
        self.retry(exc=e, countdown=60, max_retries=3)

@shared_task(bind=True)
def task_processar_corte_youtube(self, corte_gerado_id, musica_base_id, volume_musica, gerar_legendas):
    """
    Tarefa Celery para processar o corte de vídeos do YouTube em segundo plano.
    """
    # CORREÇÃO: Importamos a função aqui dentro, e não no topo do arquivo.
    from .views import processar_corte_youtube

    try:
        logger.info(f"Iniciando task_processar_corte_youtube para o ID: {corte_gerado_id}")
        # A lógica pesada é chamada aqui
        processar_corte_youtube(corte_gerado_id, musica_base_id, volume_musica, gerar_legendas)
        logger.info(f"task_processar_corte_youtube para o ID: {corte_gerado_id} concluída com sucesso.")
    except Exception as e:
        logger.error(f"ERRO na task_processar_corte_youtube para o ID {corte_gerado_id}: {e}", exc_info=True)
        # Tenta novamente em 60 segundos, no máximo 3 vezes
        self.retry(exc=e, countdown=60, max_retries=3)