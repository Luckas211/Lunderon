# Em core/utils.py

import secrets
import string
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse


def generate_verification_token():
    """Gera um token seguro para verificação de email"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(64))


def send_verification_email(user, request):
    """Envia email de verificação para o usuário"""
    token = generate_verification_token()
    user.email_verification_token = token
    user.email_verification_token_created = timezone.now()
    user.save()

    verification_url = request.build_absolute_uri(
        reverse('verify_email', kwargs={'token': token})
    )

    subject = 'Ative sua conta na LUNDERON'
    message = f'''
Olá {user.username},

Seu cadastro foi realizado com sucesso! Falta apenas um passo para você começar a criar vídeos incríveis.

Clique no link abaixo para ativar sua conta:
{verification_url}

Este link é válido por 24 horas.

Se você não se cadastrou, por favor, ignore este e-mail.

Atenciosamente,
Equipe LUNDERON
'''
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Erro ao enviar email de verificação: {e}")
        return False


def is_token_valid(user, token, max_age_hours=24):
    """Verifica se o token de verificação é válido e não expirou."""
    # Garante que o token no usuário corresponde ao token do link
    if not user.email_verification_token or user.email_verification_token != token:
        return False

    # Verifica se o token não expirou (criado nas últimas 24 horas)
    if user.email_verification_token_created:
        expiration_time = user.email_verification_token_created + timedelta(hours=max_age_hours)
        if timezone.now() > expiration_time:
            return False # Token expirou

    return True