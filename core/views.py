# ==============================================================================
# IMPORTS ORGANIZADOS
# ==============================================================================
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import subprocess
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
from django.urls import reverse
import random
import os
from datetime import timedelta
from django.utils import timezone # <-- ADICIONE ESTA LINHA
from django.db.models import Count, Q,Sum
import platform
import textwrap
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.conf import settings
from django.contrib import messages
from google.cloud import texttospeech_v1beta1 as texttospeech
from PIL import Image, ImageDraw, ImageFont
from .forms import GeradorFormSet, CadastroUsuarioForm, AdminUsuarioForm, EditarPerfilForm, ConfiguracaoForm,EditarAssinaturaForm
from .models import (
    Assinatura, Pagamento, Configuracao, VideoBase, 
    MusicaBase, VideoGerado, CategoriaVideo, CategoriaMusica, Plano,Usuario,VideoGerado
)



# Pega o modelo de usuário customizado que definimos
User = get_user_model()

# Se estiver usando `gcloud auth application-default login`, esta linha deve ficar comentada.
# os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(settings.BASE_DIR, 'gcloud-auth.json')


# ==============================================================================
# CONSTANTES E FUNÇÕES HELPER (LÓGICA DO GERADOR DE VÍDEO)
# ==============================================================================

FONT_PATHS = {
    'Windows': {
        'cunia': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'Cunia.ttf'),
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
        'cunia': os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'Cunia.ttf'),
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
# FUNÇÃO DE VERIFICAÇÃO DE ADMIN
# ==============================================================================
def is_admin(user):
    """Verifica se o usuário é parte da equipe (staff)."""
    return user.is_staff


# ==============================================================================
# VIEWS PÚBLICAS E DE AUTENTICAÇÃO
# ==============================================================================

def index(request): return render(request, 'core/home.html')
def como_funciona(request): return render(request, 'core/como_funciona.html')
def planos(request): return render(request, 'core/planos.html')
def suporte(request): return render(request, 'core/suporte.html')

def cadastre_se(request):
    if request.method == "POST":
        form = CadastroUsuarioForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Cadastro realizado com sucesso!")
            return redirect("pagina_gerador")
    else:
        form = CadastroUsuarioForm()
    return render(request, "core/user/cadastre-se.html", {"form": form})

def login_view(request):
    if request.method == "POST":
        email_digitado = request.POST.get("email")
        password_digitado = request.POST.get("password")
        if not email_digitado or not password_digitado:
            messages.error(request, "Por favor, preencha o email e a senha.")
            return render(request, "core/login.html")
        try:
            user_encontrado = User.objects.get(email=email_digitado)
            user = authenticate(request, username=user_encontrado.username, password=password_digitado)
            if user is not None:
                login(request, user)
                return redirect("meu_perfil")
            else:
                messages.error(request, "Email ou senha inválidos.")
        except User.DoesNotExist:
            messages.error(request, "Email ou senha inválidos.")
    return render(request, "core/login.html")

def logout_view(request):
    logout(request)
    return redirect("login")

# ==============================================================================
# VIEWS DA APLICAÇÃO (requerem login)
# ==============================================================================
def pagamento_falho(request):
    """
    Renderiza a página de pagamento falho.
    """
    return render(request, 'planos/pagamento_falho.html')

