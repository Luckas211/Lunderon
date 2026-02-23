# core/services.py

import os
import re
import urllib.parse
import time
import requests
import shutil

import logging
import tempfile
import subprocess
import random
import yt_dlp
import numpy as np
import torch
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont
from kokoro import KPipeline
from django.conf import settings
from django.shortcuts import get_object_or_404

from .models import (
    VideoGerado,
    Usuario,
    Assinatura,
    VideoBase,
    CategoriaVideo,
    CategoriaMusica,
    MusicaBase,
    CorteGerado,
)
from .utils import (
    verificar_arquivo_existe_no_r2,
    download_from_cloudflare,
    upload_to_r2,
    generate_thumbnail_from_video_r2,
    get_valid_media_from_category,
)
from .transcription_utils import get_word_timestamps, extract_audio_from_video, transcribe_audio_to_srt

logger = logging.getLogger(__name__)

class YTDLPLogger:
    def __init__(self, prefix):
        self.prefix = prefix

    def debug(self, msg):
        logger.info(f"[yt-dlp:{self.prefix}] {msg}")

    def warning(self, msg):
        logger.warning(f"[yt-dlp:{self.prefix}] {msg}")

    def error(self, msg):
        logger.error(f"[yt-dlp:{self.prefix}] {msg}")

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================

FONT_PATHS = {
    "Windows": {
        "cunia": os.path.join(settings.BASE_DIR, "core", "static", "fonts", "Cunia.ttf"),
        "arial": os.path.join(settings.BASE_DIR, "core", "static", "fonts", "arial.ttf"),
    },
    "Linux": {
        "cunia": os.path.join(settings.BASE_DIR, "core", "static", "fonts", "Cunia.ttf"),
        "arial": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    },
}

# ==============================================================================
# FUNÇÕES DE ÁUDIO E IA (KOKORO ATUALIZADO)
# ==============================================================================

def carregar_embedding_voz(pipeline, nome_voz):
    """
    Carrega o vetor da voz. Prioriza arquivos .npy personalizados.
    Retorna o Tensor ou Numpy Array dos dados da voz.
    """
    # 1. Tenta carregar arquivo personalizado (.npy)
    path_custom = os.path.join(settings.BASE_DIR, 'core', 'voices_custom', f"{nome_voz}.npy")
    
    if os.path.exists(path_custom):
        try:
            logger.info(f"🎤 Carregando voz personalizada do disco: {nome_voz}")
            return np.load(path_custom)
        except Exception as e:
            logger.error(f"Erro ao ler arquivo .npy {nome_voz}: {e}")

    # 2. Tenta carregar voz padrão do sistema Kokoro
    try:
        logger.info(f"🎤 Tentando carregar voz padrão: {nome_voz}")
        # O load_voice do Kokoro retorna um Tensor se achar, ou baixa do HF
        voice = pipeline.load_voice(nome_voz)
        return voice
    except Exception as e:
        # 3. Fallback final
        logger.warning(f"⚠️ Voz {nome_voz} não encontrada nem em disco nem no sistema. Usando 'pf_dora'. Erro: {e}")
        return pipeline.load_voice('pf_dora')


