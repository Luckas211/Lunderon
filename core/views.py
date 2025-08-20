import subprocess
import random
import os
import platform
import textwrap
import re

from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.conf import settings

from google.cloud import texttospeech_v1beta1 as texttospeech
from PIL import Image, ImageDraw, ImageFont

from .forms import GeradorFormSet
from .models import VideoBase, MusicaBase, VideoGerado, CategoriaVideo, CategoriaMusica

# Se estiver usando `gcloud auth application-default login`, esta linha deve ficar comentada.
# os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(settings.BASE_DIR, 'gcloud-auth.json')

# --- CONSTANTES ---
# --- CONSTANTES ---
FONT_PATHS = {
    'Windows': {
        'arial': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'arial.ttf'),
        'arialbd': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'arialbd.ttf'),
        'times': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'times.ttf'),
        'courier': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'cour.ttf'),
        'impact': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'impact.ttf'),
        'verdana': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'verdana.ttf'),
        'georgia': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'georgia.ttf'),
        'alfa_slab_one': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'AlfaSlabOne-Regular.ttf'),
    },
    'Linux': {
        # Como agora todas as fontes estão no projeto, podemos simplesmente copiar a mesma lógica.
        'arial': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'arial.ttf'),
        'arialbd': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'arialbd.ttf'),
        'times': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'times.ttf'),
        'courier': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'cour.ttf'),
        'impact': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'impact.ttf'),
        'verdana': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'verdana.ttf'),
        'georgia': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'georgia.ttf'),
        'alfa_slab_one': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'AlfaSlabOne-Regular.ttf'),
    },
}

# ==============================================================================
# FUNÇÕES HELPER (COM LÓGICA DE COR E POSIÇÃO ATUALIZADAS)
# ==============================================================================

