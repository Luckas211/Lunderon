# Em core/views.py

from .tasks import task_processar_geracao_video, task_processar_corte_youtube # <-- Importe as novas tarefas Celery
from .transcription_utils import get_word_timestamps
from django.utils.safestring import mark_safe
from .utils import send_verification_email, is_token_valid
import tempfile
import requests
import logging

logger = logging.getLogger(__name__)
from urllib.parse import urlparse
import os

from .utils import (
    verificar_arquivo_existe_no_r2,
    generate_presigned_url,
    download_from_cloudflare,
    upload_to_r2,
    upload_fileobj_to_r2,
    delete_from_r2,
)
from django.conf import settings

import re
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import subprocess
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY
from django.urls import reverse
import random
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Q, Sum
import platform
import textwrap
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.conf import settings
from django.contrib import messages
from PIL import Image, ImageDraw, ImageFont

from .models import (
    Assinatura,
    Pagamento,
    Configuracao,
    VideoBase,
    MusicaBase,
    VideoGerado,
    CorteGerado,
    CategoriaVideo,
    CategoriaMusica,
    Plano,
    Usuario,
)


from django.core.mail import send_mail
import yt_dlp
from .transcription_utils import extract_audio_from_video, transcribe_audio_to_srt


def _get_user_video_usage(user):
    """
    Busca a assinatura ativa de um usuário e retorna seu uso de vídeos,
    o limite do seu plano e o objeto da assinatura.
    """
    # Usar select_related('plano') otimiza a consulta, evitando uma busca extra no banco de dados.
    assinatura_ativa = (
        Assinatura.objects.filter(usuario=user, status="ativo")
        .select_related("plano")
        .first()
    )

    limite_videos_mes = 0
    if assinatura_ativa:
        limite_videos_mes = assinatura_ativa.plano.limite_videos_mensal

    trinta_dias_atras = timezone.now() - timedelta(days=30)
    videos_criados = (
        VideoGerado.objects.filter(usuario=user, criado_em__gte=trinta_dias_atras)
        .exclude(status="ERRO")
        .count()
    )

    return videos_criados, limite_videos_mes, assinatura_ativa


def get_valid_media_from_category(model, category):
    """
    Retorna uma mídia válida (com object_key) da categoria especificada
    Verifica se o arquivo realmente existe no R2 antes de retornar
    """
    # Primeiro, verifica se há mídias válidas na categoria
    valid_media = (
        model.objects.filter(categoria=category)
        .exclude(object_key__isnull=True)
        .exclude(object_key__exact="")
    )

    if not valid_media.exists():
        print(f"Erro: Não há {model.__name__} válidos para a categoria {category}")
        return None

    # Tenta encontrar uma mídia que realmente existe no R2
    for media in valid_media.order_by("?"):
        if verificar_arquivo_existe_no_r2(media.object_key):
            return media

    print(
        f"Erro: Nenhum {model.__name__} encontrado para a categoria {category} que exista no R2"
    )
    return None


VOICE_MAPPING = {
    "pf_dora": {"speaker": "pf_dora", "language": "pt-br"},
    "pm_alex": {"speaker": "pm_alex", "language": "pt-br"},
    "pm_santa": {"speaker": "pm_santa", "language": "pt-br"},
}

# ==============================================================================
# CONSTANTES E FUNÇÕES HELPER (LÓGICA DO GERADOR DE VÍDEO)
# ==============================================================================
from kokoro import KPipeline
import numpy as np
import soundfile as sf

VOZES_KOKORO = {
    "pt-BR-Wavenet-A": "pf_dora",
    "pt-BR-Wavenet-C": "pf_dora",
    "pt-BR-Wavenet-D": "pf_dora",
    "pt-BR-Wavenet-B": "pm_alex",
    "pt-BR-Neural2-B": "pm_santa",
}


def gerar_audio_e_tempos(
    texto, voz, velocidade, obter_tempos=False
):  # Parâmetro 'tom' removido
    """
    Gera áudio a partir do texto usando o modelo Kokoro para português brasileiro
    """
    try:
        pipeline = KPipeline(lang_code="p")
        speed_factor = float(velocidade) / 100.0

        # Gerar áudio (sem o argumento 'pitch')
        generator = pipeline(texto, voice=voz, speed=speed_factor, split_pattern=r"\n+")

        audio_segments = []
        for i, (gs, ps, audio) in enumerate(generator):
            audio_segments.append(audio)

        full_audio = np.concatenate(audio_segments)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_f:
            caminho_audio = temp_f.name
        sf.write(caminho_audio, full_audio, 24000)

        duracao = len(full_audio) / 24000

        timepoints = None
        if obter_tempos:
            pass  # Sua lógica de timepoints aqui

        return caminho_audio, timepoints, duracao

    except Exception as e:
        print(f"Erro ao gerar áudio para voz {voz}: {e}")
        if voz != "pf_dora":
            print(f"Tentando com voz padrão (pf_dora)...")
            # Chamada de fallback também sem o 'tom'
            return gerar_audio_e_tempos(texto, "pf_dora", velocidade, obter_tempos)
        return None, None, 0


FONT_PATHS = {
    "Windows": {
        "cunia": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "Cunia.ttf"
        ),
        "arial": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "arial.ttf"
        ),
        "arialbd": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "arialbd.ttf"
        ),
        "times": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "times.ttf"
        ),
        "courier": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "cour.ttf"
        ),
        "impact": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "impact.ttf"
        ),
        "verdana": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "verdana.ttf"
        ),
        "georgia": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "georgia.ttf"
        ),
        "alfa_slab_one": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "AlfaSlabOne-Regular.ttf"
        ),
    },
    "Linux": {
        "cunia": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "Cunia.ttf"
        ),
        "arial": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "arial.ttf"
        ),
        "arialbd": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "arialbd.ttf"
        ),
        "times": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "times.ttf"
        ),
        "courier": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "cour.ttf"
        ),
        "impact": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "impact.ttf"
        ),
        "verdana": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "verdana.ttf"
        ),
        "georgia": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "georgia.ttf"
        ),
        "alfa_slab_one": os.path.join(
            settings.BASE_DIR, "core", "static", "fonts", "AlfaSlabOne-Regular.ttf"
        ),
    },
}


def wrap_text_by_width(text, font, max_width, draw):
    """Wraps text to fit within a specified width, using the draw object."""
    lines = []
    if not text:
        return ""

    words = text.split(' ')
    
    if not words:
        return ""

    current_line = words[0]
    for word in words[1:]:
        if draw.textbbox((0, 0), current_line + " " + word, font=font)[2] <= max_width:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return "\n".join(lines)