@csrf_exempt
def stripe_webhook(request):
    """
    CORRIGIDO E OTIMIZADO: Escuta os eventos do Stripe para gerenciar o ciclo de vida 
    completo das assinaturas de forma automática e robusta.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    event = None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        print(f"🚨 ERRO no webhook: Payload ou assinatura inválida. Detalhes: {e}")
        return HttpResponse(status=400)

    # --- LÓGICA DE PAGAMENTO BEM-SUCEDIDO (CRIAÇÃO INICIAL) ---
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        stripe_customer_id = session.get('customer')
        stripe_subscription_id = session.get('subscription')
        plano_id = session.get('metadata', {}).get('plano_id')
        valor_pago = session.get('amount_total', 0) / 100

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
                    'plano': plano,
                    'status': 'ativo',  # Define o status como 'ativo'
                    'data_inicio': timezone.now(),
                    'data_expiracao': timezone.now() + timedelta(days=30)
                }
            )
            # O método .save() da Assinatura já vai garantir que 'usuario.plano_ativo' seja True.

            # 3. CRIA O REGISTRO DO PAGAMENTO
            Pagamento.objects.create(
                usuario=usuario,
                plano=plano,
                valor=valor_pago,
                status='aprovado'
            )
            
            print(f"✅ Assinatura e Pagamento registrados com sucesso para: {usuario.email}")

        except (Usuario.DoesNotExist, Plano.DoesNotExist) as e:
            print(f"🚨 ERRO no webhook (checkout.session.completed): Usuário ou Plano não encontrado. Detalhes: {e}")
            return HttpResponse(status=404)

    # --- LÓGICA DE RENOVAÇÃO (PAGAMENTOS RECORRENTES) ---
    elif event['type'] == 'invoice.paid':
        invoice = event['data']['object']
        stripe_subscription_id = invoice.get('subscription')
        valor_pago = invoice.get('amount_paid', 0) / 100

        # Ignora invoices sem subscription_id (pagamentos únicos)
        if stripe_subscription_id:
            try:
                # Encontra a assinatura pela ID de inscrição do Stripe
                assinatura = Assinatura.objects.get(usuario__stripe_subscription_id=stripe_subscription_id)

                # 1. Garante que o status está ativo e estende a data de expiração
                assinatura.status = 'ativo'
                assinatura.data_expiracao = (assinatura.data_expiracao or timezone.now()) + timedelta(days=30)
                assinatura.save() # O .save() já atualiza o 'plano_ativo' do usuário para True

                # 2. Cria um novo registro de Pagamento para a renovação
                Pagamento.objects.create(
                    usuario=assinatura.usuario,
                    plano=assinatura.plano,
                    valor=valor_pago,
                    status='aprovado'
                )

                print(f"✅ Renovação processada para: {assinatura.usuario.email}. Nova expiração: {assinatura.data_expiracao.strftime('%d/%m/%Y')}")

            except Assinatura.DoesNotExist as e:
                print(f"🚨 ERRO no webhook (invoice.paid): Assinatura não encontrada para o subscription_id {stripe_subscription_id}. Detalhes: {e}")
                return HttpResponse(status=404)
            
    # --- LÓGICA DE PAGAMENTO FALHO (RENOVAÇÃO RECUSADA) ---
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        stripe_subscription_id = invoice.get('subscription')

        if stripe_subscription_id:
            try:
                assinatura = Assinatura.objects.get(usuario__stripe_subscription_id=stripe_subscription_id)
                
                # 1. Altera o status da assinatura para 'pendente'
                assinatura.status = 'pendente'
                assinatura.save() # O .save() já vai atualizar o 'plano_ativo' do usuário para False
                
                print(f"⚠️ Pagamento falhou para: {assinatura.usuario.email}. Assinatura marcada como 'pendente'.")
                # Aqui você pode adicionar lógica para notificar o usuário por e-mail.

            except Assinatura.DoesNotExist as e:
                print(f"🚨 ERRO no webhook (invoice.payment_failed): Assinatura não encontrada para {stripe_subscription_id}. Detalhes: {e}")

    # --- LÓGICA DE CANCELAMENTO (pelo cliente ou por falhas de pagamento) ---
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_subscription_id = subscription.get('id')

        try:
            assinatura = Assinatura.objects.get(usuario__stripe_subscription_id=stripe_subscription_id)
            
            # 1. Altera o status da assinatura para 'cancelado'
            assinatura.status = 'cancelado'
            # Opcional: Define a data de expiração para agora se desejar
            # assinatura.data_expiracao = timezone.now() 
            assinatura.save() # O .save() já vai atualizar o 'plano_ativo' do usuário para False

            print(f"✅ Assinatura cancelada no sistema para: {assinatura.usuario.email}")

        except Assinatura.DoesNotExist as e:
            print(f"🚨 ERRO no webhook (subscription.deleted): Assinatura não encontrada para {stripe_subscription_id}. Detalhes: {e}")

    return HttpResponse(status=200)
        








@login_required
def editar_perfil(request):
    if request.method == 'POST':
        form = EditarPerfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Seu perfil foi atualizado com sucesso!')
            return redirect('meu_perfil')
    else:
        form = EditarPerfilForm(instance=request.user)
        
    return render(request, 'core/usuarios/editar_perfil.html', {'form': form})

@login_required
def meu_perfil(request):
    assinatura = Assinatura.objects.filter(usuario=request.user).first()

    # --- INÍCIO DA ATUALIZAÇÃO ---
    # Busca o limite de vídeos no banco de dados
    try:
        limite_videos_mes = int(Configuracao.objects.get(nome='LIMITE_VIDEOS_MES').valor)
    except (Configuracao.DoesNotExist, ValueError):
        limite_videos_mes = 100 # Valor padrão caso não encontre

    # Conta quantos vídeos o usuário fez nos últimos 30 dias
    trinta_dias_atras = timezone.now() - timedelta(days=30)
    videos_criados_no_mes = VideoGerado.objects.filter(
        usuario=request.user, 
        criado_em__gte=trinta_dias_atras
    ).count()
    # --- FIM DA ATUALIZAÇÃO ---

    context = {
        'user': request.user,
        'assinatura': assinatura,
        # Enviando os novos dados para o template
        'videos_criados_no_mes': videos_criados_no_mes,
        'limite_videos_mes': limite_videos_mes,
    }
    return render(request, 'core/usuarios/perfil.html', context)

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
        return redirect('meu_perfil')

    try:
        # Constrói a URL de retorno completa para o seu site
        return_url = request.build_absolute_uri(reverse('meu_perfil'))

        # Cria a sessão do portal de clientes na API do Stripe
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        # Redireciona o usuário para a URL do portal gerada pelo Stripe
        return redirect(session.url)

    except Exception as e:
        messages.error(request, "Ocorreu um erro ao acessar o portal de assinaturas.")
        print(f"Erro do Stripe: {e}") # Para você ver o erro no terminal
        return redirect('meu_perfil')

@login_required
def meus_videos(request):
    videos = VideoGerado.objects.filter(usuario=request.user).order_by('-criado_em')

    # --- INÍCIO DA ATUALIZAÇÃO ---
    # REPETIMOS A MESMA LÓGICA AQUI PARA TER OS DADOS NA PÁGINA DE VÍDEOS
    try:
        limite_videos_mes = int(Configuracao.objects.get(nome='LIMITE_VIDEOS_MES').valor)
    except (Configuracao.DoesNotExist, ValueError):
        limite_videos_mes = 100

    trinta_dias_atras = timezone.now() - timedelta(days=30)
    videos_criados_no_mes = VideoGerado.objects.filter(
        usuario=request.user, 
        criado_em__gte=trinta_dias_atras
    ).count()
    # --- FIM DA ATUALIZAÇÃO ---

    context = {
        'videos': videos,
        'videos_criados_no_mes': videos_criados_no_mes,
        'limite_videos_mes': limite_videos_mes,
    }
    return render(request, 'core/meus_videos.html', context)

@login_required
def pagina_gerador(request):
    # Verificação 1: O usuário tem um plano ativo?
    tem_assinatura_ativa = Assinatura.objects.filter(usuario=request.user, status='ativo').exists()
    if not tem_assinatura_ativa:
        messages.warning(request, 'Você precisa de um plano ativo para acessar o gerador.')
        return redirect('planos')

    # --- INÍCIO DA NOVA VERIFICAÇÃO DE LIMITE ---

    # Busca o limite no banco de dados
    try:
        config_limite = Configuracao.objects.get(nome='LIMITE_VIDEOS_MES')
        limite_videos = int(config_limite.valor)
    except (Configuracao.DoesNotExist, ValueError):
        limite_videos = 100 # Usa 100 como padrão se a configuração não existir

    # Conta quantos vídeos o usuário fez nos últimos 30 dias
    trinta_dias_atras = timezone.now() - timedelta(days=30)
    videos_criados = VideoGerado.objects.filter(usuario=request.user, criado_em__gte=trinta_dias_atras).count()

    # Verificação 2: O usuário atingiu o limite?
    if videos_criados >= limite_videos:
        messages.error(request, f'Você atingiu seu limite de {limite_videos} vídeos por mês. Seu limite será renovado na sua próxima data de cobrança.')
        return redirect('meu_perfil') # Redireciona para o perfil

    # --- FIM DA VERIFICAÇÃO DE ASSINATURA ---

    # Se o código chegou até aqui, o usuário tem permissão. A lógica do gerador continua.
    if request.method == 'POST':
        formset = GeradorFormSet(request.POST, request.FILES)
        if formset.is_valid():
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
                
                if not usar_narrador and data.get('texto_overlay'):
                    caminho_imagem_texto = create_text_image(data['texto_overlay'], cor_selecionada_hex, data, posicao_selecionada)
                
                if texto_tela_final:
                    opcoes_tela_final = {'texto_fonte': 'arial', 'texto_tamanho': 80}
                    caminho_tela_final = create_text_image(texto_tela_final, '#FFFFFF', opcoes_tela_final, 'centro')

                video_base = VideoBase.objects.filter(categoria=data['categoria_video']).order_by('?').first()
                musica_base = MusicaBase.objects.filter(categoria=data['categoria_musica']).order_by('?').first()

                if not video_base or not musica_base:
                    messages.error(request, "Mídia de fundo (vídeo ou música) não encontrada para as categorias selecionadas.")
                    continue

                caminho_video_input = video_base.arquivo_video.path
                caminho_musica_input = musica_base.arquivo_musica.path
                
                nome_base = f"video_{request.user.id}_{random.randint(10000, 99999)}"
                caminho_video_final = os.path.join(settings.MEDIA_ROOT, 'videos_gerados', f"{nome_base}.mp4")
                caminho_video_temp = os.path.join(settings.MEDIA_ROOT, 'videos_gerados', f"{nome_base}_temp.mp4")
                caminho_tela_final_video = os.path.join(settings.MEDIA_ROOT, 'videos_gerados', f"{nome_base}_endscreen.mp4")
                lista_concat_path = os.path.join(settings.MEDIA_ROOT, 'videos_gerados', f"{nome_base}_concat.txt")

                try:
                    cmd_etapa1 = ['ffmpeg', '-y']
                    if usar_narrador or data.get('loop_video', False):
                        cmd_etapa1.extend(['-stream_loop', '-1', '-i', caminho_video_input])
                    else:
                        cmd_etapa1.extend(['-i', caminho_video_input])
                    
                    inputs_adicionais_etapa1 = [caminho_musica_input]
                    if caminho_imagem_texto: inputs_adicionais_etapa1.insert(0, caminho_imagem_texto)
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
                    cmd_etapa1.extend(['-filter_complex', filter_complex_str, "-map", final_video_stream, "-map", "[aout]"])

                    duracao_desejada = data.get('duracao_segundos', 30)
                    if usar_narrador and timepoints:
                        duracao_video = timepoints[-1].time_seconds + 1
                        cmd_etapa1.extend(['-t', str(duracao_video)])
                    else:
                        cmd_etapa1.extend(['-t', str(duracao_desejada)])

                    cmd_etapa1.extend(['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k'])
                    cmd_etapa1.append(caminho_video_temp)
                    
                    subprocess.run(cmd_etapa1, check=True, text=True, capture_output=True, encoding='utf-8')

                    if caminho_tela_final:
                        duracao_tela_final = 3
                        cmd_etapa2 = ['ffmpeg', '-y', '-loop', '1', '-t', str(duracao_tela_final), '-i', caminho_tela_final, '-f', 'lavfi', '-t', str(duracao_tela_final), '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest', caminho_tela_final_video]
                        subprocess.run(cmd_etapa2, check=True, text=True, capture_output=True, encoding='utf-8')

                        with open(lista_concat_path, 'w') as f:
                            f.write(f"file '{caminho_video_temp.replace(os.sep, '/')}'\n")
                            f.write(f"file '{caminho_tela_final_video.replace(os.sep, '/')}'\n")

                        cmd_etapa3 = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', lista_concat_path, '-c', 'copy', caminho_video_final]
                        subprocess.run(cmd_etapa3, check=True, text=True, capture_output=True, encoding='utf-8')
                    else: 
                        os.rename(caminho_video_temp, caminho_video_final)

                    # Bloco de criação do VideoGerado corrigido
                    dados_para_salvar = data.copy()
                    if 'loop_video' in dados_para_salvar:
                        dados_para_salvar['loop'] = dados_para_salvar.pop('loop_video')
                    chaves_para_remover = ['tipo_conteudo', 'categoria_video', 'categoria_musica']
                    for chave in chaves_para_remover:
                        dados_para_salvar.pop(chave, None)

                    VideoGerado.objects.create(
                        usuario=request.user, status='CONCLUIDO',
                        arquivo_final=os.path.join('videos_gerados', f"{nome_base}.mp4"),
                        **dados_para_salvar
                    )
                    messages.success(request, f"Vídeo '{nome_base}.mp4' gerado com sucesso!")
                    
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    messages.error(request, "Ocorreu um erro ao gerar seu vídeo.")
                    if isinstance(e, subprocess.CalledProcessError):
                        print(f"Comando que falhou: {' '.join(e.cmd)}")
                        print(f"Saída de Erro (stderr):\n{e.stderr}")
                    
                    dados_para_salvar = data.copy()
                    if 'loop_video' in dados_para_salvar:
                        dados_para_salvar['loop'] = dados_para_salvar.pop('loop_video')
                    chaves_para_remover = ['tipo_conteudo', 'categoria_video', 'categoria_musica']
                    for chave in chaves_para_remover:
                        dados_para_salvar.pop(chave, None)
                    VideoGerado.objects.create(usuario=request.user, status='ERRO', **dados_para_salvar)
                
                finally:
                    for path in [caminho_narrador_input, caminho_legenda_ass, caminho_imagem_texto, caminho_tela_final, caminho_video_temp, caminho_tela_final_video, lista_concat_path]:
                        if path and os.path.exists(path):
                            os.remove(path)
            
            return redirect('meus_videos')
    else:
        formset = GeradorFormSet()
    
    return render(request, 'core/gerador.html', {'formset': formset})


# ==============================================================================
# PAINEL DE ADMINISTRAÇÃO CUSTOMIZADO (PROTEGIDO)
# ==============================================================================

@login_required
@user_passes_test(is_admin)
def admin_assinaturas(request):
    assinaturas = Assinatura.objects.select_related('usuario', 'plano').all()
    return render(request, 'core/user/admin_assinaturas.html', {'assinaturas': assinaturas})



# Em seu arquivo core/views.py

# Certifique-se de que 'os' está importado no topo do seu arquivo


# ... (resto dos seus imports e views)

@login_required
def planos(request):
    # Verifica se o usuário tem um plano ativo
    if request.user.plano_ativo:
        # Busca a assinatura ativa mais recente do usuário no banco de dados
        assinatura_ativa = Assinatura.objects.filter(usuario=request.user, status='ativo').order_by('-data_inicio').first()
        
        context = {
            'assinatura': assinatura_ativa
        }
        # ATENÇÃO: Verifique o caminho correto do seu template.
        # Pode ser 'core/planos/plano_ativo.html' ou apenas 'plano_ativo.html' dependendo da sua estrutura
        return render(request, 'core/planos/plano_ativo.html', context)
    
    # Se não tiver plano ativo, mostra a página normal para assinar
    context = {
        'stripe_publishable_key': os.getenv("STRIPE_PUBLISHABLE_KEY")
    }
    return render(request, 'core/planos/planos.html', context)
@login_required
@user_passes_test(is_admin)
def ativar_assinatura(request, id):
    assinatura = get_object_or_404(Assinatura, id=id)
    assinatura.status = 'ativo'
    assinatura.save()
    messages.success(request, f"Assinatura de {assinatura.usuario.username} ativada.")
    return redirect('admin_assinaturas')

@login_required
@user_passes_test(is_admin)
def cancelar_assinatura(request, id):
    assinatura = get_object_or_404(Assinatura, id=id)
    assinatura.status = 'cancelado'
    assinatura.save()
    messages.warning(request, f"Assinatura de {assinatura.usuario.username} cancelada.")
    return redirect('admin_assinaturas')

@login_required
@user_passes_test(is_admin)
def editar_assinatura(request, id):
    assinatura = get_object_or_404(Assinatura, id=id)
    if request.method == "POST":
        form = EditarAssinaturaForm(request.POST, instance=assinatura)
        if form.is_valid():
            form.save()
            messages.info(request, "Assinatura atualizada com sucesso.")
            return redirect('admin_assinaturas')
    else:
        form = EditarAssinaturaForm(instance=assinatura)
        
    contexto = {
        'form': form,
        'assinatura': assinatura
    }
    return render(request, 'core/user/editar_assinatura.html', contexto)

@login_required
@user_passes_test(is_admin)
def excluir_assinatura(request, id):
    assinatura = get_object_or_404(Assinatura, id=id)
    assinatura.delete()
    messages.error(request, "Assinatura excluída.")
    return redirect('admin_assinaturas')

# Em core/views.py

@login_required
@user_passes_test(is_admin)
def admin_usuarios(request):
    # Calcula a data de 30 dias atrás a partir de hoje
    trinta_dias_atras = timezone.now() - timedelta(days=30)

    # A mágica acontece aqui: .annotate() adiciona um novo campo temporário
    # 'videos_no_mes' a cada usuário, contando apenas os vídeos criados
    # nos últimos 30 dias.
    usuarios = User.objects.prefetch_related('assinatura_set').annotate(
        videos_no_mes=Count('videogerado', filter=Q(videogerado__criado_em__gte=trinta_dias_atras))
    ).order_by('-date_joined')

    contexto = {
        'usuarios': usuarios
    }
    return render(request, 'core/user/admin_usuarios.html', contexto)

@login_required
@user_passes_test(is_admin)
def editar_usuario(request, user_id):
    user = get_object_or_404(User, id=user_id)
    assinatura = Assinatura.objects.filter(usuario=user).order_by('-data_inicio').first()

    if request.method == 'POST':
        form = AdminUsuarioForm(request.POST)
        if form.is_valid():
            # Atualiza os dados do Usuário
            user.username = form.cleaned_data['username']
            user.email = form.cleaned_data['email']
            user.is_staff = form.cleaned_data['is_staff']
            user.save()

            # Lógica para gerenciar a Assinatura
            plano_selecionado = form.cleaned_data['plano']
            status_selecionado = form.cleaned_data['status']

            if plano_selecionado:
                # --- INÍCIO DA ATUALIZAÇÃO ---
                # Busca a duração da assinatura no banco de dados
                try:
                    config_duracao = Configuracao.objects.get(nome='DURACAO_ASSINATURA_DIAS')
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
                    if status_selecionado == 'ativo':
                        # Usa a duração vinda do banco de dados
                        assinatura.data_expiracao = timezone.now() + timedelta(days=duracao_dias)
                    assinatura.save()
                else:
                    # Se não existe e um plano foi selecionado, cria uma nova
                    Assinatura.objects.create(
                        usuario=user,
                        plano=plano_selecionado,
                        status=status_selecionado,
                        data_inicio=timezone.now(),
                        # Usa a duração vinda do banco de dados
                        data_expiracao=timezone.now() + timedelta(days=duracao_dias)
                    )
                messages.success(request, f'Assinatura de {user.username} atualizada.')
            
            elif assinatura:
                assinatura.status = 'cancelado'
                assinatura.save()
                messages.warning(request, f'Assinatura de {user.username} cancelada.')

            messages.success(request, f'Usuário "{user.username}" atualizado com sucesso!')
            return redirect('admin_usuarios')
    else:
        initial_data = {
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff
        }
        if assinatura:
            initial_data['plano'] = assinatura.plano
            initial_data['status'] = assinatura.status
        
        form = AdminUsuarioForm(initial=initial_data)
        
    contexto = {
        'form': form,
        'usuario_editando': user,
        'assinatura': assinatura
    }
    return render(request, 'core/user/editar_usuario.html', contexto)

@login_required
@user_passes_test(is_admin)
def deletar_usuario(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    messages.error(request, "Usuário excluído.")
    return redirect('admin_usuarios')

@login_required
@user_passes_test(is_admin)
def admin_configuracoes(request):
    configuracoes = Configuracao.objects.all()
    return render(request, 'core/user/admin_configuracoes.html', {'configuracoes': configuracoes})

@login_required
@user_passes_test(is_admin)
def adicionar_configuracao(request):
    if request.method == "POST":
        form = ConfiguracaoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Nova configuração salva com sucesso.")
            return redirect('admin_configuracoes')
    else:
        form = ConfiguracaoForm()
    contexto = {'form': form}
    return render(request, 'core/user/adicionar_configuracao.html', contexto)

@login_required
@user_passes_test(is_admin)
def editar_configuracao(request, id):
    config = get_object_or_404(Configuracao, id=id)
    if request.method == "POST":
        form = ConfiguracaoForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.info(request, "Configuração atualizada com sucesso.")
            return redirect('admin_configuracoes')
    else:
        form = ConfiguracaoForm(instance=config)
        
    contexto = {
        'form': form,
        'config': config
    }
    return render(request, 'core/user/editar_configuracao.html', contexto)

@login_required
@user_passes_test(is_admin)
def deletar_configuracao(request, id):
    config = get_object_or_404(Configuracao, id=id)
    if request.method == "POST":
        config.delete()
        messages.error(request, f"A configuração '{config.nome}' foi excluída.")
        return redirect('admin_configuracoes')
    
    # Se a requisição for GET, mostra uma página de confirmação
    contexto = {'item': config}
    return render(request, 'core/user/confirmar_exclusao.html', contexto)

@login_required
@user_passes_test(is_admin)
def admin_pagamentos(request):
    pagamentos = Pagamento.objects.select_related('usuario', 'plano').all()
    return render(request, 'core/user/admin_pagamentos.html', {'pagamentos': pagamentos})

@login_required
@user_passes_test(is_admin)
def aprovar_pagamento(request, id):
    pagamento = get_object_or_404(Pagamento, id=id)
    usuario = pagamento.usuario

    # 1. Atualiza o status do pagamento (como já fazia)
    pagamento.status = 'aprovado'
    pagamento.save()

    # --- INÍCIO DA CORREÇÃO ---
    # 2. Busca a duração padrão da assinatura nas configurações
    try:
        config_duracao = Configuracao.objects.get(nome='DURACAO_ASSINATURA_DIAS')
        duracao_dias = int(config_duracao.valor)
    except (Configuracao.DoesNotExist, ValueError):
        duracao_dias = 30 # Usa 30 dias como padrão se não encontrar

    # 3. Atualiza ou cria a ASSINATURA do usuário, deixando-a ativa
    Assinatura.objects.update_or_create(
        usuario=usuario,
        defaults={
            'plano': pagamento.plano,
            'status': 'ativo',
            'data_expiracao': timezone.now() + timedelta(days=duracao_dias)
        }
    )
    # O método .save() da Assinatura já vai garantir que o 'usuario.plano_ativo' seja True.
    # --- FIM DA CORREÇÃO ---

    messages.success(request, f"Pagamento de {usuario.username} aprovado e assinatura ativada/atualizada.")
    return redirect('admin_pagamentos')

@login_required
@user_passes_test(is_admin)
def recusar_pagamento(request, id):
    pagamento = get_object_or_404(Pagamento, id=id)
    usuario = pagamento.usuario

    # 1. Atualiza o status do pagamento
    pagamento.status = 'recusado'
    pagamento.save()

    # --- INÍCIO DA CORREÇÃO ---
    # 2. Busca a assinatura do usuário (se existir)
    assinatura = Assinatura.objects.filter(usuario=usuario).first()
    if assinatura:
        # 3. Altera o status da assinatura para pendente
        #    Isso vai desativar o acesso do usuário ao gerador
        assinatura.status = 'pendente'
        assinatura.save()
        messages.warning(request, f"Pagamento de {usuario.username} recusado e assinatura marcada como pendente.")
    else:
        messages.warning(request, f"Pagamento de {usuario.username} recusado.")
    # --- FIM DA CORREÇÃO ---
    
    return redirect('admin_pagamentos')

@login_required
@user_passes_test(is_admin)
def deletar_pagamento(request, id):
    pagamento = get_object_or_404(Pagamento, id=id)
    pagamento.delete()
    messages.error(request, "Pagamento excluído.")
    return redirect('admin_pagamentos')

@login_required
@user_passes_test(is_admin)
def admin_relatorios(request):
    # --- LÓGICA ANTIGA (BUSCANDO AS LISTAS) ---
    assinaturas = Assinatura.objects.select_related('usuario', 'plano').order_by('-data_inicio')
    pagamentos = Pagamento.objects.select_related('usuario', 'plano').order_by('-data_pagamento')

    # --- NOVA LÓGICA (CALCULANDO OS INDICADORES / KPIs) ---

    # 1. Total de Assinantes com status 'ativo'
    total_assinantes_ativos = Assinatura.objects.filter(status='ativo').count()

    # 2. Receita total, somando apenas pagamentos 'aprovados'
    receita_total = Pagamento.objects.filter(status='aprovado').aggregate(soma=Sum('valor'))['soma'] or 0

    # 3. Novos assinantes nos últimos 30 dias
    trinta_dias_atras = timezone.now() - timedelta(days=30)
    novos_assinantes = Assinatura.objects.filter(data_inicio__gte=trinta_dias_atras).count()
    
    # 4. Total de vídeos gerados na plataforma
    total_videos_gerados = VideoGerado.objects.count()

    context = {
        'assinaturas': assinaturas,
        'pagamentos': pagamentos,
        # Adicionando os novos KPIs ao contexto para serem usados no template
        'total_assinantes_ativos': total_assinantes_ativos,
        'receita_total': receita_total,
        'novos_assinantes': novos_assinantes,
        'total_videos_gerados': total_videos_gerados,
    }
    return render(request, 'core/user/admin_relatorios.html', context)


@login_required
def pagamento_sucesso(request):
    """
    Apenas exibe uma mensagem de sucesso. A ativação real do plano é feita pelo webhook.
    """
    messages.success(request, "Pagamento recebido com sucesso! Seu plano será ativado em instantes.")
    return render(request, 'core/pagamento_sucesso.html')
@login_required
def criar_checkout_session(request):

    if request.user.plano_ativo:
        messages.warning(request, "Você já possui um plano ativo.")
        return redirect('plano_ativo')  # Assuma que você tem uma view/template para isso, ou crie
    """
    Cria uma sessão de checkout no Stripe para o usuário logado assinar o plano.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        # Pega o primeiro plano disponível. Ideal para quando se tem apenas um plano.
        # Se tiver múltiplos planos, você precisará de uma lógica para identificar qual plano o usuário escolheu.
        plano = Plano.objects.first()
        if not plano:
            messages.error(request, "Nenhum plano de assinatura foi configurado no sistema.")
            return redirect('planos')

        # 1. Busca o ID do cliente no Stripe (se não tiver, cria um novo)
        stripe_customer_id = request.user.stripe_customer_id
        if not stripe_customer_id:
            customer = stripe.Customer.create(
                email=request.user.email,
                name=request.user.username
            )
            request.user.stripe_customer_id = customer.id
            request.user.save()
            stripe_customer_id = customer.id

        # 2. Define as URLs de sucesso e cancelamento
        success_url = request.build_absolute_uri(reverse('pagamento_sucesso'))
        cancel_url = request.build_absolute_uri(reverse('planos'))

        # 3. Cria a sessão de Checkout no Stripe
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': settings.STRIPE_PRICE_ID, # O ID do preço do seu plano no Stripe
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            # ADICIONADO: Envia o ID do nosso plano para o webhook
            metadata={
                'plano_id': plano.id
            }
        )
        
        return redirect(checkout_session.url, code=303)

    except Exception as e:
        messages.error(request, "Não foi possível iniciar o processo de pagamento. Tente novamente mais tarde.")
        print(f"Erro do Stripe ao criar checkout: {e}")
        return redirect(reverse('planos'))