def gerar_audio_e_tempos(texto, voz, velocidade, obter_tempos=False):
    """
    Gera áudio a partir do texto usando o modelo Kokoro.
    CORREÇÃO APLICADA: Injeta o embedding no pipeline e passa o NOME (string).
    """
    caminho_audio_final = None
    
    try:
        # 1. Inicializa Pipeline (Português)
        pipeline = KPipeline(lang_code="p", repo_id='hexgrad/Kokoro-82M')
        
        # 2. Carrega os dados brutos da voz (Array ou Tensor)
        dados_da_voz = carregar_embedding_voz(pipeline, voz)
        
        # O Kokoro espera que passemos uma STRING como 'voice', não o array.
        # Mas para vozes customizadas ('br_imperador'), o pipeline não conhece esse nome.
        # Então injetamos manualmente os dados no dicionário interno do pipeline.
        
        # Garante que é um Tensor do PyTorch (Kokoro usa Torch internamente)
        if isinstance(dados_da_voz, np.ndarray):
            dados_da_voz = torch.from_numpy(dados_da_voz).float()
            
        # Injeta no dicionário de vozes do pipeline
        pipeline.voices[voz] = dados_da_voz
        
        # 3. Configura velocidade
        try:
            speed_factor = float(velocidade) / 100.0
        except:
            speed_factor = 1.0

        # 4. Gera o áudio passando o NOME DA VOZ (String), pois agora ela existe no pipeline
        generator = pipeline(
            texto, 
            voice=voz,  # <--- Passamos a STRING 'br_imperador', não o array
            speed=speed_factor, 
            split_pattern=r"\n+"
        )

        audio_segments = []
        for i, (gs, ps, audio) in enumerate(generator):
            audio_segments.append(audio)
        
        if not audio_segments:
            raise Exception("Nenhum áudio foi gerado pelo pipeline.")

        full_audio = np.concatenate(audio_segments)

        # 5. Salva o arquivo final
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_f:
            caminho_audio_final = temp_f.name
        
        sf.write(caminho_audio_final, full_audio, 24000)

        # Calcula duração
        info = sf.info(caminho_audio_final)
        duracao = info.duration
        
        timepoints = None

        return caminho_audio_final, timepoints, duracao

    except Exception as e:
        logger.error(f"Erro CRÍTICO ao gerar áudio (Kokoro) para voz {voz}: {e}", exc_info=True)
        if caminho_audio_final and os.path.exists(caminho_audio_final):
            try:
                os.remove(caminho_audio_final)
            except:
                pass
        return None, None, 0