def create_text_image(texto, cor_da_fonte_hex, data, posicao="centro"):
    target_size = (1080, 1920)
    w, h = target_size
    sistema_op = platform.system()
    nome_fonte = data.get("texto_fonte", "arial")
    caminho_da_fonte = FONT_PATHS.get(sistema_op, {}).get(
        nome_fonte, FONT_PATHS.get("Windows", {}).get(nome_fonte)
    )
    if not caminho_da_fonte:
        print(f"AVISO: Fonte '{nome_fonte}' não encontrada. Usando Cunia como padrão.")
        caminho_da_fonte = FONT_PATHS["Windows"]["cunia"]

    # --- LÓGICA DE DELIMITAÇÃO DE TEXTO ---
    try:
        tamanho_fonte_inicial = int(data.get("texto_tamanho", 35))
    except (ValueError, TypeError):
        tamanho_fonte_inicial = 35

    tamanho_fonte = tamanho_fonte_inicial
    max_text_width = w * 0.9  # 90% da largura
    max_text_height = h * 0.4 # 40% da altura
    min_font_size = 35

    while tamanho_fonte >= min_font_size:
        try:
            if data.get("texto_negrito", False) and nome_fonte == "arial":
                caminho_da_fonte_atual = FONT_PATHS.get(sistema_op, {}).get("arialbd", caminho_da_fonte)
            else:
                caminho_da_fonte_atual = caminho_da_fonte
            font = ImageFont.truetype(caminho_da_fonte_atual, size=tamanho_fonte)
        except Exception as e:
            print(f"AVISO: Fonte '{caminho_da_fonte_atual}' não pôde ser carregada: {e}. Usando fonte padrão.")
            font = ImageFont.load_default(size=tamanho_fonte)

        temp_img = Image.new("RGBA", (w, h))
        temp_draw = ImageDraw.Draw(temp_img)
        
        texto_quebrado = wrap_text_by_width(texto, font, max_text_width, temp_draw)
        
        bbox = temp_draw.textbbox((0, 0), texto_quebrado, font=font, align="center", spacing=15)
        text_h = bbox[3] - bbox[2]

        if text_h <= max_text_height:
            # O texto cabe, podemos parar
            break
        
        # O texto não cabe, reduz o tamanho da fonte e tenta de novo
        tamanho_fonte -= 2
    # --- FIM DA LÓGICA DE DELIMITAÇÃO ---

    # Agora, desenha a imagem final com o tamanho de fonte calculado
    img = Image.new("RGBA", target_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    espacamento_entre_linhas = 15
    final_bbox = draw.textbbox((0, 0), texto_quebrado, font=font, align="center", spacing=espacamento_entre_linhas)
    text_w, text_h = final_bbox[2] - final_bbox[0], final_bbox[3] - final_bbox[1] 

    x = (w - text_w) / 2
    if posicao == "inferior":
        y = h - text_h - 170
    else: # centro
        y = (h - text_h) / 2

    try:
        hex_limpo = cor_da_fonte_hex.lstrip("#")
        r, g, b = tuple(int(hex_limpo[i : i + 2], 16) for i in (0, 2, 4))
        cor_rgba = (r, g, b, 255)
    except (ValueError, IndexError, TypeError):
        cor_rgba = (255, 255, 255, 255)

    draw.text(
        (x + 2, y + 2),
        texto_quebrado,
        font=font,
        fill=(0, 0, 0, 128),
        align="center",
        spacing=espacamento_entre_linhas,
    )
    draw.text(
        (x, y),
        texto_quebrado,
        font=font,
        fill=cor_rgba,
        align="center",
        spacing=espacamento_entre_linhas,
    )

    if data.get("texto_sublinhado", False):
        num_linhas = len(texto_quebrado.split("\n"))
        altura_total_texto_sem_espaco = text_h - (espacamento_entre_linhas * (num_linhas - 1))
        altura_linha_unica = altura_total_texto_sem_espaco / num_linhas
        for i, linha_texto in enumerate(texto_quebrado.split("\n")):
            linha_y = y + (i * (altura_linha_unica + espacamento_entre_linhas))
            bbox_linha = draw.textbbox((0, 0), linha_texto, font=font)
            largura_linha = bbox_linha[2] - bbox_linha[0]
            x_linha = (w - largura_linha) / 2
            underline_y = linha_y + altura_linha_unica + 2
            draw.line(
                (x_linha, underline_y, x_linha + largura_linha, underline_y),
                fill=cor_rgba,
                width=2,
            )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_f:
        caminho_imagem_texto = temp_f.name
    img.save(caminho_imagem_texto, "PNG")
    return caminho_imagem_texto


@csrf_exempt
def preview_voz(request, nome_da_voz):
    """
    Gera um preview de áudio para uma voz específica usando Kokoro
    """
    try:
        # Verificar se a voz está disponível
        if nome_da_voz not in VOICE_MAPPING:
            return JsonResponse({"error": "Voz não encontrada"}, status=404)

        texto_teste = "Esta é uma prévia da voz selecionada."

        # Gerar o áudio com Kokoro
        pipeline = KPipeline(lang_code="p")
        generator = pipeline(texto_teste, voice=nome_da_voz, speed=1.0)

        # Concatenar segmentos de áudio
        audio_segments = []
        for i, (gs, ps, audio) in enumerate(generator):
            audio_segments.append(audio)

        full_audio = np.concatenate(audio_segments)

        # Salvar em arquivo temporário
        audio_temp_dir = os.path.join(settings.MEDIA_ROOT, "audio_temp")
        os.makedirs(audio_temp_dir, exist_ok=True)
        caminho_audio = os.path.join(
            audio_temp_dir, f"preview_{nome_da_voz}_{random.randint(1000,9999)}.wav"
        )
        sf.write(caminho_audio, full_audio, 24000)

        # Retornar o arquivo de áudio
        with open(caminho_audio, "rb") as audio_file:
            response = HttpResponse(audio_file.read(), content_type="audio/wav")
            response["Content-Disposition"] = f'attachment; filename="preview_{nome_da_voz}.wav"'

            # Limpeza do arquivo temporário após o envio
            def cleanup():
                try:
                    os.remove(caminho_audio)
                except:
                    pass

            response._resource_closers.append(cleanup)
            return response

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def meus_videos(request):
    # --- LÓGICA DE NOTIFICAÇÃO ---
    videos_para_notificar = VideoGerado.objects.filter(
        usuario=request.user, notificacao_vista=False
    )
    for video in videos_para_notificar:
        if video.status == "CONCLUIDO":
            # Tenta usar o texto do narrador ou o texto de overlay para dar um título mais útil
            titulo_video = video.narrador_texto or video.texto_overlay or "sem título"
            messages.success(
                request,
                f'Boas notícias! O seu vídeo "{ (titulo_video[:30] + '...') if len(titulo_video) > 30 else titulo_video }" foi gerado com sucesso.',
            )
        elif video.status == "ERRO":
            # Limita a mensagem de erro para não poluir a tela do usuário
            mensagem_curta = (
                (video.mensagem_erro[:75] + "...")
                if video.mensagem_erro and len(video.mensagem_erro) > 75
                else "Erro desconhecido"
            )
            messages.error(
                request,
                f"Ops! Houve um problema ao gerar seu vídeo. Detalhes: {mensagem_curta}",
            )

    # Marca as notificações como vistas para não serem exibidas novamente
    if videos_para_notificar.exists():
        videos_para_notificar.update(notificacao_vista=True)
    # --- FIM DA LÓGICA DE NOTIFICAÇÃO ---

    videos = VideoGerado.objects.filter(usuario=request.user).select_related('cortegerado').order_by("-criado_em")

    # --- LÓGICA ATUALIZADA ---
    # A lógica de busca do limite foi substituída pela função auxiliar.

    videos_criados_no_mes, limite_videos_mes, assinatura = _get_user_video_usage(
        request.user
    )

    uso_percentual = 0
    if limite_videos_mes > 0:
        # Calcula a porcentagem de uso
        uso_percentual = (videos_criados_no_mes / limite_videos_mes) * 100
    # --- FIM DA ATUALIZAÇÃO ---

    context = {
        "videos": videos,
        "videos_criados_no_mes": videos_criados_no_mes,
        "limite_videos_mes": limite_videos_mes,
        "uso_percentual": uso_percentual,
    }
    return render(request, "core/meus_videos.html", context)


@login_required
def video_download_page(request, video_id):
    """
    Renderiza a página intermediária que iniciará o download.
    """
    video = get_object_or_404(VideoGerado, id=video_id, usuario=request.user)

    if video.status != "CONCLUIDO" or not video.arquivo_final:
        messages.error(request, "Este vídeo não está mais disponível para download.")
        return redirect("meus_videos")

    # Gera a URL segura para ser usada no template
    presigned_url = generate_presigned_url(
        video.arquivo_final, expiration=300
    )  # 5 minutos

    if not presigned_url:
        messages.error(request, "Não foi possível gerar o link de download.")
        return redirect("meus_videos")

    context = {"video": video, "download_url": presigned_url}
    return render(request, "core/download_page.html", context)



def processar_geracao_video(
    video_gerado_id, data, user_id, assinatura_id, limite_testes_config=0
):
    logger.info(f"Iniciando processamento para VideoGerado ID: {video_gerado_id}")
    video = get_object_or_404(VideoGerado, id=video_gerado_id)
    user = get_object_or_404(Usuario, id=user_id)
    assinatura_ativa = None
    if assinatura_id:
        assinatura_ativa = get_object_or_404(Assinatura, id=assinatura_id)

    caminhos_para_limpar = []
    logger.debug(f"[{video_gerado_id}] Data recebida: {data}")

    try:
        tipo_conteudo = data.get("tipo_conteudo")
        duracao_video = data.get("duracao_segundos") or 30
        logger.info(f"[{video_gerado_id}] Tipo de conteúdo: {tipo_conteudo}, Duração: {duracao_video}s")

        caminho_narrador_input = None
        if (tipo_conteudo == "narrador" or tipo_conteudo == "vendedor") and data.get("narrador_texto"):
            logger.info(f"[{video_gerado_id}] Gerando áudio de narração...")
            texto_narrador_limpo = re.sub(r'\{\{\d+\}\}', '', data["narrador_texto"])
            caminho_narrador_input, _, duracao_audio = gerar_audio_e_tempos(
                texto_narrador_limpo,
                data["narrador_voz"],
                data["narrador_velocidade"],
            )
            if caminho_narrador_input:
                logger.info(f"[{video_gerado_id}] Áudio de narração gerado em: {caminho_narrador_input}, Duração: {duracao_audio}s")
                caminhos_para_limpar.append(caminho_narrador_input)
                if duracao_audio > 0:
                    duracao_video = duracao_audio
            else:
                logger.warning(f"[{video_gerado_id}] Falha ao gerar áudio de narração.")

        caminho_legenda_ass = None
        if data.get("legenda_sincronizada") and caminho_narrador_input:
            logger.info(f"[{video_gerado_id}] Gerando legenda sincronizada...")
            try:
                word_timestamps = get_word_timestamps(caminho_narrador_input)
                if word_timestamps:
                    caminho_legenda_ass = gerar_legenda_karaoke_ass(
                        word_timestamps, data, data.get("cor_da_fonte", "#FFFFFF"),
                        data.get("cor_destaque_legenda", "#FFFF00"), data.get("posicao_texto", "centro")
                    )
                    logger.info(f"[{video_gerado_id}] Legenda gerada em: {caminho_legenda_ass}")
                    caminhos_para_limpar.append(caminho_legenda_ass)
                else:
                    logger.warning(f"[{video_gerado_id}] Não foi possível obter timestamps das palavras para a legenda.")
            except Exception as e:
                logger.error(f"[{video_gerado_id}] Erro ao gerar legenda precisa: {e}", exc_info=True)

        caminho_video_input = None
        logger.info(f"[{video_gerado_id}] Obtendo vídeo de fundo...")
        if tipo_conteudo in ["narrador", "texto"]:
            video_base_id = data.get("video_base_id")
            video_base = None
            if video_base_id:
                try:
                    video_base = VideoBase.objects.get(id=video_base_id)
                    if not verificar_arquivo_existe_no_r2(video_base.object_key):
                        logger.warning(f"[{video_gerado_id}] Vídeo escolhido (ID: {video_base_id}) não encontrado no R2. Selecionando um aleatório.")
                        video_base = None
                except VideoBase.DoesNotExist:
                    logger.warning(f"[{video_gerado_id}] VideoBase com ID {video_base_id} não existe. Selecionando um aleatório.")
                    video_base = None
            
            if not video_base:
                categoria_video_id = data.get("categoria_video")
                if categoria_video_id:
                    try:
                        categoria_video = CategoriaVideo.objects.get(id=categoria_video_id)
                        video_base = get_valid_media_from_category(VideoBase, categoria_video)
                    except CategoriaVideo.DoesNotExist:
                        raise Exception(f"Categoria de vídeo com ID {categoria_video_id} não encontrada.")
            
            if not video_base:
                raise Exception("Não foi possível encontrar um vídeo de fundo válido para a categoria.")
            
            logger.info(f"[{video_gerado_id}] Baixando vídeo de fundo: {video_base.object_key}")
            caminho_video_input = download_from_cloudflare(video_base.object_key, ".mp4")

        elif tipo_conteudo == "vendedor":
            video_upload_key = data.get("video_upload_key")
            if video_upload_key:
                logger.info(f"[{video_gerado_id}] Baixando vídeo de vendedor: {video_upload_key}")
                caminho_video_input = download_from_cloudflare(video_upload_key, ".mp4")
            else:
                raise Exception("Nenhuma 'video_upload_key' fornecida para o tipo 'vendedor'.")
        
        if caminho_video_input:
            logger.info(f"[{video_gerado_id}] Vídeo de fundo obtido em: {caminho_video_input}")
            caminhos_para_limpar.append(caminho_video_input)
        else:
            raise Exception("Falha ao obter o vídeo de fundo.")

        caminho_imagem_texto = None
        if tipo_conteudo == "texto" and data.get("texto_overlay"):
            logger.info(f"[{video_gerado_id}] Criando imagem de texto overlay...")
            caminho_imagem_texto = create_text_image(
                data["texto_overlay"], data.get("cor_da_fonte", "#FFFFFF"),
                data, data.get("posicao_texto", "centro")
            )
            logger.info(f"[{video_gerado_id}] Imagem de texto criada em: {caminho_imagem_texto}")
            caminhos_para_limpar.append(caminho_imagem_texto)

        caminho_musica_input = None
        if data.get("volume_musica", 0) > 0 and data.get("categoria_musica"):
            logger.info(f"[{video_gerado_id}] Obtendo música de fundo...")
            try:
                categoria_musica = CategoriaMusica.objects.get(id=data["categoria_musica"])
                musica_base = get_valid_media_from_category(MusicaBase, categoria_musica)
                if musica_base:
                    logger.info(f"[{video_gerado_id}] Baixando música: {musica_base.object_key}")
                    caminho_musica_input = download_from_cloudflare(musica_base.object_key, ".mp3")
                    if caminho_musica_input:
                        logger.info(f"[{video_gerado_id}] Música obtida em: {caminho_musica_input}")
                        caminhos_para_limpar.append(caminho_musica_input)
                else:
                    logger.warning(f"[{video_gerado_id}] Nenhuma música válida encontrada para a categoria.")
            except CategoriaMusica.DoesNotExist:
                logger.warning(f"[{video_gerado_id}] Categoria de música não encontrada.")

        with tempfile.NamedTemporaryFile(delete=False, suffix="_temp.mp4") as temp_f:
            caminho_video_temp = temp_f.name
        caminhos_para_limpar.append(caminho_video_temp)

        cmd = ["ffmpeg", "-y"]
        if tipo_conteudo == "narrador" or data.get("loop_video", False):
            cmd.extend(["-stream_loop", "-1", "-i", caminho_video_input])
        else:
            cmd.extend(["-i", caminho_video_input])

        inputs_adicionais = []
        if caminho_musica_input: inputs_adicionais.append(caminho_musica_input)
        if caminho_imagem_texto: inputs_adicionais.insert(0, caminho_imagem_texto)
        if caminho_narrador_input: inputs_adicionais.append(caminho_narrador_input)
        for f in inputs_adicionais:
            if f: cmd.extend(["-i", f])

        video_chain_parts = ["[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:-1:-1,setsar=1[v_scaled]"]
        current_stream = "[v_scaled]"

        if caminho_legenda_ass:
            # Escapa o caminho do arquivo de legenda para o filtro do FFMPEG
            escaped_ass_path = caminho_legenda_ass.replace('\\', '/').replace(':', '\\:')
            video_chain_parts.append(f"{current_stream}ass=filename='{escaped_ass_path}'[v_subtitled]")
            current_stream = "[v_subtitled]"

        if not assinatura_ativa:
            # Adiciona marca d'água para usuários não assinantes
            video_chain_parts.append(f"{current_stream}drawtext=text='LUNDERON.COM':x=(w-text_w-10):y=(h-text_h-10):fontsize=32:fontcolor=white@0.5:shadowcolor=black@0.5:shadowx=2:shadowy=2[v_watermarked]")
            current_stream = "[v_watermarked]"

        video_input_offset = 1
        if caminho_imagem_texto:
            video_chain_parts.append(f"{current_stream}[{video_input_offset}:v]overlay=(W-w)/2:(H-h)/2[final_v]")
            video_input_offset += 1
        else:
            video_chain_parts.append(f"{current_stream}copy[final_v]")
        final_video_stream = "[final_v]"

        audio_chain_parts = []
        final_audio_stream = None
        music_input_index, narrator_input_index = -1, -1
        current_audio_input_index = video_input_offset
        if caminho_musica_input:
            music_input_index = current_audio_input_index
            current_audio_input_index += 1
        if caminho_narrador_input:
            narrator_input_index = current_audio_input_index

        if music_input_index != -1 and narrator_input_index != -1:
            # Mixa a música de fundo com o narrador
            volume_musica = data.get("volume_musica", 20) / 100.0
            audio_chain_parts.append(f"[{music_input_index}:a]volume={volume_musica}[bg_audio]")
            audio_chain_parts.append(f"[{narrator_input_index}:a][bg_audio]amix=inputs=2:duration=first:dropout_transition=3[aout]")
            final_audio_stream = "[aout]"
        elif music_input_index != -1:
            # Apenas música de fundo
            volume_musica = data.get("volume_musica", 50) / 100.0
            audio_chain_parts.append(f"[{music_input_index}:a]volume={volume_musica}[aout]")
            final_audio_stream = "[aout]"
        elif narrator_input_index != -1:
            # Apenas áudio do narrador
            audio_chain_parts.append(f"[{narrator_input_index}:a]acopy[aout]")
            final_audio_stream = "[aout]"

        video_chain = ";".join(video_chain_parts)
        if audio_chain_parts:
            audio_chain = ";".join(audio_chain_parts)
            cmd.extend(["-filter_complex", f"{video_chain};{audio_chain}"])
        else:
            cmd.extend(["-filter_complex", video_chain])

        cmd.extend(["-map", final_video_stream])
        if final_audio_stream:
            cmd.extend(["-map", final_audio_stream])
        else:
            cmd.extend(["-an"])
        
        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "28", "-r", "30", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-t", str(duracao_video), caminho_video_temp])

        logger.info(f"[{video_gerado_id}] Executando comando FFMPEG: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        logger.info(f"[{video_gerado_id}] FFMPEG concluído com sucesso.")

        object_key_r2 = f"videos_gerados/video_{user.id}_{random.randint(10000, 99999)}.mp4"
        logger.info(f"[{video_gerado_id}] Fazendo upload do vídeo final para R2: {object_key_r2}")
        if not upload_to_r2(caminho_video_temp, object_key_r2):
            raise Exception("Falha no upload do vídeo final para o Cloudflare R2.")
        logger.info(f"[{video_gerado_id}] Upload para R2 concluído.")

        from .utils import generate_thumbnail_from_video_r2
        logger.info(f"[{video_gerado_id}] Gerando thumbnail...")
        thumbnail_key = generate_thumbnail_from_video_r2(object_key_r2)
        logger.info(f"[{video_gerado_id}] Thumbnail gerada: {thumbnail_key}")

        video.status = "CONCLUIDO"
        video.arquivo_final = object_key_r2
        video.thumbnail_key = thumbnail_key
        video.notificacao_vista = False
        video.save()
        logger.info(f"[{video_gerado_id}] Processamento concluído com SUCESSO.")

    except Exception as e:
        logger.error(f"!!!!!!!!!! ERRO AO PROCESSAR VÍDEO ID {video_gerado_id} !!!!!!!!!!", exc_info=True)
        video.status = "ERRO"
        video.mensagem_erro = str(e)
        video.notificacao_vista = False
        video.save()
        if isinstance(e, subprocess.CalledProcessError):
            logger.error(f"[{video_gerado_id}] Erro FFMPEG (stdout): {e.stdout}")
            logger.error(f"[{video_gerado_id}] Erro FFMPEG (stderr): {e.stderr}")

    finally:
        logger.info(f"[{video_gerado_id}] Iniciando limpeza de arquivos temporários...")
        for caminho in caminhos_para_limpar:
            if caminho and os.path.exists(caminho):
                try:
                    os.remove(caminho)
                    logger.info(f"[{video_gerado_id}] Arquivo temporário removido: {caminho}")
                except OSError as err:
                    logger.error(f"[{video_gerado_id}] Erro ao remover arquivo temporário {caminho}: {err}")
        logger.info(f"[{video_gerado_id}] Limpeza de arquivos temporários finalizada.")


# ==============================================================================
# VIEW DE PRÉ-VISUALIZAÇÃO (NOVA)
# ==============================================================================
@login_required
def videos_por_categoria(request, categoria_id):
    try:
        categoria = get_object_or_404(CategoriaVideo, id=categoria_id)
        videos = (
            VideoBase.objects.filter(categoria=categoria)
            .exclude(object_key__isnull=True)
            .exclude(object_key__exact="")
        )

        videos_data = []
        for video in videos:
            presigned_url = generate_presigned_url(
                video.object_key, expiration=3600
            )  # 1 hour
            if presigned_url:
                videos_data.append(
                    {"id": video.id, "url": presigned_url, "titulo": video.titulo}
                )

        return JsonResponse({"videos": videos_data})

    except Exception as e:
        print(f"Erro ao buscar vídeos por categoria: {e}")
        return JsonResponse({"error": "Ocorreu um erro inesperado."}, status=500)


@login_required
def preview_video_base(request, categoria_id):
    try:
        categoria = get_object_or_404(CategoriaVideo, id=categoria_id)
        video_base = get_valid_media_from_category(VideoBase, categoria)

        if not video_base:
            return JsonResponse(
                {
                    "error": "Nenhum vídeo de base válido encontrado para esta categoria."
                },
                status=404,
            )

        # Gerar uma URL assinada temporária para o vídeo
        presigned_url = generate_presigned_url(
            video_base.object_key, expiration=300
        )  # 5 minutos

        if not presigned_url:
            return JsonResponse(
                {"error": "Falha ao gerar a URL de pré-visualização."},
                status=500,
            )

        return JsonResponse({"url": presigned_url})

    except Exception as e:
        print(f"Erro na pré-visualização do vídeo: {e}")
        return JsonResponse({"error": "Ocorreu um erro inesperado."}, status=500)


@login_required
def download_video_direto(request, video_id):
    """
    Verifica a validade do vídeo. Se for válido, gera um link de download.
    Se expirou, apaga o arquivo e informa o usuário.
    """
    video = get_object_or_404(VideoGerado, id=video_id, usuario=request.user)

    if video.status != "CONCLUIDO" or not video.arquivo_final:
        messages.error(request, "Este vídeo não está mais disponível.")
        return redirect("meus_videos")

    # Define o tempo de vida do vídeo (1 hora)
    tempo_expiracao = video.criado_em + timedelta(hours=1)

    # Verifica se o tempo de vida já passou
    if timezone.now() > tempo_expiracao:
        messages.warning(
            request,
            "O link de download para este vídeo expirou e o arquivo foi removido.",
        )

        # Lógica de limpeza sob demanda
        delete_from_r2(video.arquivo_final)
        video.arquivo_final = None
        video.save()

        return redirect("meus_videos")

    # Se o vídeo ainda é válido, gera o link e redireciona
    presigned_url = generate_presigned_url(
        video.arquivo_final, expiration=600
    )  # Link válido por 10 min

    if not presigned_url:
        messages.error(request, "Não foi possível gerar o link de download no momento.")
        return redirect("meus_videos")

    return redirect(presigned_url)


def estimar_tempo_narracao(texto, velocidade=100):
    """
    Estima o tempo de narração com base no texto e velocidade
    Baseado em: 150 palavras por minuto para velocidade normal (100%)
    """
    # Contar palavras
    palavras = texto.split()
    num_palavras = len(palavras)

    # Palavras por minuto base (velocidade normal)
    ppm_base = 150

    # Garantir que velocidade seja tratada como número (caso venha como string)
    try:
        velocidade_float = float(velocidade)
    except (ValueError, TypeError):
        velocidade_float = 100.0  # Valor padrão se a conversão falhar

    # Ajustar pela velocidade
    ppm_ajustado = ppm_base * (velocidade_float / 100.0)

    # Calcular duração em segundos
    duracao_minutos = num_palavras / ppm_ajustado
    duracao_segundos = duracao_minutos * 60

    return duracao_segundos, num_palavras


def formatar_tempo_ass(segundos):
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    cs = int((segundos - int(segundos)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ================================================================
# NOVA FUNÇÃO DE LEGENDA PRECISA (ESTILO KARAOKÊ)
# ================================================================
def gerar_legenda_karaoke_ass(
    word_timestamps, data, cor_da_fonte_hex, cor_destaque_hex, posicao="centro"
):
    """
    Gera uma legenda .ASS com sincronização precisa por palavra (efeito karaokê)
    a partir dos timestamps extraídos pelo Whisper.
    """
    # Configurações de estilo (esta parte não muda)
    nome_fonte = data.get("texto_fonte", "Arial")
    tamanho = data.get("texto_tamanho", 70)
    negrito = -1 if data.get("texto_negrito", False) else 0
    sublinhado = -1 if data.get("texto_sublinhado", False) else 0

    # Converte a cor principal (texto não dito) para o formato BGR do ASS
    try:
        hex_limpo = cor_da_fonte_hex.lstrip("#")
        r, g, b = tuple(int(hex_limpo[i : i + 2], 16) for i in (0, 2, 4))
        cor_primaria_ass = f"&H00{b:02X}{g:02X}{r:02X}"
    except (ValueError, IndexError):
        cor_primaria_ass = "&H00FFFFFF"  # Branco opaco como padrão

    # Converte a cor de destaque (texto dito) para o formato BGR do ASS
    try:
        hex_limpo_destaque = cor_destaque_hex.lstrip("#")
        r_s, g_s, b_s = tuple(int(hex_limpo_destaque[i : i + 2], 16) for i in (0, 2, 4))
        cor_secundaria_ass = f"&H00{b_s:02X}{g_s:02X}{r_s:02X}"
    except (ValueError, IndexError, TypeError):
        cor_secundaria_ass = "&H0000FFFF"  # Amarelo opaco como padrão

    cor_outline = "&H00000000"
    cor_back = "&H80000000"

    alignment_code = 5 if posicao == "centro" else 2
    margin_v = 150 if posicao == "inferior" else 50

    header = (
        f"[Script Info]\nTitle: Legenda Sincronizada com Precisão\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        f"[V4+ Styles]\n"
        f"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{nome_fonte},{tamanho},{cor_primaria_ass},{cor_secundaria_ass},{cor_outline},{cor_back},{negrito},0,{sublinhado},0,100,100,0,0,1,2,2,{alignment_code},30,30,{margin_v},1\n\n"
        f"[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    dialogos = []
    palavras_por_linha = 4

    linhas = [
        word_timestamps[i : i + palavras_por_linha]
        for i in range(0, len(word_timestamps), palavras_por_linha)
    ]

    for linha in linhas:
        if not linha:
            continue

        start_time_linha = linha[0]["start"]
        end_time_linha = linha[-1]["end"]

        texto_karaoke = ""
        for palavra in linha:
            duracao_cs = int((palavra["end"] - palavra["start"]) * 100)
            # CORREÇÃO: Formata a tag de karaoke para o padrão ASS {\k<duração>}
            texto_karaoke += f"{{\k{duracao_cs}}}{palavra['word'].strip()} "

        dialogos.append(
            f"Dialogue: 0,{formatar_tempo_ass(start_time_linha)},{formatar_tempo_ass(end_time_linha)},Default,,0,0,0,,{texto_karaoke.strip()}"
        )

    conteudo_ass = header + "\n".join(dialogos)

    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".ass", encoding="utf-8"
    ) as temp_f:
        temp_f.write(conteudo_ass)
        caminho_legenda = temp_f.name

    return caminho_legenda


@require_POST
@csrf_exempt
def estimativa_narracao(request):
    try:
        data = json.loads(request.body)
        texto = data.get("texto", "")
        velocidade = data.get("velocidade", 100)

        # Função para estimar tempo de narração
        def estimar_tempo_narracao(texto, velocidade=100):
            """
            Estima o tempo de narração com base no texto e velocidade
            Baseado em: 150 palavras por minuto para velocidade normal (100%)
            """
            # Contar palavras
            palavras = texto.split()
            num_palavras = len(palavras)

            # Palavras por minuto base (velocidade normal)
            ppm_base = 150

            # Ajustar pela velocidade
            ppm_ajustado = ppm_base * (velocidade / 100.0)

            # Calcular duração em segundos
            duracao_minutos = num_palavras / ppm_ajustado
            duracao_segundos = duracao_minutos * 60

            return duracao_segundos, num_palavras

        duracao_segundos, num_palavras = estimar_tempo_narracao(texto, velocidade)

        return JsonResponse(
            {"duracao_segundos": duracao_segundos, "num_palavras": num_palavras}
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ==============================================================================
# FUNÇÃO DE VERIFICAÇÃO DE ADMIN
# ==============================================================================
def is_admin(user):
    """Verifica se o usuário é parte da equipe (staff)."""
    return user.is_staff


# ==============================================================================
# VIEWS PÚBLICAS E DE AUTENTICAÇÃO
# ==============================================================================


def index(request):
    return render(request, "core/home.html")


def como_funciona(request):
    return render(request, "core/como_funciona.html")


def planos(request):
    return render(request, "core/planos.html")


def suporte(request):
    return render(request, "core/suporte.html")


def termos_de_servico(request):
    return render(request, "core/termos_de_servico.html")


def politica_de_privacidade(request):
    return render(request, "core/politica_de_privacidade.html")


def verificar_email(request, token):
    try:
        # 1. Tenta encontrar um usuário que tenha exatamente este token.
        user = Usuario.objects.get(email_verification_token=token)
    except Usuario.DoesNotExist:
        # 2. Se não encontrar, o link é inválido.
        messages.error(request, "Link de verificação inválido ou já utilizado.")
        return redirect("login")

    # 3. Verifica se o token não expirou (a lógica está em utils.py)
    if is_token_valid(user, token):
        # 4. Se tudo estiver certo, ativa o usuário e marca como verificado.
        user.is_active = True
        user.email_verificado = True
        user.email_verification_token = None  # Limpa o token para não ser usado de novo
        user.email_verification_token_created = None
        user.save()

        # 5. Loga o usuário automaticamente e o envia para o painel.
        login(request, user)
        messages.success(
            request,
            "E-mail verificado com sucesso! Bem-vindo(a) à Lunderon.",
        )
        return redirect("meu_perfil")
    else:
        # 6. Se o token expirou, informa o usuário.
        messages.error(
            request,
            "Seu link de verificação expirou. Por favor, tente se cadastrar novamente.",
        )
        return redirect("login")


def cadastre_se(request):
    from .forms import CadastroUsuarioForm

    if request.method == "POST":
        form = CadastroUsuarioForm(request.POST)
        if form.is_valid():
            # Cria o usuário, mas não salva no banco ainda
            user = form.save(commit=False)
            # Define o usuário como inativo até que o e-mail seja verificado
            user.is_active = False
            user.save()

            # Tenta enviar o e-mail de verificação
            try:
                send_verification_email(user, request)
                messages.success(
                    request,
                    "Cadastro realizado com sucesso! Enviamos um link de ativação para o seu e-mail.",
                )
            except Exception as e:
                # Informa sobre o erro no terminal para debug
                print(f"ERRO AO ENVIAR E-MAIL DE VERIFICAÇÃO: {e}")
                messages.error(
                    request,
                    "Ocorreu um erro ao enviar o e-mail de verificação. Por favor, tente novamente ou contate o suporte.",
                )

            # Redireciona para a página de login, onde a mensagem de sucesso/erro será exibida
            return redirect("login")
    else:
        form = CadastroUsuarioForm()
    return render(request, "core/user/cadastre-se.html", {"form": form})


def validate_otp_view(request):
    # 
    # ATENÇÃO: Este é um código temporário para o site não quebrar.
    # Você precisa substituir este conteúdo pela sua lógica original
    # que valida o código OTP do usuário.
    #

    # Por enquanto, esta função apenas redireciona o usuário para o perfil.
    print("LOG: Acessou a view 'validate_otp_view' com sucesso!")
    messages.success(request, "Validação concluída!")
    return redirect("meu_perfil")


def reenviar_verificacao_email(request, user_id):
    try:
        user = Usuario.objects.get(id=user_id)
        if not user.is_active:
            send_verification_email(user, request)
            messages.success(
                request,
                "Um novo link de verificação foi enviado para o seu e-mail.",
            )
        else:
            messages.info(
                request,
                "Esta conta já está ativa. Você pode fazer login normalmente.",
            )
    except Usuario.DoesNotExist:
        messages.error(request, "Usuário não encontrado.")

    return redirect("login")


def login_view(request):
    if request.method == "POST":
        email_digitado = request.POST.get("email")
        password_digitado = request.POST.get("password")

        if not email_digitado or not password_digitado:
            messages.error(request, "Por favor, preencha o email e a senha.")
            return render(request, "core/login.html")

        try:
            # 1. Primeiro, apenas busca o usuário pelo e-mail, sem verificar a senha.
            user_encontrado = Usuario.objects.get(email=email_digitado)

            # 2. VERIFICA SE A CONTA ESTÁ ATIVA.
            if not user_encontrado.is_active:
                # Se não estiver ativa, mostra uma mensagem específica com um link para reenviar o e-mail.
                resend_url = reverse(
                    "reenviar_verificacao", kwargs={"user_id": user_encontrado.id}
                )
                mensagem = mark_safe(
                    f"Sua conta ainda não foi ativada. Por favor, verifique o link que enviamos para o seu e-mail. "
                    f'<a href="{resend_url}" class="alert-link">Não recebeu? Clique aqui para reenviar.</a>'
                )
                messages.warning(request, mensagem)
                return redirect("login")

            # 3. Se a conta estiver ativa, aí sim tentamos autenticar com a senha.
            user = authenticate(
                request, username=user_encontrado.username, password=password_digitado
            )

            if user is not None:
                login(request, user)
                return redirect("meu_perfil")
            else:
                # Se chegou aqui, a conta é ativa, mas a senha está errada.
                messages.error(request, "Email ou senha inválidos.")

        except Usuario.DoesNotExist:
            # Se o e-mail nem existe no banco de dados.
            messages.error(request, "Email ou senha inválidos.")

    return render(request, "core/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
@user_passes_test(is_admin)
def admin_ativar_usuario(request, user_id):
    """
    Ativa a conta de um usuário manualmente pelo painel de admin.
    """
    user_para_ativar = get_object_or_404(Usuario, id=user_id)
    user_para_ativar.is_active = True
    user_para_ativar.email_verificado = True
    user_para_ativar.save()
    messages.success(
        request,
        f'O usuário "{user_para_ativar.username}" foi ativado com sucesso.',
    )
    return redirect("admin_usuarios")


@login_required
@user_passes_test(is_admin)
def admin_reenviar_verificacao(request, user_id):
    """
    Reenvia o e-mail de verificação para um usuário inativo.
    """
    user_para_verificar = get_object_or_404(Usuario, id=user_id)
    if not user_para_verificar.is_active:
        try:
            send_verification_email(user_para_verificar, request)
            messages.success(
                request,
                f"E-mail de verificação reenviado para {user_para_verificar.email}.",
            )
        except Exception as e:
            messages.error(request, "Ocorreu um erro ao tentar reenviar o e-mail.")
            print(f"ERRO AO REENVIAR E-MAIL ADMIN: {e}")
    else:
        messages.warning(
            request,
            f'O usuário "{user_para_verificar.username}" já está ativo.',
        )

    return redirect("admin_usuarios")


# ==============================================================================
# VIEWS DA APLICAÇÃO (requerem login)
# ==============================================================================
def pagamento_falho(request):
    """
    Renderiza a página de pagamento falho.
    """
    from .forms import EditarPerfilForm

    return render(request, "planos/pagamento_falho.html")


@csrf_exempt
def stripe_webhook(request):
    """
    CORRIGIDO E OTIMIZADO: Escuta os eventos do Stripe para gerenciar o ciclo de vida
    completo das assinaturas de forma automática e robusta.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    event = None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        print(f"🚨 ERRO no webhook: Payload ou assinatura inválida. Detalhes: {e}")
        return HttpResponse(status=400)

    # --- LÓGICA DE PAGAMENTO BEM-SUCEDIDO (CRIAÇÃO INICIAL) ---
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        stripe_customer_id = session.get("customer")
        stripe_subscription_id = session.get("subscription")
        plano_id = session.get("metadata", {}).get("plano_id")
        valor_pago = session.get("amount_total", 0) / 100

        try:
            usuario = Usuario.objects.get(stripe_customer_id=stripe_customer_id)
            plano = Plano.objects.get(id=plano_id)

            # 1. ATUALIZA o ID da assinatura no usuário
            usuario.stripe_subscription_id = stripe_subscription_id
            usuario.save()

            # 2. USA 'update_or_create' para criar ou ATUALIZAR a assinatura
            # Isso é mais seguro que 'get_or_create' pois lida com casos onde já existe uma assinatura antiga.
            assinatura, created = Assinatura.objects.update_or_create(
                usuario=usuario,
                defaults={
                    "plano": plano,
                    "status": "ativo",  # Define o status como 'ativo'
                    "data_inicio": timezone.now(),
                    "data_expiracao": timezone.now() + timedelta(days=30),
                },
            )
            # O método .save() da Assinatura já vai garantir que 'usuario.plano_ativo' seja True.

            # 3. CRIA O REGISTRO DO PAGAMENTO
            Pagamento.objects.create(
                usuario=usuario, plano=plano, valor=valor_pago, status="aprovado"
            )

            print(
                f"✅ Assinatura e Pagamento registrados com sucesso para: {usuario.email}"
            )

        except (Usuario.DoesNotExist, Plano.DoesNotExist) as e:
            print(
                f"🚨 ERRO no webhook (checkout.session.completed): Usuário ou Plano não encontrado. Detalhes: {e}"
            )
            return HttpResponse(status=404)

    # --- LÓGICA DE RENOVAÇÃO (PAGAMENTOS RECORRENTES) ---
    elif event["type"] == "invoice.paid":
        invoice = event["data"]["object"]
        stripe_subscription_id = invoice.get("subscription")
        valor_pago = invoice.get("amount_paid", 0) / 100

        # Ignora invoices sem subscription_id (pagamentos únicos)
        if stripe_subscription_id:
            try:
                # Encontra a assinatura pela ID de inscrição do Stripe
                assinatura = Assinatura.objects.get(
                    usuario__stripe_subscription_id=stripe_subscription_id
                )

                # 1. Garante que o status está ativo e estende a data de expiração
                assinatura.status = "ativo"
                assinatura.data_expiracao = (
                    assinatura.data_expiracao or timezone.now()
                ) + timedelta(days=30)
                assinatura.save()  # O .save() já atualiza o 'plano_ativo' do usuário para True

                # 2. Cria um novo registro de Pagamento para a renovação
                Pagamento.objects.create(
                    usuario=assinatura.usuario,
                    plano=assinatura.plano,
                    valor=valor_pago,
                    status="aprovado",
                )

                print(
                    f"✅ Renovação processada para: {assinatura.usuario.email}. Nova expiração: {assinatura.data_expiracao.strftime('%d/%m/%Y')}"
                )

            except Assinatura.DoesNotExist as e:
                print(
                    f"🚨 ERRO no webhook (invoice.paid): Assinatura não encontrada para o subscription_id {stripe_subscription_id}. Detalhes: {e}"
                )
                return HttpResponse(status=404)

    # --- LÓGICA DE PAGAMENTO FALHO (RENOVAÇÃO RECUSADA) ---
    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        stripe_subscription_id = invoice.get("subscription")

        if stripe_subscription_id:
            try:
                assinatura = Assinatura.objects.get(
                    usuario__stripe_subscription_id=stripe_subscription_id
                )

                # 1. Altera o status da assinatura para 'pendente'
                assinatura.status = "pendente"
                assinatura.save()  # O .save() já vai atualizar o 'plano_ativo' do usuário para False

                print(
                    f"⚠️ Pagamento falhou para: {assinatura.usuario.email}. Assinatura marcada como 'pendente'."
                )
                # Aqui você pode adicionar lógica para notificar o usuário por e-mail.

            except Assinatura.DoesNotExist as e:
                print(
                    f"🚨 ERRO no webhook (invoice.payment_failed): Assinatura não encontrada para {stripe_subscription_id}. Detalhes: {e}"
                )

    # --- LÓGICA DE CANCELAMENTO (pelo cliente ou por falhas de pagamento) ---
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        stripe_subscription_id = subscription.get("id")

        try:
            assinatura = Assinatura.objects.get(
                usuario__stripe_subscription_id=stripe_subscription_id
            )

            # 1. Altera o status da assinatura para 'cancelado'
            assinatura.status = "cancelado"
            # Opcional: Define a data de expiração para agora se desejar
            # assinatura.data_expiracao = timezone.now()
            assinatura.save()  # O .save() já vai atualizar o 'plano_ativo' do usuário para False

            print(
                f"✅ Assinatura cancelada no sistema para: {assinatura.usuario.email}"
            )

        except Assinatura.DoesNotExist as e:
            print(
                f"🚨 ERRO no webhook (subscription.deleted): Assinatura não encontrada para {stripe_subscription_id}. Detalhes: {e}"
            )

    return HttpResponse(status=200)


@login_required
def editar_perfil(request):
    from .forms import EditarPerfilForm

    if request.method == "POST":
        form = EditarPerfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Seu perfil foi atualizado com sucesso!")
            return redirect("meu_perfil")
    else:
        form = EditarPerfilForm(instance=request.user)

    return render(request, "core/usuarios/editar_perfil.html", {"form": form})


@login_required
def meu_perfil(request):
    # A linha abaixo busca TUDO o que precisamos: os vídeos criados,
    # o limite correto do plano do usuário e a assinatura dele.
    videos_criados_no_mes, limite_videos_mes, assinatura = _get_user_video_usage(
        request.user
    )

    context = {
        "user": request.user,
        "assinatura": assinatura,
        "videos_criados_no_mes": videos_criados_no_mes,
        "limite_videos_mes": limite_videos_mes,
    }
    return render(request, "core/usuarios/perfil.html", context)


@login_required
def gerenciar_assinatura_redirect(request):
    """
    Cria uma sessão no portal de clientes do Stripe e redireciona o usuário para lá.
    """
    # Busca o ID do cliente no Stripe que guardamos no nosso modelo Usuario
    stripe_customer_id = request.user.stripe_customer_id

    # Se o usuário não for um cliente no Stripe ainda, não há o que gerenciar
    if not stripe_customer_id:
        messages.error(request, "Não encontramos uma assinatura para gerenciar.")
        return redirect("meu_perfil")

    try:
        # Constrói a URL de retorno completa para o seu site
        return_url = request.build_absolute_uri(reverse("meu_perfil"))

        # Cria a sessão do portal de clientes na API do Stripe
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        # Redireciona o usuário para a URL do portal gerada pelo Stripe
        return redirect(session.url)

    except Exception as e:
        messages.error(request, "Ocorreu um erro ao acessar o portal de assinaturas.")
        print(f"Erro do Stripe: {e}")  # Para você ver o erro no terminal
        return redirect("meu_perfil")


# ==============================================================================
# PAINEL DE ADMINISTRAÇÃO CUSTOMIZADO (PROTEGIDO)
# ==============================================================================


@login_required
@user_passes_test(is_admin)
def admin_assinaturas(request):
    assinaturas = Assinatura.objects.select_related("usuario", "plano").all()
    return render(
        request, "core/user/admin_assinaturas.html", {"assinaturas": assinaturas}
    )


# Em seu arquivo core/views.py

# Certifique-se de que 'os' está importado no topo do seu arquivo


# ... (resto dos seus imports e views)


def planos(request):
    """
    Exibe a página de Planos. Para usuários logados e com plano ativo,
    mostra o status da assinatura. Para outros, mostra os planos para contratação.
    """
    if request.user.is_authenticated and request.user.plano_ativo:
        # Esta parte já está correta, buscando o uso e limite do plano do usuário.
        videos_criados_no_mes, limite_videos_mes, assinatura_ativa = (
            _get_user_video_usage(request.user)
        )

        if not assinatura_ativa:
            # Caso de segurança se plano_ativo=True mas não há assinatura
            return redirect(
                "planos"  # Redireciona para a mesma página para reavaliar a lógica abaixo
            )

        uso_percentual = 0
        if limite_videos_mes > 0:
            uso_percentual = (videos_criados_no_mes / limite_videos_mes) * 100

        context = {
            "assinatura": assinatura_ativa,
            "videos_criados_no_mes": videos_criados_no_mes,
            "limite_videos_mes": limite_videos_mes,
            "uso_percentual": uso_percentual,
        }
        return render(request, "core/planos/plano_ativo.html", context)

    # --- CORREÇÃO APLICADA AQUI ---
    # Para usuários não assinantes, buscamos todos os planos para exibi-los na página.
    todos_os_planos = Plano.objects.order_by("preco")
    context = {
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "planos": todos_os_planos,  # Adiciona a lista de planos ao contexto
    }
    # --- FIM DA CORREÇÃO ---

    return render(request, "core/planos/planos.html", context)


@login_required
@user_passes_test(is_admin)
def ativar_assinatura(request, id):
    assinatura = get_object_or_404(Assinatura, id=id)

    # --- INÍCIO DA MELHORIA ---
    # Garante que o usuário também seja ativado junto com a assinatura
    usuario = assinatura.usuario
    if not usuario.is_active:
        usuario.is_active = True
        usuario.email_verificado = True
        usuario.save(update_fields=["is_active", "email_verificado"])
    # --- FIM DA MELHORIA ---

    assinatura.status = "ativo"
    assinatura.save()  # O .save() da assinatura já cuida do campo 'plano_ativo'

    messages.success(
        request,
        f"Assinatura de {assinatura.usuario.username} ativada com sucesso. A conta do usuário também foi ativada.",
    )
    return redirect("admin_assinaturas")


@login_required
@user_passes_test(is_admin)
def cancelar_assinatura(request, id):
    assinatura = get_object_or_404(Assinatura, id=id)
    assinatura.status = "cancelado"
    assinatura.save()
    messages.warning(request, f"Assinatura de {assinatura.usuario.username} cancelada.")
    return redirect("admin_assinaturas")


@login_required
@user_passes_test(is_admin)
def editar_assinatura(request, id):
    from .forms import EditarAssinaturaForm

    assinatura = get_object_or_404(Assinatura, id=id)
    if request.method == "POST":
        form = EditarAssinaturaForm(request.POST, instance=assinatura)
        if form.is_valid():
            form.save()
            messages.info(request, "Assinatura atualizada com sucesso.")
            return redirect("admin_assinaturas")
    else:
        form = EditarAssinaturaForm(instance=assinatura)

    contexto = {"form": form, "assinatura": assinatura}
    return render(request, "core/user/editar_assinatura.html", contexto)


@login_required
@user_passes_test(is_admin)
def excluir_assinatura(request, id):
    assinatura = get_object_or_404(Assinatura, id=id)
    if request.method == "POST":
        assinatura.delete()
        messages.error(request, "Assinatura excluída.")
        return redirect("admin_assinaturas")
    contexto = {"item": assinatura}
    return render(request, "core/user/confirmar_exclusao.html", contexto)


# Em core/views.py


# Em core/views.py

# Garanta que os imports necessários estão no topo do arquivo
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

# (e outros imports necessários)


@user_passes_test(is_admin)
def admin_usuarios(request):
    trinta_dias_atras = timezone.now() - timedelta(days=30)

    # --- INÍCIO DA CORREÇÃO ---
    # Trocamos 'select_related' por 'prefetch_related' e usamos 'assinatura_set__plano'
    # para otimizar a busca reversa da assinatura e do plano associado.
    usuarios = (
        Usuario.objects.prefetch_related("assinatura_set__plano")
        .annotate(
            videos_no_mes=Count(
                "videogerado",
                filter=Q(videogerado__criado_em__gte=trinta_dias_atras)
                & ~Q(videogerado__status="ERRO"),
            )
        )
        .order_by("-date_joined")
    )
    # --- FIM DA CORREÇÃO ---

    contexto = {
        "usuarios": usuarios,
        # A variável 'limite_videos_mes' foi corretamente removida,
        # pois o template agora busca o limite do plano de cada usuário.
    }

    return render(request, "core/user/admin_usuarios.html", contexto)


@login_required
@user_passes_test(is_admin)
def editar_usuario(request, user_id):
    from .forms import AdminUsuarioForm

    user = get_object_or_404(Usuario, id=user_id)
    assinatura = (
        Assinatura.objects.filter(usuario=user).order_by("-data_inicio").first()
    )

    if request.method == "POST":
        form = AdminUsuarioForm(request.POST)
        if form.is_valid():
            # Atualiza os dados do Usuário
            user.username = form.cleaned_data["username"]
            user.email = form.cleaned_data["email"]
            user.is_staff = form.cleaned_data["is_staff"]
            user.save()

            # Lógica para gerenciar a Assinatura
            plano_selecionado = form.cleaned_data["plano"]
            status_selecionado = form.cleaned_data["status"]

            if plano_selecionado:
                # --- INÍCIO DA ATUALIZAÇÃO ---
                # Busca a duração da assinatura no banco de dados
                try:
                    config_duracao = Configuracao.objects.get(
                        nome="DURACAO_ASSINATURA_DIAS"
                    )
                    # Converte o valor (que é texto) para um número inteiro
                    duracao_dias = int(config_duracao.valor)
                except (Configuracao.DoesNotExist, ValueError):
                    # Se não encontrar ou o valor não for um número, usa 30 como padrão
                    duracao_dias = 30
                # --- FIM DA ATUALIZAÇÃO ---

                if assinatura:
                    # Se já existe uma assinatura, atualiza
                    assinatura.plano = plano_selecionado
                    assinatura.status = status_selecionado
                    if status_selecionado == "ativo":
                        # Usa a duração vinda do banco de dados
                        assinatura.data_expiracao = timezone.now() + timedelta(
                            days=duracao_dias
                        )
                    assinatura.save()
                else:
                    # Se não existe e um plano foi selecionado, cria uma nova
                    Assinatura.objects.create(
                        usuario=user,
                        plano=plano_selecionado,
                        status=status_selecionado,
                        data_inicio=timezone.now(),
                        # Usa a duração vinda do banco de dados
                        data_expiracao=timezone.now() + timedelta(days=duracao_dias),
                    )
                messages.success(request, f"Assinatura de {user.username} atualizada.")

            elif assinatura:
                assinatura.status = "cancelado"
                assinatura.save()
                messages.warning(request, f"Assinatura de {user.username} cancelada.")

            messages.success(
                request, f'Usuário "{user.username}" atualizado com sucesso!'
            )
            return redirect("admin_usuarios")
    else:
        initial_data = {
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
        }
        if assinatura:
            initial_data["plano"] = assinatura.plano
            initial_data["status"] = assinatura.status

        form = AdminUsuarioForm(initial=initial_data)

    contexto = {"form": form, "usuario_editando": user, "assinatura": assinatura}
    return render(request, "core/user/editar_usuario.html", contexto)


@login_required
@user_passes_test(is_admin)
def deletar_usuario(request, user_id):
    user = get_object_or_404(Usuario, id=user_id)
    if request.method == "POST":
        user.delete()
        messages.error(request, "Usuário excluído.")
        return redirect("admin_usuarios")
    contexto = {"item": user}
    return render(request, "core/user/confirmar_exclusao.html", contexto)


@login_required
@user_passes_test(is_admin)
def admin_configuracoes(request):
    configuracoes = Configuracao.objects.all()
    return render(
        request, "core/user/admin_configuracoes.html", {"configuracoes": configuracoes}
    )


@login_required
@user_passes_test(is_admin)
def adicionar_configuracao(request):
    from .forms import ConfiguracaoForm

    if request.method == "POST":
        form = ConfiguracaoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Nova configuração salva com sucesso.")
            return redirect("admin_configuracoes")
    else:
        form = ConfiguracaoForm()
    contexto = {"form": form}
    return render(request, "core/user/adicionar_configuracao.html", contexto)


@login_required
@user_passes_test(is_admin)
def editar_configuracao(request, id):
    from .forms import ConfiguracaoForm

    config = get_object_or_404(Configuracao, id=id)
    if request.method == "POST":
        form = ConfiguracaoForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.info(request, "Configuração atualizada com sucesso.")
            return redirect("admin_configuracoes")
    else:
        form = ConfiguracaoForm(instance=config)

    contexto = {"form": form, "config": config}
    return render(request, "core/user/editar_configuracao.html", contexto)


@login_required
@user_passes_test(is_admin)
def deletar_configuracao(request, id):
    config = get_object_or_404(Configuracao, id=id)
    if request.method == "POST":
        config.delete()
        messages.error(request, f"A configuração '{config.nome}' foi excluída.")
        return redirect("admin_configuracoes")

    # Se a requisição for GET, mostra uma página de confirmação
    contexto = {"item": config}
    return render(request, "core/user/confirmar_exclusao.html", contexto)


@login_required
@user_passes_test(is_admin)
def admin_pagamentos(request):
    pagamentos = Pagamento.objects.select_related("usuario", "plano").all()
    return render(
        request, "core/user/admin_pagamentos.html", {"pagamentos": pagamentos}
    )


@login_required
@user_passes_test(is_admin)
def aprovar_pagamento(request, id):
    pagamento = get_object_or_404(Pagamento, id=id)
    usuario = pagamento.usuario

    # 1. Atualiza o status do pagamento
    pagamento.status = "aprovado"
    pagamento.save()

    # --- INÍCIO DA MELHORIA ---
    # 2. Ativa e verifica a conta do usuário automaticamente para garantir o acesso
    usuario.is_active = True
    usuario.email_verificado = True
    usuario.save(update_fields=["is_active", "email_verificado"])

    # 3. Busca a duração padrão da assinatura nas configurações
    try:
        config_duracao = Configuracao.objects.get(nome="DURACAO_ASSINATURA_DIAS")
        duracao_dias = int(config_duracao.valor)
    except (Configuracao.DoesNotExist, ValueError):
        duracao_dias = 30  # Usa 30 dias como padrão se não encontrar

    # 4. Atualiza ou cria a ASSINATURA do usuário, deixando-a ativa
    Assinatura.objects.update_or_create(
        usuario=usuario,
        defaults={
            "plano": pagamento.plano,
            "status": "ativo",
            "data_expiracao": timezone.now() + timedelta(days=duracao_dias),
        },
    )
    # --- FIM DA MELHORIA ---

    messages.success(
        request,
        f"Pagamento de {usuario.username} aprovado. A assinatura e a conta do usuário foram ativadas.",
    )
    return redirect("admin_pagamentos")


@login_required
@user_passes_test(is_admin)
def recusar_pagamento(request, id):
    pagamento = get_object_or_404(Pagamento, id=id)
    usuario = pagamento.usuario

    # 1. Atualiza o status do pagamento
    pagamento.status = "recusado"
    pagamento.save()

    # --- INÍCIO DA CORREÇÃO ---
    # 2. Busca a assinatura do usuário (se existir)
    assinatura = Assinatura.objects.filter(usuario=usuario).first()
    if assinatura:
        # 3. Altera o status da assinatura para pendente
        #    Isso vai desativar o acesso do usuário ao gerador
        assinatura.status = "pendente"
        assinatura.save()
        messages.warning(
            request,
            f"Pagamento de {usuario.username} recusado e assinatura marcada como pendente.",
        )
    else:
        messages.warning(request, f"Pagamento de {usuario.username} recusado.")
    # --- FIM DA CORREÇÃO ---

    return redirect("admin_pagamentos")


@login_required
@user_passes_test(is_admin)
def deletar_pagamento(request, id):
    pagamento = get_object_or_404(Pagamento, id=id)
    if request.method == "POST":
        pagamento.delete()
        messages.error(request, "Pagamento excluído.")
        return redirect("admin_pagamentos")
    contexto = {"item": pagamento}
    return render(request, "core/user/confirmar_exclusao.html", contexto)


@login_required
@user_passes_test(is_admin)
def admin_relatorios(request):
    # --- LÓGICA EXISTENTE ---
    assinaturas = Assinatura.objects.select_related("usuario", "plano").order_by(
        "-data_inicio"
    )
    pagamentos = Pagamento.objects.select_related("usuario", "plano").order_by(
        "-data_pagamento"
    )

    # --- CÁLCULO DOS KPIs ---
    total_assinantes_ativos = Assinatura.objects.filter(status="ativo").count()
    receita_total = (
        Pagamento.objects.filter(status="aprovado").aggregate(soma=Sum("valor"))["soma"]
        or 0
    )
    trinta_dias_atras = timezone.now() - timedelta(days=30)
    novos_assinantes = Assinatura.objects.filter(
        data_inicio__gte=trinta_dias_atras
    ).count()
    total_videos_gerados = VideoGerado.objects.filter(status="CONCLUIDO").count()
    total_videos_falhos = VideoGerado.objects.filter(status="ERRO").count()
    total_videos_processando = VideoGerado.objects.filter(status="PROCESSANDO").count()

    # --- LÓGICA NOVA ADICIONADA ---
    # Conta usuários que não são admins e que ainda estão inativos (não verificaram e-mail)
    usuarios_pendentes = Usuario.objects.filter(is_active=False, is_staff=False).count()
    # Pega os 5 últimos usuários pendentes para exibir na nova tabela
    ultimos_pendentes = Usuario.objects.filter(
        is_active=False, is_staff=False
    ).order_by("-date_joined")[:5]

    context = {
        "assinaturas": assinaturas,
        "pagamentos": pagamentos,
        "total_assinantes_ativos": total_assinantes_ativos,
        "receita_total": receita_total,
        "novos_assinantes": novos_assinantes,
        "total_videos_gerados": total_videos_gerados,
        "total_videos_falhos": total_videos_falhos,
        "total_videos_processando": total_videos_processando,
        # --- NOVOS DADOS ENVIADOS PARA O TEMPLATE ---
        "usuarios_pendentes": usuarios_pendentes,
        "ultimos_pendentes": ultimos_pendentes,
    }
    return render(request, "core/user/admin_relatorios.html", context)


@login_required
def pagamento_sucesso(request):
    """
    Apenas exibe uma mensagem de sucesso. A ativação real do plano é feita pelo webhook.
    """
    messages.success(
        request, "Pagamento recebido com sucesso! Seu plano será ativado em instantes."
    )
    return render(request, "core/pagamento_sucesso.html")


@login_required
def criar_checkout_session(request, plano_id):
    """
    Cria uma sessão de checkout no Stripe para um plano específico que o usuário selecionou.
    """
    if request.user.plano_ativo:
        messages.warning(request, "Você já possui um plano ativo.")
        return redirect("plano_ativo")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        # 1. Busca o plano específico pelo ID vindo da URL.
        plano = get_object_or_404(Plano, id=plano_id)

        # Valida se o plano tem um Price ID do Stripe configurado
        if not plano.stripe_price_id:
            messages.error(
                request,
                "Este plano não está configurado para pagamento. Por favor, contate o suporte.",
            )
            return redirect("planos")

        # 2. Busca ou cria o cliente no Stripe.
        stripe_customer_id = request.user.stripe_customer_id
        if not stripe_customer_id:
            customer = stripe.Customer.create(
                email=request.user.email, name=request.user.username
            )
            request.user.stripe_customer_id = customer.id
            request.user.save()
            stripe_customer_id = customer.id

        # 3. Define as URLs de sucesso e cancelamento.
        success_url = request.build_absolute_uri(reverse("pagamento_sucesso"))
        cancel_url = request.build_absolute_uri(reverse("planos"))

        # 4. Cria a sessão de Checkout no Stripe usando o Price ID do plano selecionado.
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            payment_method_types=["card"],
            line_items=[
                {
                    "price": plano.stripe_price_id,  # <-- CORREÇÃO PRINCIPAL AQUI
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "plano_id": plano.id  # Envia o ID do nosso banco de dados para o webhook
            },
        )

        return redirect(checkout_session.url, code=303)

    except Exception as e:
        messages.error(
            request,
            "Não foi possível iniciar o processo de pagamento. Tente novamente mais tarde.",
        )
        print(f"Erro do Stripe ao criar checkout: {e}")
        return redirect(reverse("planos"))


# ==============================================================================
# VIEWS ADICIONADAS PARA GERENCIAMENTO DE STATUS PELO ADMIN
# ==============================================================================


@user_passes_test(lambda u: u.is_staff)  # Garante que apenas admins acessem
def deixar_assinatura_pendente(request, assinatura_id):
    """
    View para o admin marcar uma assinatura como 'pendente'.
    """
    assinatura = get_object_or_404(Assinatura, id=assinatura_id)
    assinatura.status = "pendente"
    assinatura.save()  # O método save que modificamos cuidará de atualizar o usuário
    messages.warning(
        request,
        f"A assinatura de {assinatura.usuario.username} foi marcada como pendente.",
    )
    return redirect("admin_usuarios")  # Redireciona de volta para a lista de usuários


@user_passes_test(lambda u: u.is_staff)  # Garante que apenas admins acessem
def cancelar_assinatura_admin(request, assinatura_id):
    """
    View para o admin cancelar uma assinatura.
    """
    assinatura = get_object_or_404(Assinatura, id=assinatura_id)
    assinatura.status = "cancelado"
    assinatura.save()  # O método save que modificamos cuidará de atualizar o usuário
    messages.error(
        request, f"A assinatura de {assinatura.usuario.username} foi cancelada."
    )
    return redirect("admin_usuarios")  # Redireciona de volta para a lista de usuários


@login_required
@require_POST
@csrf_exempt
def get_youtube_most_replayed_segments(request):
    """
    Endpoint AJAX que recebe uma URL do YouTube, busca a página
    e extrai os timestamps dos segmentos "mais repetidos", evitando duplicatas.
    """
    try:
        data = json.loads(request.body)
        youtube_url = data.get("url")
        if not youtube_url or "youtube.com" not in youtube_url:
            return JsonResponse({"error": "URL do YouTube inválida."}, status=400)

        headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR,pt;q=0.9"}
        response = requests.get(youtube_url, headers=headers)
        response.raise_for_status()

        # Regex para encontrar o objeto ytInitialData
        match = re.search(r'window["|\"]ytInitialData["|\"] = ({.*?});', response.text)
        if not match:
            match = re.search(r"var ytInitialData = ({.*?});", response.text)

        if not match:
            return JsonResponse(
                {
                    "error": "Não foi possível encontrar os dados do vídeo na página. O vídeo pode ter restrição de idade, ser privado ou a estrutura do YouTube mudou."
                },
                status=404,
            )

        initial_data = json.loads(match.group(1))

        # Navega pela estrutura do JSON para encontrar os marcadores
        decorations = []
        mutations = (
            initial_data.get("frameworkUpdates", {})
            .get("entityBatchUpdate", {})
            .get("mutations", [])
        )
        for mutation in mutations:
            if (
                "payload" in mutation
                and "macroMarkersListEntity" in mutation["payload"]
            ):
                markers_list = mutation["payload"]["macroMarkersListEntity"].get(
                    "markersList", {}
                )
                decorations = markers_list.get("markersDecoration", {}).get(
                    "timedMarkerDecorations", []
                )
                if decorations:
                    break

        if not decorations:
            return JsonResponse(
                {
                    "segments": [],
                    "message": 'Nenhum segmento "mais repetido" foi encontrado para este vídeo.',
                }
            )

        segments = []
        processed_ranges = set()  # Conjunto para rastrear intervalos já adicionados

        for deco in decorations:
            if (
                deco.get("label", {}).get("runs", [{}])[0].get("text")
                == "Mais repetidos"
            ):
                start_ms = int(deco.get("visibleTimeRangeStartMillis", 0))
                end_ms = int(deco.get("visibleTimeRangeEndMillis", 0))

                time_range_key = (start_ms, end_ms)

                # Adiciona o segmento apenas se o intervalo de tempo for único
                if time_range_key not in processed_ranges:
                    segments.append(
                        {
                            "start": start_ms / 1000.0,
                            "end": end_ms / 1000.0,
                            "duration": (end_ms - start_ms) / 1000.0,
                        }
                    )
                    processed_ranges.add(time_range_key)

        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            duration = info.get('duration', 0)

        return JsonResponse({"segments": sorted(segments, key=lambda x: x["start"])
, "duration": duration})

    except requests.RequestException as e:
        return JsonResponse(
            {"error": f"Erro ao buscar a URL do YouTube: {e}"},
            status=500,
        )
    except Exception as e:
        print(f"Erro em get_youtube_most_replayed_segments: {e}")
        return JsonResponse(
            {"error": "Ocorreu um erro inesperado ao analisar o vídeo."},
            status=500,
        )


def processar_corte_youtube(
    corte_gerado_id, musica_base_id, volume_musica, gerar_legendas
):
    corte_gerado = get_object_or_404(CorteGerado, pk=corte_gerado_id)
    video = corte_gerado.video_gerado
    youtube_url = corte_gerado.youtube_url
    segment = {"start": corte_gerado.start_time, "end": corte_gerado.end_time}
    temp_dir = os.path.join(settings.MEDIA_ROOT, "youtube_cuts_temp")
    os.makedirs(temp_dir, exist_ok=True)

    # Inicializa os caminhos para garantir a limpeza no bloco 'finally'
    caminho_video_segmento = None
    caminho_audio_extraido = None
    caminho_legenda_srt = None
    caminho_video_local_final = None
    caminho_musica_input = None
    caminhos_para_limpar = []

    try:
        # --- ETAPA 1: Baixar o segmento com yt-dlp (esta parte já estava correta) ---
        video.status = "PROCESSANDO (1/4 - Baixando segmento)"
        video.save()

        segment_filename_template = os.path.join(
            temp_dir, f"segment_{video.usuario.id}_{random.randint(1000, 9999)}.%(ext)s"
        )

        ydl_opts = {
            "format": "best[ext=mp4][height<=1080]/best[ext=mp4]/best",
            "outtmpl": segment_filename_template,
            "quiet": True,
            "download_ranges": yt_dlp.utils.download_range_func(
                None, [(segment["start"], segment["end"])]
            ),
            "force_keyframes_at_cuts": False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            caminho_video_segmento = ydl.prepare_filename(info)

        if not caminho_video_segmento or not os.path.exists(caminho_video_segmento):
            raise Exception("yt-dlp não conseguiu baixar o arquivo do segmento.")

        caminhos_para_limpar.append(caminho_video_segmento)

        # --- ETAPA 2: Gerar legendas (se solicitado) ---
        if gerar_legendas:
            video.status = "PROCESSANDO (2/4 - Gerando legendas)"
            video.save()
            caminho_audio_extraido = extract_audio_from_video(caminho_video_segmento)
            caminhos_para_limpar.append(caminho_audio_extraido)
            caminho_legenda_srt = transcribe_audio_to_srt(caminho_audio_extraido)
            caminhos_para_limpar.append(caminho_legenda_srt)

        # --- ETAPA 3: Processar vídeo final (redimensionar, música, legendas) ---
        video.status = "PROCESSANDO (3/4 - Finalizando vídeo)"
        video.save()

        if musica_base_id:
            musica_base = get_object_or_404(MusicaBase, id=musica_base_id)
            caminho_musica_input = download_from_cloudflare(
                musica_base.object_key, ".mp3"
            )
            if not caminho_musica_input:
                raise Exception("Falha ao baixar a música de fundo.")
            caminhos_para_limpar.append(caminho_musica_input)

        nome_base = f"corte_{video.usuario.id}_{random.randint(10000, 99999)}"
        nome_arquivo_final = f"{nome_base}.mp4"
        caminho_video_local_final = os.path.join(
            settings.MEDIA_ROOT, "videos_gerados", nome_arquivo_final
        )
        caminhos_para_limpar.append(caminho_video_local_final)
        object_key_r2 = f"videos_gerados/{nome_arquivo_final}"
        os.makedirs(os.path.dirname(caminho_video_local_final), exist_ok=True)

        cmd = ["ffmpeg", "-y", "-i", caminho_video_segmento]
        if caminho_musica_input:
            cmd.extend(["-i", caminho_musica_input])

        # --- INÍCIO DA CORREÇÃO NO FFMPEG ---
        video_filters = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:-1:-1,setsar=1"
        if caminho_legenda_srt:
            escaped_srt_path = caminho_legenda_srt.replace("\\", "/").replace(
                ":", "\\:"
            )
            style_options = "FontName=impact,FontSize=9,PrimaryColour=&H00FFFFFF,Bold=-1,MarginV=60,BorderStyle=3,Outline=2,Shadow=1"
            video_filters += (
                f",subtitles='{escaped_srt_path}':force_style='{style_options}'"
            )

        # CORREÇÃO 1: O filtro de vídeo precisa do input [0:v]
        filter_complex_parts = [f"[0:v]{video_filters}[v]"]

        if caminho_musica_input:
            # CORREÇÃO 2: O volume precisa ser um valor decimal (ex: 0.7), não um inteiro (ex: 70)
            volume_musica_decimal = float(volume_musica) / 100.0

            # CORREÇÃO 3: A sintaxe do filtro de áudio estava incorreta
            audio_filters = (
                f"[0:a]loudnorm[audio_original_norm];"
                f"[1:a]loudnorm[audio_musica_norm];"
                f"[audio_musica_norm]volume={volume_musica_decimal}[audio_musica_final];"
                f"[audio_original_norm][audio_musica_final]amix=inputs=2:duration=longest:dropout_transition=2[audio_mix]"
            )
            filter_complex_parts.append(audio_filters)

            filter_complex_str = ";".join(filter_complex_parts)
            cmd.extend(
                [
                    "-filter_complex",
                    filter_complex_str,
                    "-map",
                    "[v]",
                    "-map",
                    "[audio_mix]",
                ]
            )
        else:  # Sem música, usa o filtro de vídeo simples
            cmd.extend(["-vf", video_filters, "-map", "0:v", "-map", "0:a?"])

        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "28",
                "-r",
                "30",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                caminho_video_local_final,
            ]
        )

        logger.info(f"Comando FFMPEG a ser executado: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        # --- FIM DA CORREÇÃO ---

        # --- ETAPA 4: Upload para o R2 ---
        video.status = "PROCESSANDO (4/4 - Enviando para nuvem)"
        video.save()

        if not upload_to_r2(caminho_video_local_final, object_key_r2):
            raise Exception("Falha no upload do corte para o Cloudflare R2.")

        # Gerar e salvar a thumbnail
        from .utils import generate_thumbnail_from_video_r2
        thumbnail_key = generate_thumbnail_from_video_r2(object_key_r2)

        video.status = "CONCLUIDO"
        video.arquivo_final = object_key_r2
        video.thumbnail_key = thumbnail_key
        video.mensagem_erro = None
        video.save()

    except Exception as e:
        # --- CORREÇÃO NO TRATAMENTO DE ERRO ---
        video.status = "ERRO"
        # Salva a mensagem de erro detalhada no banco de dados para facilitar a depuração
        video.mensagem_erro = str(e)
        video.save()

        logger.error(f"!!!!!!!!!! ERRO AO PROCESSAR CORTE (ID: {corte_gerado_id}) !!!!!!!!!!")
        if isinstance(e, subprocess.CalledProcessError):
            # Imprime os detalhes do erro do ffmpeg no console
            logger.error(f"--- ERRO FFMPEG (STDOUT) ---\n{e.stdout}")
            logger.error(f"--- ERRO FFMPEG (STDERR) ---\n{e.stderr}")
        else:
            logger.error(f"Exceção: {e}")

    finally:
        # A lógica de limpeza de arquivos já está correta, usando a lista
        for path in caminhos_para_limpar:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as err:
                    print(f"Erro ao remover arquivo temporário {path}: {err}")


@login_required
def pagina_gerador(request):
    from .forms import GeradorForm

    videos_criados, limite_videos, assinatura = _get_user_video_usage(request.user)

    if not assinatura or assinatura.status != "ativo":
        messages.warning(request, "Você precisa de um plano ativo para gerar vídeos.")
        return redirect("planos")

    if videos_criados >= limite_videos:
        messages.error(
            request,
f"Você atingiu seu limite de {limite_videos} vídeos por mês."
        )
        return redirect("meu_perfil")

    if request.method == "POST":
        form = GeradorForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data

            # --- VALIDAÇÃO DE LIMITE DE CARACTERES ---
            texto_overlay = data.get("texto_overlay", "")
            if texto_overlay and len(texto_overlay) > 250:
                messages.error(request, "O texto estático não pode ter mais de 250 caracteres.")
                context = {
                    "form": form,
                    "videos_restantes": limite_videos - videos_criados,
                    "limite_videos_mes": limite_videos,
                }
                return render(request, "core/gerador.html", context)

            narrador_texto = data.get("narrador_texto", "")
            if narrador_texto:
                velocidade_str = data.get("narrador_velocidade", "100")
                try:
                    velocidade = int(velocidade_str)
                except (ValueError, TypeError):
                    velocidade = 100

                if velocidade <= 85:
                    limite_chars = 2000
                    nome_velocidade = "lenta"
                elif velocidade <= 100:
                    limite_chars = 2600
                    nome_velocidade = "normal"
                else:
                    limite_chars = 3200
                    nome_velocidade = "rápida"

                if len(narrador_texto) > limite_chars:
                    messages.error(
                        request,
                        f"O texto da narração excedeu o limite de {limite_chars} caracteres para a velocidade {nome_velocidade}. Por favor, reduza o texto.",
                    )
                    context = {
                        "form": form,
                        "videos_restantes": limite_videos - videos_criados,
                        "limite_videos_mes": limite_videos,
                    }
                    return render(request, "core/gerador.html", context)
            
            # --- UPLOAD DE VÍDEO (permanece igual) ---
            video_upload = data.get("video_upload")
            if video_upload:
                try:
                    temp_object_key = (
                        f"uploaded_videos_temp/{request.user.id}_{uuid.uuid4().hex}.mp4"
                    )
                    upload_fileobj_to_r2(video_upload, temp_object_key)
                    data["video_upload_key"] = temp_object_key
                except Exception as e:
                    messages.error(request, f"Falha ao fazer upload do vídeo: {e}")
                    return redirect("pagina_gerador")

            if "video_upload" in data:
                del data["video_upload"]

            video_gerado = VideoGerado.objects.create(
                usuario=request.user,
                status="PROCESSANDO",
                duracao_segundos=data.get("duracao_segundos") or 30,
                loop=data.get("loop_video", False),
                plano_de_fundo=data.get("plano_de_fundo", "normal"),
                volume_musica=data.get("volume_musica", 70),
                texto_overlay=data.get("texto_overlay", ""),
                narrador_texto=data.get("narrador_texto", ""),
                texto_tela_final=data.get("texto_tela_final", ""),
                posicao_texto=data.get("posicao_texto", "centro"),
                cor_da_fonte=data.get("cor_da_fonte", "#FFFFFF"),
                texto_fonte=data.get("texto_fonte", "arial"),
                texto_tamanho=data.get("texto_tamanho", 20),
                texto_negrito=data.get("texto_negrito", False),
                texto_sublinhado=data.get("texto_sublinhado", False),
                legenda_sincronizada=data.get("legenda_sincronizada", False),
                narrador_voz=data.get("narrador_voz", "pt-BR-Wavenet-B"),
                narrador_velocidade=data.get("narrador_velocidade", 100),
                narrador_tom=data.get("narrador_tom", 0.0),
            )

            try:
                # Convert model objects to IDs for Celery serialization
                if data.get("categoria_video"):
                    data["categoria_video"] = data["categoria_video"].id
                if data.get("categoria_musica"):
                    data["categoria_musica"] = data["categoria_musica"].id
                
                # ==========================================================
                # ALTERAÇÃO PRINCIPAL AQUI
                # Trocamos o `enqueue_video_task` pela chamada da tarefa Celery
                # ==========================================================
                task_processar_geracao_video.delay(
                    video_gerado.id,
                    data,
                    request.user.id,
                    assinatura.id if assinatura else None,
                )
                
                messages.success(
                    request,
                    "Seu vídeo começou a ser processado! Ele aparecerá em 'Meus Vídeos' em breve.",
                )
                return redirect("meus_videos")
                
            except Exception as e:
                video_gerado.status = "ERRO"
                video_gerado.mensagem_erro = "Falha ao enfileirar a tarefa."
                video_gerado.save()
                print(f"ERROR: Falha ao enfileirar a tarefa de geração de vídeo. {e}")
                messages.error(
                    request,
                    "Ocorreu um erro ao enviar seu vídeo para processamento. Por favor, tente novamente.",
                )
                return redirect("pagina_gerador")
        else:
            messages.error(
                request,
                "Houve um erro no formulário. Por favor, verifique os dados inseridos.",
            )
    else:  # GET request
        form = GeradorForm()

    context = {
        "form": form,
        "videos_restantes": limite_videos - videos_criados,
        "limite_videos_mes": limite_videos,
    }
    return render(request, "core/gerador.html", context)


@login_required
def cortes_youtube_view(request):
    from .forms import CortesYouTubeForm

    if not request.user.plano_ativo:
        messages.warning(
            request,
            "Esta funcionalidade está disponível apenas para assinantes.",
        )
        return redirect("planos")

    videos_criados, limite_videos_mes, _ = _get_user_video_usage(request.user)

    if limite_videos_mes is not None and videos_criados >= limite_videos_mes:
        messages.error(
            request,
f"Você atingiu seu limite de {limite_videos_mes} vídeos por mês."
        )
        return redirect("meu_perfil")

    if request.method == "POST":
        form = CortesYouTubeForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            youtube_url = data["youtube_url"]
            selected_segments = json.loads(data["segments"])

            # --- VALIDAÇÃO DE DURAÇÃO (permanece igual) ---
            for segment in selected_segments:
                if segment.get("duration", 0) > 180:
                    messages.error(
                        request,
                        f"O corte que começa em {segment['start']:.0f}s tem duração maior que 3 minutos e não pode ser processado.",
                    )
                    form = CortesYouTubeForm(initial=data)
                    return render(
                        request,
                        "core/cortes_youtube.html",
                        {
                            "form": form,
                            "videos_restantes": (
                                (limite_videos_mes - videos_criados)
                                if videos_criados is not None
                                and limite_videos_mes is not None
                                else "Ilimitado"
                            ),
                        },
                    )
            
            # --- VALIDAÇÃO DE LIMITE DE VÍDEOS (permanece igual) ---
            if (
                limite_videos_mes is not None
                and (videos_criados + len(selected_segments)) > limite_videos_mes
            ):
                messages.error(
                    request,
                    f"A criação de {len(selected_segments)} cortes excederia seu limite mensal de {limite_videos_mes} vídeos.",
                )
                return render(
                    request,
                    "core/cortes_youtube.html",
                    {
                        "form": form,
                        "videos_restantes": limite_videos_mes - videos_criados,
                    },
                )

            musica_base = get_valid_media_from_category(
                MusicaBase, data["categoria_musica"]
            )
            if not musica_base:
                messages.error(
                    request,
                    f"Não foi possível encontrar uma música válida para a categoria '{data['categoria_musica']}'.",
                )
                return render(
                    request,
                    "core/cortes_youtube.html",
                    {
                        "form": form,
                        "videos_restantes": limite_videos_mes - videos_criados,
                    },
                )

            try:
                for segment in selected_segments:
                    video_gerado = VideoGerado.objects.create(
                        usuario=request.user,
                        status="PROCESSANDO",
                        narrador_texto=f"Corte do vídeo: {youtube_url}",
                        texto_overlay=f"Início: {segment['start']}s",
                    )
                    corte_gerado = CorteGerado.objects.create(
                        video_gerado=video_gerado,
                        youtube_url=youtube_url,
                        start_time=segment['start'],
                        end_time=segment['end'],
                    )
                    
                    logger.info(f"Enfileirando task de corte para o ID de corte: {corte_gerado.pk}")
                    task_processar_corte_youtube.delay(
                        corte_gerado.pk,
                        musica_base.id,
                        data["volume_musica"],
                        data["gerar_legendas"],
                    )

                messages.success(
                    request,
                    f"{len(selected_segments)} cortes foram enviados para processamento. Eles aparecerão em 'Meus Vídeos' em breve.",
                )
                return redirect("meus_videos")

            except Exception as e:
                logger.error(f"FALHA CRÍTICA AO ENFILEIRAR TAREFA DE CORTE: {e}", exc_info=True)
                messages.error(
                    request,
                    f"Ocorreu um erro CRÍTICO ao iniciar o processamento. A tarefa não foi enviada. Por favor, verifique a conexão com o sistema de tarefas e tente novamente. Erro: {e}",
                )

    else:  # GET request
        form = CortesYouTubeForm()

    context = {
        "form": form,
        "videos_restantes": (
            (limite_videos_mes - videos_criados)
            if videos_criados is not None and limite_videos_mes is not None
            else "Ilimitado"
        ),
    }
    return render(request, "core/cortes_youtube.html", context)