# ==============================================================================
# VIEWS ADICIONADAS PARA GERENCIAMENTO DE STATUS PELO ADMIN
# ==============================================================================

@user_passes_test(lambda u: u.is_staff) # Garante que apenas admins acessem
def deixar_assinatura_pendente(request, assinatura_id):
    """
    View para o admin marcar uma assinatura como 'pendente'.
    """
    assinatura = get_object_or_404(Assinatura, id=assinatura_id)
    assinatura.status = 'pendente'
    assinatura.save() # O método save que modificamos cuidará de atualizar o usuário
    messages.warning(request, f"A assinatura de {assinatura.usuario.username} foi marcada como pendente.")
    return redirect('admin_usuarios') # Redireciona de volta para a lista de usuários


@user_passes_test(lambda u: u.is_staff) # Garante que apenas admins acessem
def cancelar_assinatura_admin(request, assinatura_id):
    """
    View para o admin cancelar uma assinatura.
    """
    assinatura = get_object_or_404(Assinatura, id=assinatura_id)
    assinatura.status = 'cancelado'
    assinatura.save() # O método save que modificamos cuidará de atualizar o usuário
    messages.error(request, f"A assinatura de {assinatura.usuario.username} foi cancelada.")
    return redirect('admin_usuarios') # Redireciona de volta para a lista de usuários
    

    