# ==============================================================================
# FUNÇÕES DE TEXTO E IMAGEM
# ==============================================================================
# 
def obter_video_pexels(texto, duracao_total, temp_dir):
    """Busca múltiplos vídeos reais no Pexels para criar um fundo dinâmico que acompanha a história."""
    logger.info("Iniciando busca de múltiplos vídeos reais (Pexels)...")
    api_key = os.getenv("PEXELS_API_KEY")
    
    if not api_key:
        logger.error("ERRO: PEXELS_API_KEY não encontrada no .env")
        return None

    # 1. Define quantos vídeos vamos baixar (Ex: 1 clipe a cada 5 segundos, máximo de 6 para não estourar a API)
    num_clipes = max(3, min(int(duracao_total / 5), 6))
    tempo_por_clipe = duracao_total / num_clipes

    # 2. Pede para a IA criar as palavras-chave em inglês baseadas na progressão da história
    prompt_ia = (
        f"Based on this story, create exactly {num_clipes} short English search terms (1-2 words max) "
        "for a stock video site. Represent the chronological flow of the story. "
        "Return ONLY the terms separated by '|'. Example: dark forest|jumping fish|calm lake. "
        f"Story: {texto[:1500]}"
    )
    
    termos_busca = []
    try:
        url_termo = f"https://gen.pollinations.ai/text/{urllib.parse.quote(prompt_ia)}"
        resp_text = requests.get(url_termo, timeout=15).text.strip()
        # Limpa e separa os termos gerados
        termos_brutos = resp_text.split('|')
        for t in termos_brutos:
            t_limpo = re.sub(r'[^a-zA-Z\s]', '', t).strip()
            if t_limpo:
                termos_busca.append(t_limpo)
    except Exception as e:
        logger.warning(f"Falha ao gerar termos múltiplos: {e}")

    # Fallback: Se a IA falhar ou retornar menos termos, preenchemos com temas genéricos cinematográficos
    termos_fallback = ["cinematic nature", "urban city", "people walking", "abstract light", "beautiful landscape", "ocean waves"]
    if len(termos_busca) < num_clipes:
        termos_busca.extend(termos_fallback[:num_clipes - len(termos_busca)])
    
    termos_busca = termos_busca[:num_clipes]
    logger.info(f"Termos de busca gerados para o Pexels ({len(termos_busca)} cenas): {termos_busca}")

    headers = {"Authorization": api_key}
    video_clips = []

    # 3. Baixa e corta cada vídeo para formar a sequência
    for i, termo in enumerate(termos_busca):
        url_api = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(termo)}&orientation=portrait&size=large&per_page=5"
        clip_path = os.path.join(temp_dir, f"pexels_clip_{i:03d}.mp4")
        
        try:
            resp = requests.get(url_api, headers=headers, timeout=20)
            if resp.status_code == 200:
                dados = resp.json()
                
                # Se o Pexels não achar nada com o termo da IA, tenta um termo genérico para não deixar buracos
                if not dados.get('videos'):
                    termo_salva_vidas = random.choice(["cinematic video", "beautiful scenery", "dark background"])
                    resp = requests.get(f"https://api.pexels.com/videos/search?query={urllib.parse.quote(termo_salva_vidas)}&orientation=portrait", headers=headers, timeout=20)
                    dados = resp.json()

                if dados.get('videos'):
                    # Pega um vídeo aleatório entre os primeiros resultados
                    video_escolhido = random.choice(dados['videos'])
                    
                    # Busca a qualidade HD
                    hd_files = [f for f in video_escolhido['video_files'] if f['quality'] == 'hd' and f['width'] >= 720]
                    video_url = hd_files[0]['link'] if hd_files else video_escolhido['video_files'][0]['link']
                    
                    # Baixa o vídeo cru
                    logger.info(f"Baixando cena {i+1}/{num_clipes} (Termo: {termo})...")
                    raw_vid = os.path.join(temp_dir, f"pexels_raw_{i:03d}.mp4")
                    with open(raw_vid, 'wb') as f:
                        f.write(requests.get(video_url, timeout=30).content)
                    
                    # Formata o vídeo (loop se for muito curto, corta no tempo exato, ajusta tamanho)
                    raw_vid_clean = raw_vid.replace('\\', '/')
                    clip_path_clean = clip_path.replace('\\', '/')
                    
                    cmd = [
                        "ffmpeg", "-y", "-stream_loop", "-1", "-i", raw_vid_clean,
                        "-t", f"{tempo_por_clipe:.2f}", 
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p",
                        "-c:v", "libx264", "-preset", "ultrafast", "-r", "30", clip_path_clean
                    ]
                    subprocess.run(cmd, check=True, capture_output=True)
                    video_clips.append(clip_path)
        except Exception as e:
            logger.error(f"Erro na cena {i} (Pexels): {e}")

    # 4. Junta todas as cenas em um único vídeo final
    if not video_clips:
        logger.error("Falha total: Nenhum vídeo pôde ser processado do Pexels.")
        return None

    logger.info("Unindo cenas do Pexels...")
    concat_file = os.path.join(temp_dir, "lista_pexels.txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for clip in video_clips:
            caminho_limpo = clip.replace('\\', '/')
            f.write(f"file '{caminho_limpo}'\n")

    video_final_path = os.path.join(temp_dir, "fundo_pexels_sequencia.mp4")
    
    # Comando de concatenação ultra-rápido do FFmpeg
    cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", video_final_path]
    subprocess.run(cmd_concat, check=True)
    
    logger.info("✓ Sequência dinâmica de vídeos Pexels gerada com sucesso!")
    return video_final_path

def gerar_fundo_hibrido(texto, duracao_total, temp_dir, modo='imagem'):
    """
    Função Maestro: Decide se vai chamar a API do Pexels (Vídeo Real) 
    ou a API do Pollinations (Imagens IA c/ Ken Burns).
    """
    if modo == 'video':
        caminho_pexels = obter_video_pexels(texto, duracao_total, temp_dir)
        if caminho_pexels:
            return caminho_pexels
        logger.warning("Pexels falhou ou não encontrou vídeo. Usando Pollinations Imagem como fallback.")
    
    # Se escolheu 'imagem' ou se o Pexels deu erro, cai na função de imagens que já criamos
    return gerar_fundo_com_ia_pollinations(texto, duracao_total, temp_dir)





def gerar_fundo_com_ia_pollinations(texto, duracao_total, temp_dir):
    """
    Versão Ultra Storytelling Cinematográfico: Gera até 10 cenas coordenadas por IA
    com qualidade hiper-realista e efeito Ken Burns.
    """
    logger.info("Iniciando inteligência visual para 10 cenas cinematográficas...")
    api_key = os.getenv("POLLINATIONS_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    # --- PASSO 1: IA CRIA UM ROTEIRO DE 10 CENAS VISUAIS ---
    # Aprimoramos o prompt para forçar descrições mais focadas em ambiente e atmosfera
    prompt_roteirista = (
        "Based on this story, create exactly 10 highly visual scene descriptions in ENGLISH. "
        "Focus on environments, characters, and atmosphere. "
        "Return ONLY the descriptions separated by '|'. "
        f"Story: {texto[:1500]}"
    )
    
    frases_visuais = []
    try:
        url_text = f"https://gen.pollinations.ai/text/{urllib.parse.quote(prompt_roteirista)}"
        resp_text = requests.get(url_text, headers=headers, timeout=40)
        if resp_text.status_code == 200:
            frases_visuais = [f.strip() for f in resp_text.text.split('|') if len(f) > 5]
            frases_visuais = frases_visuais[:10]
            logger.info(f"Roteiro de {len(frases_visuais)} cenas identificadas com sucesso.")
    except Exception as e:
        logger.error(f"Falha ao gerar roteiro visual: {e}")

    if not frases_visuais:
        frases_visuais = ["mystical dark forest", "ancient ruined castle", "glowing magic lake"]

    tempo_por_imagem = duracao_total / len(frases_visuais)
    video_clips = []

    # --- PASSO 2: RENDERIZAÇÃO HIPER-REALISTA COM FLUX ---
    for i, prompt_en in enumerate(frases_visuais):
        img_path = os.path.join(temp_dir, f"ia_raw_{i:03d}.jpg")
        clip_path = os.path.join(temp_dir, f"ia_move_{i:03d}.mp4")
        
        # 🌟 O GRANDE SEGREDO: Injetamos modificadores de alta qualidade em cada cena!
        prompt_premium = f"{prompt_en}, cinematic masterpiece, photorealistic, 8k resolution, highly detailed, dramatic lighting, epic movie scene, unreal engine 5 render, depth of field"
        
        # Continuamos usando o Flux gratuito do Pollinations
        url_img = f"https://gen.pollinations.ai/image/{urllib.parse.quote(prompt_premium)}?model=flux&width=1080&height=1920&nologo=true&seed={random.randint(1,99999)}"
        if api_key: url_img += f"&key={api_key}"

        try:
            logger.info(f"Renderizando cena {i+1}/{len(frases_visuais)} (Ultra Qualidade)...")
            resp = requests.get(url_img, timeout=45)
            if resp.status_code == 200:
                with open(img_path, 'wb') as f:
                    f.write(resp.content)
                
                total_frames = int(tempo_por_imagem * 30)
                
                # Ken Burns suave para manter a qualidade 8k sem pixelar
                kb_filter = (
                    f"scale=2160:3840,zoompan=z='min(zoom+0.001,1.15)':"
                    f"d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,format=yuv420p"
                )
                
                cmd_clip = [
                    "ffmpeg", "-y", "-loop", "1", "-i", img_path,
                    "-t", f"{tempo_por_imagem:.2f}",
                    "-vf", kb_filter,
                    "-c:v", "libx264", "-preset", "ultrafast", "-r", "30", clip_path
                ]
                subprocess.run(cmd_clip, check=True, capture_output=True)
                video_clips.append(clip_path)
        except Exception as e:
            logger.error(f"Erro na cena {i}: {e}")

    # --- PASSO 3: CONCATENAÇÃO FINAL ---
    if not video_clips:
        raise Exception("Nenhuma imagem pôde ser processada.")

    concat_file = os.path.join(temp_dir, "lista_videos.txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for clip in video_clips:
            caminho_limpo = clip.replace('\\', '/')
            f.write(f"file '{caminho_limpo}'\n")

    video_final = os.path.join(temp_dir, "fundo_ia_10_cenas.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", video_final], check=True)
    
    return video_final

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
    import platform
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


def formatar_tempo_ass(segundos):
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    cs = int((segundos - int(segundos)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def gerar_legenda_karaoke_ass(
    word_timestamps, data, cor_da_fonte_hex, cor_destaque_hex, posicao="centro"
):
    """
    Gera uma legenda .ASS com sincronização precisa por palavra.
    """
    # Configurações de estilo
    nome_fonte = data.get("texto_fonte", "Arial")
    tamanho = data.get("texto_tamanho", 70)
    negrito = -1 if data.get("texto_negrito", False) else 0
    sublinhado = -1 if data.get("texto_sublinhado", False) else 0

    # Converte a cor principal
    try:
        hex_limpo = cor_da_fonte_hex.lstrip("#")
        r, g, b = tuple(int(hex_limpo[i : i + 2], 16) for i in (0, 2, 4))
        cor_primaria_ass = f"&H00{b:02X}{g:02X}{r:02X}"
    except (ValueError, IndexError):
        cor_primaria_ass = "&H00FFFFFF"  # Branco opaco

    # Converte a cor de destaque
    try:
        hex_limpo_destaque = cor_destaque_hex.lstrip("#")
        r_s, g_s, b_s = tuple(int(hex_limpo_destaque[i : i + 2], 16) for i in (0, 2, 4))
        cor_secundaria_ass = f"&H00{b_s:02X}{g_s:02X}{r_s:02X}"
    except (ValueError, IndexError, TypeError):
        cor_secundaria_ass = "&H0000FFFF"  # Amarelo opaco

    cor_outline = "&H00000000"
    cor_back = "&H80000000"

    alignment_code = 5 if posicao == "centro" else 2
    margin_v = 150 if posicao == "inferior" else 50

    header = (
        f"[Script Info]\nTitle: Legenda Sincronizada\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
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
            # Formata a tag de karaoke para o padrão ASS {\k<duração>}
            texto_karaoke += f"{{\\k{duracao_cs}}}{palavra['word'].strip()} "

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


def estimar_tempo_narracao(texto, velocidade=100):
    """
    Estima o tempo de narração com base no texto e velocidade
    Baseado em: 150 palavras por minuto para velocidade normal (100%)
    """
    palavras = texto.split()
    num_palavras = len(palavras)
    ppm_base = 150

    try:
        velocidade_float = float(velocidade)
    except (ValueError, TypeError):
        velocidade_float = 100.0

    ppm_ajustado = ppm_base * (velocidade_float / 100.0)
    duracao_minutos = num_palavras / ppm_ajustado
    duracao_segundos = duracao_minutos * 60

    return duracao_segundos, num_palavras


# ==============================================================================
# PROCESSAMENTO DE VÍDEOS
# ==============================================================================

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
            texto_narrador_limpo = re.sub(r'{{{\d+}}}', '', data["narrador_texto"])
            
            # Geração de áudio
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
            # Verifica se o usuário escolheu gerar fundo com IA
            gerar_fundo_ia = str(data.get("gerar_fundo_ia", "")).lower() in ["true", "1", "yes"]
            
            if tipo_conteudo == "narrador" and gerar_fundo_ia:
                # 1. Pega qual foi o motor visual escolhido no formulário (imagem ou video)
                modo_visual = data.get("tipo_visual_ia", "imagem")
                
                logger.info(f"[{video_gerado_id}] Gerando vídeo de fundo dinâmico com IA (Motor: {modo_visual})...")
                video.status = f"PROCESSANDO (Gerando fundo - {modo_visual})"
                video.save()
                
                texto_base = data.get("narrador_texto", "Cinematic aesthetic video background")
                temp_dir_ia = tempfile.mkdtemp(prefix="ia_fundo_")
                caminhos_para_limpar.append(temp_dir_ia) # Adicionado para limpeza futura
                
                # 2. CHAMA A FUNÇÃO HÍBRIDA (Maestro) em vez de forçar o Pollinations
                caminho_video_input = gerar_fundo_hibrido(texto_base, duracao_video, temp_dir_ia, modo=modo_visual)
            else:
                # Lógica existente: Baixa do Cloudflare R2
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
            # Se for do Pollinations, já está na pasta temp que será limpa, mas não faz mal adicionar
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
                    if os.path.isdir(caminho):
                        shutil.rmtree(caminho)  # Remove a pasta temporária criada pela IA
                        logger.info(f"[{video_gerado_id}] Pasta temporária removida: {caminho}")
                    else:
                        os.remove(caminho)
                        logger.info(f"[{video_gerado_id}] Arquivo temporário removido: {caminho}")
                except OSError as err:
                    logger.error(f"[{video_gerado_id}] Erro ao remover arquivo/pasta temporária {caminho}: {err}")
        logger.info(f"[{video_gerado_id}] Limpeza de arquivos temporários finalizada.")


def processar_corte_youtube(
    corte_gerado_id, musica_base_id, volume_musica, gerar_legendas
):
    corte_gerado = get_object_or_404(CorteGerado, pk=corte_gerado_id)
    video = corte_gerado.video_gerado
    youtube_url = corte_gerado.youtube_url
    segment = {"start": corte_gerado.start_time, "end": corte_gerado.end_time}
    temp_dir = os.path.join(settings.MEDIA_ROOT, "youtube_cuts_temp")
    os.makedirs(temp_dir, exist_ok=True)

    caminho_video_segmento = None
    caminho_audio_extraido = None
    caminho_legenda_srt = None
    caminho_video_local_final = None
    caminho_musica_input = None
    caminhos_para_limpar = []

    try:
        # --- ETAPA 1: Baixar o segmento com yt-dlp ---
        video.status = "PROCESSANDO (1/4 - Baixando segmento)"
        video.save()

        full_filename_template = os.path.join(
            temp_dir, f"full_{video.usuario.id}_{random.randint(1000, 9999)}.%(ext)s"
        )

        ydl_opts = {
            "format": "best[ext=mp4][protocol^=https][height<=1080][acodec!=none][vcodec!=none]/best[protocol^=https][height<=1080][acodec!=none][vcodec!=none]",
            "outtmpl": full_filename_template,
            "quiet": True,
            "noplaylist": True,
            "retries": 3,
            "fragment_retries": 3,
            "extractor_args": {"youtube": {"player_client": ["ios", "android"]}},
            # HABILITADO O USO DE COOKIES:
            "cookiefile": os.path.join(settings.BASE_DIR, "cookies.txt"),
            "logger": YTDLPLogger(corte_gerado_id),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            caminho_video_full = ydl.prepare_filename(info)

        if not caminho_video_full or not os.path.exists(caminho_video_full):
            raise Exception("yt-dlp nao conseguiu baixar o arquivo completo.")

        caminhos_para_limpar.append(caminho_video_full)

        segment_ext = os.path.splitext(caminho_video_full)[1] or ".mp4"
        caminho_video_segmento = os.path.join(
            temp_dir,
            f"segment_{video.usuario.id}_{random.randint(1000, 9999)}{segment_ext}",
        )

        cmd_cut_copy = [
            "ffmpeg",
            "-y",
            "-ss",
            str(segment["start"]),
            "-to",
            str(segment["end"]),
            "-i",
            caminho_video_full,
            "-c",
            "copy",
            caminho_video_segmento,
        ]
        logger.info(f"Comando FFMPEG de corte (copy) a ser executado: {' '.join(cmd_cut_copy)}")
        try:
            result = subprocess.run(
                cmd_cut_copy,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
                stdin=subprocess.DEVNULL,
            )
            if result.stdout:
                logger.info(f"FFMPEG corte (copy) stdout: {result.stdout}")
            if result.stderr:
                logger.warning(f"FFMPEG corte (copy) stderr: {result.stderr}")
        except subprocess.CalledProcessError as e:
            logger.warning(
                "FFMPEG corte (copy) falhou (returncode=%s). stdout: %s stderr: %s",
                e.returncode,
                e.stdout,
                e.stderr,
            )
            cmd_cut_encode = [
                "ffmpeg",
                "-y",
                "-ss",
                str(segment["start"]),
                "-to",
                str(segment["end"]),
                "-i",
                caminho_video_full,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                caminho_video_segmento,
            ]
            logger.info(
                f"Comando FFMPEG de corte (reencode) a ser executado: {' '.join(cmd_cut_encode)}"
            )
            result = subprocess.run(
                cmd_cut_encode,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
                stdin=subprocess.DEVNULL,
            )
            if result.stdout:
                logger.info(f"FFMPEG corte (reencode) stdout: {result.stdout}")
            if result.stderr:
                logger.warning(f"FFMPEG corte (reencode) stderr: {result.stderr}")

        if not caminho_video_segmento or not os.path.exists(caminho_video_segmento):
            raise Exception("ffmpeg nao conseguiu gerar o segmento do video.")

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

        video_filters = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:-1:-1,setsar=1"
        if caminho_legenda_srt:
            escaped_srt_path = caminho_legenda_srt.replace("\\", "/").replace(
                ":", "\\:"
            )
            style_options = "FontName=impact,FontSize=9,PrimaryColour=&H00FFFFFF,Bold=-1,MarginV=60,BorderStyle=3,Outline=2,Shadow=1"
            video_filters += (
                f",subtitles='{escaped_srt_path}':force_style='{style_options}'"
            )

        filter_complex_parts = [f"[0:v]{video_filters}[v]"]

        if caminho_musica_input:
            volume_musica_decimal = float(volume_musica) / 100.0
            audio_filters = (
                f"[0:a]loudnorm[audio_original_norm]" 
                f";[1:a]loudnorm[audio_musica_norm]" 
                f";[audio_musica_norm]volume={volume_musica_decimal}[audio_musica_final]" 
                f";[audio_original_norm][audio_musica_final]amix=inputs=2:duration=longest:dropout_transition=2[audio_mix]" 
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
        else:  # Sem música
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
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
                stdin=subprocess.DEVNULL,
            )
            if result.stdout:
                logger.info(f"FFMPEG stdout: {result.stdout}")
            if result.stderr:
                logger.warning(f"FFMPEG stderr: {result.stderr}")
        except subprocess.CalledProcessError as e:
            logger.error(
                f"FFMPEG falhou (returncode={e.returncode}). stdout: {e.stdout} stderr: {e.stderr}"
            )
            raise

        # --- ETAPA 4: Upload para o R2 ---
        video.status = "PROCESSANDO (4/4 - Enviando para nuvem)"
        video.save()

        if not upload_to_r2(caminho_video_local_final, object_key_r2):
            raise Exception("Falha no upload do corte para o Cloudflare R2.")

        # Gerar e salvar a thumbnail
        thumbnail_key = generate_thumbnail_from_video_r2(object_key_r2)

        video.status = "CONCLUIDO"
        video.arquivo_final = object_key_r2
        video.thumbnail_key = thumbnail_key
        video.mensagem_erro = None
        video.save()

    except Exception as e:
        video.status = "ERRO"
        video.mensagem_erro = str(e)
        video.save()

        logger.error(f"!!!!!!!!!! ERRO AO PROCESSAR CORTE (ID: {corte_gerado_id}) !!!!!!!!!!")
        if isinstance(e, subprocess.CalledProcessError):
            logger.error(f"--- ERRO FFMPEG (STDOUT) ---\n{e.stdout}")
            logger.error(f"--- ERRO FFMPEG (STDERR) ---\n{e.stderr}")
        else:
            logger.error(f"Exceção: {e}")

    finally:
        for path in caminhos_para_limpar:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as err:
                    print(f"Erro ao remover arquivo temporário {path}: {err}")