def create_text_image(texto, cor_da_fonte_hex, data, posicao='centro'):
    target_size = (1080, 1920)
    w, h = target_size
    sistema_op = platform.system()
    nome_fonte = data.get('texto_fonte', 'cunia')
    caminho_da_fonte = FONT_PATHS.get(sistema_op, {}).get(nome_fonte, FONT_PATHS.get('Windows', {}).get(nome_fonte))
    if not caminho_da_fonte:
        print(f"AVISO: Fonte '{nome_fonte}' não encontrada. Usando Cunia como padrão.")
        caminho_da_fonte = FONT_PATHS['Windows']['cunia']
    tamanho_fonte = data.get('texto_tamanho', 70)
    try:
        if data.get('texto_negrito', False) and nome_fonte == 'arial':
            caminho_da_fonte = FONT_PATHS.get(sistema_op, {}).get('arialbd', caminho_da_fonte)
        font = ImageFont.truetype(caminho_da_fonte, size=tamanho_fonte)
    except Exception as e:
        print(f"AVISO: Fonte '{caminho_da_fonte}' não pôde ser carregada: {e}. Usando fonte padrão.")
        font = ImageFont.load_default(size=tamanho_fonte)
    
    texto_quebrado = textwrap.fill(texto, width=30)
    img = Image.new("RGBA", target_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    espacamento_entre_linhas = 15
    
    bbox = draw.textbbox((0, 0), texto_quebrado, font=font, align="center", spacing=espacamento_entre_linhas)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    x = (w - text_w) / 2
    if posicao == 'inferior':
        y = h - text_h - (h * 0.15)
    else:
        y = (h - text_h) / 2

    cor_rgba = cor_da_fonte_hex

    draw.text((x + 2, y + 2), texto_quebrado, font=font, fill=(0, 0, 0, 128), align="center", spacing=espacamento_entre_linhas)
    draw.text((x, y), texto_quebrado, font=font, fill=cor_rgba, align="center", spacing=espacamento_entre_linhas)
    
    if data.get('texto_sublinhado', False):
        num_linhas = len(texto_quebrado.split('\n'))
        altura_total_texto_sem_espaco = text_h - (espacamento_entre_linhas * (num_linhas - 1))
        altura_linha_unica = altura_total_texto_sem_espaco / num_linhas
        for i, linha_texto in enumerate(texto_quebrado.split('\n')):
            linha_y = y + (i * (altura_linha_unica + espacamento_entre_linhas))
            bbox_linha = draw.textbbox((0, 0), linha_texto, font=font)
            largura_linha = bbox_linha[2] - bbox_linha[0]
            x_linha = (w - largura_linha) / 2
            underline_y = linha_y + altura_linha_unica + 2
            draw.line((x_linha, underline_y, x_linha + largura_linha, underline_y), fill=cor_rgba, width=2)
    
    temp_dir = os.path.join(settings.MEDIA_ROOT, 'text_temp')
    os.makedirs(temp_dir, exist_ok=True)
    caminho_imagem_texto = os.path.join(temp_dir, f"texto_{random.randint(1000,9999)}.png")
    img.save(caminho_imagem_texto)
    return caminho_imagem_texto

def gerar_audio_e_tempos(texto, nome_da_voz, velocidade, tom, obter_tempos=False):
    try:
        client = texttospeech.TextToSpeechClient()
        if obter_tempos:
            palavras = texto.split()
            ssml_texto = "<speak>" + "".join(f'{palavra} <mark name="word_{i}"/> ' for i, palavra in enumerate(palavras)) + "</speak>"
            synthesis_input = texttospeech.SynthesisInput(ssml=ssml_texto)
        else:
            synthesis_input = texttospeech.SynthesisInput(text=texto)
        voice = texttospeech.VoiceSelectionParams(language_code="pt-BR", name=nome_da_voz)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=velocidade / 100.0, pitch=float(tom)
        )
        request = texttospeech.SynthesizeSpeechRequest(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        if obter_tempos:
            request.enable_time_pointing = [texttospeech.SynthesizeSpeechRequest.TimepointType.SSML_MARK]
        response = client.synthesize_speech(request=request)
        timepoints = response.timepoints if obter_tempos else None
        narrador_temp_dir = os.path.join(settings.MEDIA_ROOT, 'narrador_temp')
        os.makedirs(narrador_temp_dir, exist_ok=True)
        nome_arquivo_narrador = f"narrador_{random.randint(10000, 99999)}.mp3"
        caminho_narrador_input = os.path.join(narrador_temp_dir, nome_arquivo_narrador)
        with open(caminho_narrador_input, "wb") as out:
            out.write(response.audio_content)
        return caminho_narrador_input, timepoints
    except Exception as e:
        print(f"--- ERRO GERAL AO GERAR ÁUDIO DO NARRADOR: {e} ---")
        return None, None

def formatar_tempo_ass(segundos):
    h = int(segundos // 3600); m = int((segundos % 3600) // 60); s = int(segundos % 60)
    cs = int((segundos - int(segundos)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def gerar_ficheiro_legenda_ass(timepoints, texto_original, data, cor_da_fonte_hex, posicao='centro'):
    sistema_op = platform.system()
    nome_fonte = data.get('texto_fonte', 'cunia')
    caminho_fonte = FONT_PATHS.get(sistema_op, {}).get(nome_fonte, FONT_PATHS['Windows']['cunia'])
    nome_fonte_ass = os.path.splitext(os.path.basename(caminho_fonte))[0].replace('_', ' ')
    tamanho = data.get('texto_tamanho', 70); negrito = -1 if data.get('texto_negrito', False) else 0
    sublinhado = -1 if data.get('texto_sublinhado', False) else 0
    
    hex_limpo = cor_da_fonte_hex.lstrip('#')
    r, g, b = tuple(int(hex_limpo[i:i+2], 16) for i in (0, 2, 4))
    cor_secundaria_ass = f"&H{b:02X}{g:02X}{r:02X}"

    if posicao == 'inferior':
        alignment_code = 2
        margin_v = 150
    else:
        alignment_code = 5
        margin_v = 10

    cor_primaria = '&H808080'
    cor_secundaria = cor_secundaria_ass
    cor_outline = '&H000000'
    cor_back = '&H00000000'

    header = (
        f"[Script Info]\nTitle: Video Gerado\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        f"[V4+ Styles]\n"
        f"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{nome_fonte_ass},{tamanho},{cor_primaria},{cor_secundaria},{cor_outline},{cor_back},{negrito},0,{sublinhado},0,100,100,0,0,1,2,2,{alignment_code},10,10,{margin_v},1\n\n"
        f"[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    palavras = texto_original.split()
    if not timepoints or len(timepoints) != len(palavras):
        print(f"--- AVISO: Discrepância de timepoints/palavras. Legenda não gerada. ---")
        return None
    texto_quebrado = textwrap.fill(texto_original, width=30)
    linhas = texto_quebrado.splitlines(); linhas_dialogo = []; word_index = 0
    for linha in linhas:
        words_in_line = linha.split(); num_words = len(words_in_line)
        if num_words == 0: continue
        start_time = 0.0 if word_index == 0 else timepoints[word_index - 1].time_seconds
        end_time = timepoints[word_index + num_words - 1].time_seconds
        karaoke_text = ""; prev_time = start_time
        for j in range(num_words):
            tp = timepoints[word_index + j]; dur = tp.time_seconds - prev_time
            dur_cs = max(1, int(dur * 100)); word = words_in_line[j]
            karaoke_text += f"{{\\k{dur_cs}}}{word} "; prev_time = tp.time_seconds
        karaoke_text = karaoke_text.strip(); start_str = formatar_tempo_ass(start_time); end_str = formatar_tempo_ass(end_time)
        linhas_dialogo.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{karaoke_text}")
        word_index += num_words
    conteudo_ass = header + "\n".join(linhas_dialogo)
    legenda_temp_dir = os.path.join(settings.MEDIA_ROOT, 'legenda_temp')
    os.makedirs(legenda_temp_dir, exist_ok=True)
    caminho_legenda = os.path.join(legenda_temp_dir, f"legenda_{random.randint(1000,9999)}.ass")
    with open(caminho_legenda, 'w', encoding='utf-8') as f: f.write(conteudo_ass)
    return caminho_legenda

def preview_voz(request, nome_da_voz):
    texto_exemplo = "Esta é uma demonstração da minha voz."
    try:
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=texto_exemplo)
        voice = texttospeech.VoiceSelectionParams(language_code="pt-BR", name=nome_da_voz)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        return HttpResponse(response.audio_content, content_type='audio/mpeg')
    except Exception as e:
        print(f"--- ERRO AO GERAR PREVIEW DA VOZ: {e} ---")
        return HttpResponse(status=500)

# ==============================================================================
# VIEW PRINCIPAL DO GERADOR
# ==============================================================================
@login_required
def pagina_gerador(request):
    if request.method == 'POST':
        formset = GeradorFormSet(request.POST, request.FILES)
    else:
        formset = GeradorFormSet()
    
    if request.method == 'POST' and formset.is_valid():
        for form in formset:
            if not form.has_changed():
                continue
            
            data = form.cleaned_data
            caminho_narrador_input, timepoints, caminho_legenda_ass, caminho_imagem_texto, caminho_tela_final = None, None, None, None, None
            
            usar_narrador = data.get('tipo_conteudo') == 'narrador'
            cor_selecionada_hex = data.get('cor_da_fonte', '#FFFFFF')
            posicao_selecionada = data.get('posicao_texto', 'centro')
            texto_tela_final = data.get('texto_tela_final')
            
            if usar_narrador and data.get('narrador_texto'):
                obter_tempos = data.get('legenda_sincronizada', False)
                caminho_narrador_input, timepoints = gerar_audio_e_tempos(
                    data['narrador_texto'], data['narrador_voz'],
                    data['narrador_velocidade'], data['narrador_tom'],
                    obter_tempos=obter_tempos
                )
            
            if usar_narrador and data.get('legenda_sincronizada') and timepoints:
                caminho_legenda_ass = gerar_ficheiro_legenda_ass(timepoints, data['narrador_texto'], data, cor_selecionada_hex, posicao_selecionada)
                print(f"--- Caminho do arquivo de legenda gerado: {caminho_legenda_ass} ---") # DEBUG
            
            if not usar_narrador and data.get('texto_overlay'):
                caminho_imagem_texto = create_text_image(data['texto_overlay'], cor_selecionada_hex, data, posicao_selecionada)
            
            if texto_tela_final:
                opcoes_tela_final = {'texto_fonte': 'arial', 'texto_tamanho': 80}
                caminho_tela_final = create_text_image(texto_tela_final, '#FFFFFF', opcoes_tela_final, 'centro')

            video_base = VideoBase.objects.filter(categoria=data['categoria_video']).order_by('?').first()
            musica_base = MusicaBase.objects.filter(categoria=data['categoria_musica']).order_by('?').first()

            if not video_base or not musica_base:
                print("AVISO: Mídia de fundo não encontrada. Pulando.")
                continue

            caminho_video_input = video_base.arquivo_video.path
            caminho_musica_input = musica_base.arquivo_musica.path
            
            nome_base = f"video_{request.user.id}_{random.randint(10000, 99999)}"
            caminho_video_final = os.path.join(settings.MEDIA_ROOT, 'videos_gerados', f"{nome_base}.mp4")
            caminho_video_temp = os.path.join(settings.MEDIA_ROOT, 'videos_gerados', f"{nome_base}_temp.mp4")
            caminho_tela_final_video = os.path.join(settings.MEDIA_ROOT, 'videos_gerados', f"{nome_base}_endscreen.mp4")
            lista_concat_path = os.path.join(settings.MEDIA_ROOT, 'videos_gerados', f"{nome_base}_concat.txt")

            try:
                # ETAPA 1: Gerar vídeo principal
                cmd_etapa1 = ['ffmpeg', '-y']
                if usar_narrador or data.get('loop_video', False):
                    cmd_etapa1.extend(['-stream_loop', '-1', '-i', caminho_video_input])
                else:
                    cmd_etapa1.extend(['-i', caminho_video_input])
                
                inputs_adicionais_etapa1 = []
                if caminho_imagem_texto: inputs_adicionais_etapa1.append(caminho_imagem_texto)
                inputs_adicionais_etapa1.append(caminho_musica_input)
                if caminho_narrador_input: inputs_adicionais_etapa1.append(caminho_narrador_input)
                
                for f in inputs_adicionais_etapa1: cmd_etapa1.extend(['-i', f])
                    
                video_chain = "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:-1:-1,setsar=1"
                if caminho_legenda_ass:
                    caminho_legenda_ffmpeg = caminho_legenda_ass.replace('\\', '/').replace(':', '\\:')
                    video_chain += f",ass='{caminho_legenda_ffmpeg}'"
                
                final_video_stream = "[v]"
                if caminho_imagem_texto:
                    video_chain += f"[base];[base][1:v]overlay=(W-w)/2:(H-h)/2[v]"
                else:
                    video_chain += "[v]"

                volume_musica_decimal = data.get('volume_musica', 50) / 100.0
                music_input_index = 1 + (1 if caminho_imagem_texto else 0)
                
                if caminho_narrador_input:
                    narrator_input_index = music_input_index + 1
                    audio_chain = f"[{music_input_index}:a]volume={volume_musica_decimal}[a1];[{narrator_input_index}:a]volume=1.0[a2];[a1][a2]amix=inputs=2:duration=longest[aout]"
                else:
                    audio_chain = f"[{music_input_index}:a]volume={volume_musica_decimal}[aout]"

                filter_complex_str = f"{video_chain};{audio_chain}"
                cmd_etapa1.extend(['-filter_complex', filter_complex_str])
                cmd_etapa1.extend(["-map", final_video_stream, "-map", "[aout]"])

                duracao_desejada = data.get('duracao_segundos', 30)
                if usar_narrador and timepoints:
                    duracao_video = timepoints[-1].time_seconds + 1 # Adiciona 1 segundo de segurança
                    cmd_etapa1.extend(['-to', str(duracao_video)])
                elif not usar_narrador:
                    cmd_etapa1.extend(['-to', str(duracao_desejada)])
                else:
                    # Se não houver narração ou timepoints, usa a duração padrão
                    cmd_etapa1.extend(['-to', str(duracao_desejada)])


                cmd_etapa1.extend(['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k']) # Removido -shortest
                cmd_etapa1.append(caminho_video_temp)
                
                print("--- EXECUTANDO FFMPEG (ETAPA 1) ---"); print(f"Comando: {' '.join(cmd_etapa1)}")
                subprocess.run(cmd_etapa1, check=True, text=True, capture_output=True, encoding='utf-8')

                if caminho_tela_final:
                    # ETAPA 2: Criar vídeo da tela final
                    duracao_tela_final = 3 # Duração fixa de 3 segundos
                    cmd_etapa2 = [
                        'ffmpeg', '-y', '-loop', '1', '-t', str(duracao_tela_final),
                        '-i', caminho_tela_final,
                        '-f', 'lavfi', '-t', str(duracao_tela_final), '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '192k', '-shortest',
                        caminho_tela_final_video
                    ]
                    print("--- EXECUTANDO FFMPEG (ETAPA 2) ---"); print(f"Comando: {' '.join(cmd_etapa2)}")
                    subprocess.run(cmd_etapa2, check=True, text=True, capture_output=True, encoding='utf-8')

                    # ETAPA 3: Concatenar vídeos
                    with open(lista_concat_path, 'w') as f:
                        f.write(f"file '{caminho_video_temp.replace(os.sep, '/')}'\n")
                        f.write(f"file '{caminho_tela_final_video.replace(os.sep, '/')}'\n")

                    cmd_etapa3 = [
                        'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                        '-i', lista_concat_path,
                        '-c', 'copy',
                        caminho_video_final
                    ]
                    print("--- EXECUTANDO FFMPEG (ETAPA 3) ---"); print(f"Comando: {' '.join(cmd_etapa3)}")
                    subprocess.run(cmd_etapa3, check=True, text=True, capture_output=True, encoding='utf-8')
                
                else: 
                    os.rename(caminho_video_temp, caminho_video_final)

                VideoGerado.objects.create(
                    usuario=request.user,
                    status='CONCLUIDO',
                    arquivo_final=os.path.join('videos_gerados', f"{nome_base}.mp4"),
                    
                    # Mapeando cada campo do formulário para o modelo
                    plano_de_fundo=data.get('plano_de_fundo','normal'),
                    cor_da_fonte=data.get('cor_da_fonte'),
                    posicao_texto=data.get('posicao_texto'),
                    texto_overlay=data.get('texto_overlay', ''),
                    texto_fonte=data.get('texto_fonte'),
                    texto_tamanho=data.get('texto_tamanho'),
                    texto_negrito=data.get('texto_negrito', False),
                    texto_sublinhado=data.get('texto_sublinhado', False),
                    narrador_texto=data.get('narrador_texto', ''),
                    legenda_sincronizada=data.get('legenda_sincronizada', False),
                    narrador_voz=data.get('narrador_voz'),
                    narrador_velocidade=data.get('narrador_velocidade'),
                    narrador_tom=data.get('narrador_tom'),
                    duracao_segundos=data.get('duracao_segundos'),
                    volume_musica=data.get('volume_musica'),
                    loop=data.get('loop_video'), # Mapeamento correto de loop_video -> loop
                    texto_tela_final=data.get('texto_tela_final', '')
                    # O campo 'tipo_conteudo' foi intencionalmente removido, pois ele não é salvo.
                )
                print(f"--- SUCESSO! Vídeo salvo: {nome_base}.mp4 ---")
                
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"--- ERRO NO FFMPEG OU FFPROBE ---")
                if isinstance(e, subprocess.CalledProcessError):
                    print(f"Comando que falhou: {' '.join(e.cmd)}")
                    print(f"Saída de Erro (stderr):\n{e.stderr}")
                else:
                    print("Erro: ffprobe não encontrado. Verifique se o FFmpeg está no PATH do sistema.")
                VideoGerado.objects.create(usuario=request.user, status='ERRO', texto_overlay=data.get('texto_overlay', ''))
            
            finally:
                for path in [caminho_narrador_input, caminho_legenda_ass, caminho_imagem_texto, caminho_tela_final, caminho_video_temp, caminho_tela_final_video, lista_concat_path]:
                    if path and os.path.exists(path):
                        os.remove(path)
        
        return redirect('meus_videos')
    
    return render(request, 'core/gerador.html', {'formset': formset})

# --- VIEWS DAS PÁGINAS ESTÁTICAS ---
@login_required
def meus_videos(request):
    videos = VideoGerado.objects.filter(usuario=request.user).order_by('-criado_em')
    return render(request, 'core/meus_videos.html', {'videos': videos})

def index(request): return render(request, 'core/home.html')
def como_funciona(request): return render(request, 'core/como_funciona.html')
def planos(request): return render(request, 'core/planos.html')
def cadastre_se(request): return render(request, 'core/cadastre-se.html')
def login_view(request): return render(request, 'core/login.html')
def suporte(request): return render(request, 'core/suporte.html')