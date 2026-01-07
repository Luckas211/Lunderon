# Em core/views.py
import json
import logging
import os
import random
import re
import uuid
from datetime import timedelta

import requests
import stripe
import yt_dlp
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import (
    AdminUsuarioForm,
    CadastroUsuarioForm,
    ConfiguracaoForm,
    CortesYouTubeForm,
    EditarAssinaturaForm,
    EditarPerfilForm,
    GeradorForm,
)
from .models import (
    Assinatura,
    CorteGerado,
    CategoriaVideo,
    Configuracao,
    MusicaBase,
    Pagamento,
    Plano,
    Usuario,
    VideoBase,
    VideoGerado,
)
from .services import gerar_audio_e_tempos, estimar_tempo_narracao as estimar_tempo_narracao_service
from .tasks import task_processar_corte_youtube, task_processar_geracao_video
from .utils import (
    delete_from_r2,
    generate_presigned_url,
    get_valid_media_from_category,
    is_token_valid,
    send_verification_email,
    upload_fileobj_to_r2,
)

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


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


@login_required
def preview_voz(request, nome_da_voz):
    """
    Gera um preview de áudio para uma voz específica e retorna a URL.
    """
    try:
        texto_teste = "Esta é uma prévia da voz selecionada."

        # Usa a função `gerar_audio_e_tempos` que agora está em services.py
        caminho_audio_temp, _, duracao = gerar_audio_e_tempos(
            texto=texto_teste,
            voz=nome_da_voz,
            velocidade=100
        )

        if not caminho_audio_temp:
            raise Exception("A função `gerar_audio_e_tempos` não retornou um caminho de áudio.")

        # Define o diretório e o nome do arquivo final dentro da pasta de mídia
        audio_preview_dir = os.path.join(settings.MEDIA_ROOT, 'audio_previews')
        os.makedirs(audio_preview_dir, exist_ok=True)
        
        nome_arquivo = f"preview_{nome_da_voz}_{random.randint(1000, 9999)}.wav"
        caminho_audio_final = os.path.join(audio_preview_dir, nome_arquivo)

        # Move o arquivo temporário para o local público
        os.rename(caminho_audio_temp, caminho_audio_final)

        # Gera a URL pública para o arquivo
        url_audio = os.path.join(settings.MEDIA_URL, 'audio_previews', nome_arquivo).replace('\\', '/')

        # Retorna a URL em uma resposta JSON
        return JsonResponse({'url': url_audio})

    except Exception as e:
        logger.error(f"Erro ao gerar preview de voz para '{nome_da_voz}': {e}", exc_info=True)
        return JsonResponse({"error": "Ocorreu um erro interno ao gerar o áudio."}, status=500)


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
            titulo_curto = (titulo_video[:30] + "...") if len(titulo_video) > 30 else titulo_video
            messages.success(
                request,
                f'Boas notícias! O seu vídeo "{titulo_curto}" foi gerado com sucesso.',
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

    videos_criados_no_mes, limite_videos_mes, assinatura = _get_user_video_usage(
        request.user
    )

    uso_percentual = 0
    if limite_videos_mes > 0:
        # Calcula a porcentagem de uso
        uso_percentual = (videos_criados_no_mes / limite_videos_mes) * 100

    context = {
        "videos": videos,
        "videos_criados_no_mes": videos_criados_no_mes,
        "limite_videos_mes": limite_videos_mes,
        "uso_percentual": uso_percentual,
    }
    return render(request, "core/meus_videos.html", context)


@login_required
def video_download_page(request, video_id):
    video = get_object_or_404(VideoGerado, id=video_id, usuario=request.user)

    if video.status != "CONCLUIDO" or not video.arquivo_final:
        messages.error(request, "Este vídeo não está mais disponível para download.")
        return redirect("meus_videos")

    presigned_url = generate_presigned_url(
        video.arquivo_final, expiration=300
    )  # 5 minutos

    if not presigned_url:
        messages.error(request, "Não foi possível gerar o link de download.")
        return redirect("meus_videos")

    context = {"video": video, "download_url": presigned_url}
    return render(request, "core/download_page.html", context)

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
    video = get_object_or_404(VideoGerado, id=video_id, usuario=request.user)

    if video.status != "CONCLUIDO" or not video.arquivo_final:
        messages.error(request, "Este vídeo não está mais disponível.")
        return redirect("meus_videos")

    tempo_expiracao = video.criado_em + timedelta(hours=1)

    if timezone.now() > tempo_expiracao:
        messages.warning(
            request,
            "O link de download para este vídeo expirou e o arquivo foi removido.",
        )
        delete_from_r2(video.arquivo_final)
        video.arquivo_final = None
        video.save()
        return redirect("meus_videos")

    presigned_url = generate_presigned_url(
        video.arquivo_final, expiration=600
    )  # Link válido por 10 min

    if not presigned_url:
        messages.error(request, "Não foi possível gerar o link de download no momento.")
        return redirect("meus_videos")

    return redirect(presigned_url)


@require_POST
@csrf_exempt
def estimativa_narracao(request):
    try:
        data = json.loads(request.body)
        texto = data.get("texto", "")
        velocidade = data.get("velocidade", 100)

        duracao_segundos, num_palavras = estimar_tempo_narracao_service(texto, velocidade)

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

def suporte(request):
    return render(request, "core/suporte.html")

def termos_de_servico(request):
    return render(request, "core/termos_de_servico.html")

def politica_de_privacidade(request):
    return render(request, "core/politica_de_privacidade.html")

def verificar_email(request, token):
    try:
        user = Usuario.objects.get(email_verification_token=token)
    except Usuario.DoesNotExist:
        messages.error(request, "Link de verificação inválido ou já utilizado.")
        return redirect("login")

    if is_token_valid(user, token):
        user.is_active = True
        user.email_verificado = True
        user.email_verification_token = None
        user.email_verification_token_created = None
        user.save()

        login(request, user)
        messages.success(
            request,
            "E-mail verificado com sucesso! Bem-vindo(a) à Lunderon.",
        )
        return redirect("meu_perfil")
    else:
        messages.error(
            request,
            "Seu link de verificação expirou. Por favor, tente se cadastrar novamente.",
        )
        return redirect("login")


def cadastre_se(request):
    if request.method == "POST":
        form = CadastroUsuarioForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            try:
                send_verification_email(user, request)
                messages.success(
                    request,
                    "Cadastro realizado com sucesso! Enviamos um link de ativação para o seu e-mail.",
                )
            except Exception as e:
                print(f"ERRO AO ENVIAR E-MAIL DE VERIFICAÇÃO: {e}")
                messages.error(
                    request,
                    "Ocorreu um erro ao enviar o e-mail de verificação. Por favor, tente novamente ou contate o suporte.",
                )
            return redirect("login")
    else:
        form = CadastroUsuarioForm()
    return render(request, "core/user/cadastre-se.html", {"form": form})


def validate_otp_view(request):
    # ATENÇÃO: Código temporário. Substituir pela lógica de validação de OTP.
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
            user_encontrado = Usuario.objects.get(email=email_digitado)

            if not user_encontrado.is_active:
                resend_url = reverse(
                    "reenviar_verificacao", kwargs={"user_id": user_encontrado.id}
                )
                mensagem = mark_safe(
                    f"Sua conta ainda não foi ativada. Por favor, verifique o link que enviamos para o seu e-mail. "
                    f'<a href="{resend_url}" class="alert-link">Não recebeu? Clique aqui para reenviar.</a>'
                )
                messages.warning(request, mensagem)
                return redirect("login")

            user = authenticate(
                request, username=user_encontrado.username, password=password_digitado
            )

            if user is not None:
                login(request, user)
                return redirect("meu_perfil")
            else:
                messages.error(request, "Email ou senha inválidos.")

        except Usuario.DoesNotExist:
            messages.error(request, "Email ou senha inválidos.")

    return render(request, "core/login.html")

def logout_view(request):
    logout(request)
    return redirect("login")

# ==============================================================================
# VIEWS DA APLICAÇÃO (requerem login)
# ==============================================================================
def pagamento_falho(request):
    return render(request, "planos/pagamento_falho.html")


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    event = None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        print(f"🚨 ERRO no webhook: Payload ou assinatura inválida. Detalhes: {e}")
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        stripe_customer_id = session.get("customer")
        stripe_subscription_id = session.get("subscription")
        plano_id = session.get("metadata", {}).get("plano_id")
        valor_pago = session.get("amount_total", 0) / 100

        try:
            usuario = Usuario.objects.get(stripe_customer_id=stripe_customer_id)
            plano = Plano.objects.get(id=plano_id)
            usuario.stripe_subscription_id = stripe_subscription_id
            usuario.save()
            Assinatura.objects.update_or_create(
                usuario=usuario,
                defaults={
                    "plano": plano,
                    "status": "ativo",
                    "data_inicio": timezone.now(),
                    "data_expiracao": timezone.now() + timedelta(days=30),
                },
            )
            Pagamento.objects.create(
                usuario=usuario, plano=plano, valor=valor_pago, status="aprovado"
            )
            print(f"✅ Assinatura e Pagamento registrados com sucesso para: {usuario.email}")
        except (Usuario.DoesNotExist, Plano.DoesNotExist) as e:
            print(f"🚨 ERRO no webhook (checkout.session.completed): Usuário ou Plano não encontrado. Detalhes: {e}")
            return HttpResponse(status=404)

    elif event["type"] == "invoice.paid":
        invoice = event["data"]["object"]
        stripe_subscription_id = invoice.get("subscription")
        valor_pago = invoice.get("amount_paid", 0) / 100
        if stripe_subscription_id:
            try:
                assinatura = Assinatura.objects.get(
                    usuario__stripe_subscription_id=stripe_subscription_id
                )
                assinatura.status = "ativo"
                assinatura.data_expiracao = (
                    assinatura.data_expiracao or timezone.now()
                ) + timedelta(days=30)
                assinatura.save()
                Pagamento.objects.create(
                    usuario=assinatura.usuario,
                    plano=assinatura.plano,
                    valor=valor_pago,
                    status="aprovado",
                )
                print(f"✅ Renovação processada para: {assinatura.usuario.email}. Nova expiração: {assinatura.data_expiracao.strftime('%d/%m/%Y')}")
            except Assinatura.DoesNotExist as e:
                print(f"🚨 ERRO no webhook (invoice.paid): Assinatura não encontrada para o subscription_id {stripe_subscription_id}. Detalhes: {e}")
                return HttpResponse(status=404)

    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        stripe_subscription_id = invoice.get("subscription")
        if stripe_subscription_id:
            try:
                assinatura = Assinatura.objects.get(
                    usuario__stripe_subscription_id=stripe_subscription_id
                )
                assinatura.status = "pendente"
                assinatura.save()
                print(f"⚠️ Pagamento falhou para: {assinatura.usuario.email}. Assinatura marcada como 'pendente'.")
            except Assinatura.DoesNotExist as e:
                print(f"🚨 ERRO no webhook (invoice.payment_failed): Assinatura não encontrada para {stripe_subscription_id}. Detalhes: {e}")

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        stripe_subscription_id = subscription.get("id")
        try:
            assinatura = Assinatura.objects.get(
                usuario__stripe_subscription_id=stripe_subscription_id
            )
            assinatura.status = "cancelado"
            assinatura.save()
            print(f"✅ Assinatura cancelada no sistema para: {assinatura.usuario.email}")
        except Assinatura.DoesNotExist as e:
            print(f"🚨 ERRO no webhook (subscription.deleted): Assinatura não encontrada para {stripe_subscription_id}. Detalhes: {e}")

    return HttpResponse(status=200)


@login_required
def editar_perfil(request):
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
    stripe_customer_id = request.user.stripe_customer_id
    if not stripe_customer_id:
        messages.error(request, "Não encontramos uma assinatura para gerenciar.")
        return redirect("meu_perfil")
    try:
        return_url = request.build_absolute_uri(reverse("meu_perfil"))
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return redirect(session.url)
    except Exception as e:
        messages.error(request, "Ocorreu um erro ao acessar o portal de assinaturas.")
        print(f"Erro do Stripe: {e}")
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


def planos(request):
    if request.user.is_authenticated and request.user.plano_ativo:
        videos_criados_no_mes, limite_videos_mes, assinatura_ativa = (
            _get_user_video_usage(request.user)
        )
        if not assinatura_ativa:
            return redirect("planos")
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

    todos_os_planos = Plano.objects.order_by("preco")
    context = {
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "planos": todos_os_planos,
    }
    return render(request, "core/planos/planos.html", context)


@login_required
@user_passes_test(is_admin)
def ativar_assinatura(request, id):
    assinatura = get_object_or_404(Assinatura, id=id)
    usuario = assinatura.usuario
    if not usuario.is_active:
        usuario.is_active = True
        usuario.email_verificado = True
        usuario.save(update_fields=["is_active", "email_verificado"])
    assinatura.status = "ativo"
    assinatura.save()
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


@user_passes_test(is_admin)
def admin_usuarios(request):
    trinta_dias_atras = timezone.now() - timedelta(days=30)
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
    contexto = {"usuarios": usuarios}
    return render(request, "core/user/admin_usuarios.html", contexto)


@login_required
@user_passes_test(is_admin)
def editar_usuario(request, user_id):
    user = get_object_or_404(Usuario, id=user_id)
    assinatura = (
        Assinatura.objects.filter(usuario=user).order_by("-data_inicio").first()
    )
    if request.method == "POST":
        form = AdminUsuarioForm(request.POST)
        if form.is_valid():
            user.username = form.cleaned_data["username"]
            user.email = form.cleaned_data["email"]
            user.is_staff = form.cleaned_data["is_staff"]
            user.save()
            plano_selecionado = form.cleaned_data["plano"]
            status_selecionado = form.cleaned_data["status"]
            if plano_selecionado:
                try:
                    config_duracao = Configuracao.objects.get(
                        nome="DURACAO_ASSINATURA_DIAS"
                    )
                    duracao_dias = int(config_duracao.valor)
                except (Configuracao.DoesNotExist, ValueError):
                    duracao_dias = 30
                if assinatura:
                    assinatura.plano = plano_selecionado
                    assinatura.status = status_selecionado
                    if status_selecionado == "ativo":
                        assinatura.data_expiracao = timezone.now() + timedelta(
                            days=duracao_dias
                        )
                    assinatura.save()
                else:
                    Assinatura.objects.create(
                        usuario=user,
                        plano=plano_selecionado,
                        status=status_selecionado,
                        data_inicio=timezone.now(),
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
def admin_ativar_usuario(request, user_id):
    user = get_object_or_404(Usuario, id=user_id)
    if not user.is_active:
        user.is_active = True
        user.email_verificado = True
        user.save()
        messages.success(request, f"Usuário {user.username} ativado com sucesso.")
    else:
        messages.info(request, f"Usuário {user.username} já estava ativo.")
    return redirect("admin_usuarios")


@login_required
@user_passes_test(is_admin)
def admin_reenviar_verificacao(request, user_id):
    try:
        user = Usuario.objects.get(id=user_id)
        if not user.is_active:
            send_verification_email(user, request)
            messages.success(
                request,
                f"Um novo link de verificação foi enviado para o e-mail de {user.email}.",
            )
        else:
            messages.info(
                request,
                "Esta conta já está ativa.",
            )
    except Usuario.DoesNotExist:
        messages.error(request, "Usuário não encontrado.")

    return redirect("admin_usuarios")


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
    usuario.is_active = True
    usuario.email_verificado = True
    usuario.save(update_fields=["is_active", "email_verificado"])
    try:
        config_duracao = Configuracao.objects.get(nome="DURACAO_ASSINATURA_DIAS")
        duracao_dias = int(config_duracao.valor)
    except (Configuracao.DoesNotExist, ValueError):
        duracao_dias = 30
    Assinatura.objects.update_or_create(
        usuario=usuario,
        defaults={
            "plano": pagamento.plano,
            "status": "ativo",
            "data_expiracao": timezone.now() + timedelta(days=duracao_dias),
        },
    )
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
    pagamento.status = "recusado"
    pagamento.save()
    assinatura = Assinatura.objects.filter(usuario=usuario).first()
    if assinatura:
        assinatura.status = "pendente"
        assinatura.save()
        messages.warning(
            request,
            f"Pagamento de {usuario.username} recusado e assinatura marcada como pendente.",
        )
    else:
        messages.warning(request, f"Pagamento de {usuario.username} recusado.")
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
    assinaturas = Assinatura.objects.select_related("usuario", "plano").order_by(
        "-data_inicio"
    )
    pagamentos = Pagamento.objects.select_related("usuario", "plano").order_by(
        "-data_pagamento"
    )
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
    usuarios_pendentes = Usuario.objects.filter(is_active=False, is_staff=False).count()
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
        "usuarios_pendentes": usuarios_pendentes,
        "ultimos_pendentes": ultimos_pendentes,
    }
    return render(request, "core/user/admin_relatorios.html", context)


@login_required
def pagamento_sucesso(request):
    messages.success(
        request, "Pagamento recebido com sucesso! Seu plano será ativado em instantes."
    )
    return render(request, "core/pagamento_sucesso.html")


@login_required
def criar_checkout_session(request, plano_id):
    if request.user.plano_ativo:
        messages.warning(request, "Você já possui um plano ativo.")
        return redirect("plano_ativo")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        plano = get_object_or_404(Plano, id=plano_id)
        if not plano.stripe_price_id:
            messages.error(
                request,
                "Este plano não está configurado para pagamento. Por favor, contate o suporte.",
            )
            return redirect("planos")
        stripe_customer_id = request.user.stripe_customer_id
        if not stripe_customer_id:
            customer = stripe.Customer.create(
                email=request.user.email, name=request.user.username
            )
            request.user.stripe_customer_id = customer.id
            request.user.save()
            stripe_customer_id = customer.id
        success_url = request.build_absolute_uri(reverse("pagamento_sucesso"))
        cancel_url = request.build_absolute_uri(reverse("planos"))
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            payment_method_types=["card"],
            line_items=[
                {
                    "price": plano.stripe_price_id,
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"plano_id": plano.id},
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        messages.error(
            request,
            "Não foi possível iniciar o processo de pagamento. Tente novamente mais tarde.",
        )
        print(f"Erro do Stripe ao criar checkout: {e}")
        return redirect(reverse("planos"))


@user_passes_test(lambda u: u.is_staff)
def deixar_assinatura_pendente(request, assinatura_id):
    assinatura = get_object_or_404(Assinatura, id=assinatura_id)
    assinatura.status = "pendente"
    assinatura.save()
    messages.warning(
        request,
        f"A assinatura de {assinatura.usuario.username} foi marcada como pendente.",
    )
    return redirect("admin_usuarios")


@user_passes_test(lambda u: u.is_staff)
def cancelar_assinatura_admin(request, assinatura_id):
    assinatura = get_object_or_404(Assinatura, id=assinatura_id)
    assinatura.status = "cancelado"
    assinatura.save()
    messages.error(
        request, f"A assinatura de {assinatura.usuario.username} foi cancelada."
    )
    return redirect("admin_usuarios")


@login_required
@require_POST
@csrf_exempt
def get_youtube_most_replayed_segments(request):
    try:
        data = json.loads(request.body)
        youtube_url = data.get("url")
        if not youtube_url or "youtube.com" not in youtube_url:
            return JsonResponse({"error": "URL do YouTube inválida."}, status=400)

        headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR,pt;q=0.9"}
        response = requests.get(youtube_url, headers=headers)
        response.raise_for_status()

        match = re.search(r'window["|"]ytInitialData["|"] = ({.*?});', response.text)
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
        processed_ranges = set()

        for deco in decorations:
            if (
                deco.get("label", {}).get("runs", [{}])[0].get("text")
                == "Mais repetidos"
            ):
                start_ms = int(deco.get("visibleTimeRangeStartMillis", 0))
                end_ms = int(deco.get("visibleTimeRangeEndMillis", 0))
                time_range_key = (start_ms, end_ms)
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

        return JsonResponse({"segments": sorted(segments, key=lambda x: x["start"]), "duration": duration})

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


@login_required
def pagina_gerador(request):
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
                if data.get("categoria_video"):
                    data["categoria_video"] = data["categoria_video"].id
                if data.get("categoria_musica"):
                    data["categoria_musica"] = data["categoria_musica"].id
                
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
    else:
        form = GeradorForm()

    context = {
        "form": form,
        "videos_restantes": limite_videos - videos_criados,
        "limite_videos_mes": limite_videos,
    }
    return render(request, "core/gerador.html", context)


@login_required
def cortes_youtube_view(request):
    videos_criados, limite_videos_mes, _ = _get_user_video_usage(request.user)

    if not request.user.plano_ativo:
        messages.warning(
            request,
            "Esta funcionalidade está disponível apenas para assinantes.",
        )
        return redirect("planos")

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

    else:
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
