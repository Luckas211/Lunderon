# Em core/utils.py

import secrets
import string
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse

# Imports para as funções R2
import boto3
from botocore.exceptions import ClientError
import requests
import tempfile


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

# ===============================================================
# FUNÇÕES DE UTILIDADE PARA CLOUDFLARE R2
# ===============================================================

def verificar_arquivo_existe_no_r2(object_key):
    """
    Verifica se um arquivo realmente existe no Cloudflare R2 antes de tentar baixar
    """
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )

        # Tenta obter os metadados do objeto
        s3_client.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=object_key)
        return True
    except ClientError as e:
        error_code = e.response["Error"].get("Code", "Unknown")
        if error_code == "404":
            print(f"Arquivo não encontrado no R2: {object_key}")
            return False
        else:
            print(f"Erro ao verificar arquivo no R2 {object_key}: {e}")
            return False
    except Exception as e:
        print(f"Erro inesperado ao verificar arquivo no R2 {object_key}: {e}")
        return False


def generate_presigned_url(object_key, expiration=3600):
    """
    Gera uma URL assinada temporária para um objeto no Cloudflare R2
    """
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )

        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": object_key},
            ExpiresIn=expiration,
        )
        return url
    except ClientError as e:
        print(f"Erro ao gerar URL assinada: {e}")
        return None


def download_from_cloudflare(url_or_key, extension):
    """
    Faz download de um arquivo do Cloudflare R2
    Suporta tanto URLs públicas quanto chaves de objeto (para URLs assinadas)
    """
    try:
        # Verificar se o parâmetro é válido
        if not url_or_key:
            print(f"Erro: url_or_key é None ou vazio")
            return None

        # Se for uma chave de objeto (não uma URL completa), gera URL assinada
        if not url_or_key.startswith("http"):
            download_url = generate_presigned_url(url_or_key)
        else:
            download_url = url_or_key

        if not download_url:
            print(f"Erro: não foi possível gerar URL de download para {url_or_key}")
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(download_url, stream=True, headers=headers)
        response.raise_for_status()

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=extension)

        with open(temp_file.name, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return temp_file.name
    except Exception as e:
        print(f"Erro ao baixar {url_or_key}: {e}")
        return None


def upload_to_r2(caminho_arquivo_local, object_key):
    """
    Faz o upload de um arquivo para o bucket R2 principal.
    """
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        s3_client.upload_file(
            caminho_arquivo_local, settings.AWS_STORAGE_BUCKET_NAME, object_key
        )
        return True
    except ClientError as e:
        print(f"Erro no upload para o R2: {e}")
        return False


def upload_fileobj_to_r2(file_obj, object_key):
    """
    Faz o upload de um objeto tipo arquivo (stream) para o bucket R2 principal.
    """
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        s3_client.upload_fileobj(file_obj, settings.AWS_STORAGE_BUCKET_NAME, object_key)
        return True
    except ClientError as e:
        print(f"Erro no upload de stream para o R2: {e}")
        return False


def delete_from_r2(object_key):
    """
    Apaga um arquivo do bucket R2 principal.
    """
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        s3_client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=object_key)
        return True
    except ClientError as e:
        print(f"Erro ao apagar do R2: {e}")
        return False
