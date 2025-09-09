from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models
from storages.backends.s3boto3 import S3Boto3Storage
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
import os
import unicodedata
import re

# ================================================================
# USUÁRIO CUSTOMIZADO
# ================================================================
class Usuario(AbstractUser):
    email = models.EmailField(unique=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)

    plano_ativo = models.BooleanField(default=False)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)

    def __str__(self):
        return self.username




#-----------------------------Cloudflare e admin
def criar_pasta_no_r2(caminho_pasta):
    """
    Cria uma pasta (objeto vazio) no Cloudflare R2
    """
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        
        # Cria um objeto vazio para simular uma pasta
        s3_client.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=f"{caminho_pasta}/",  # A barra no final indica que é uma pasta
            Body=b'',
            ContentLength=0
        )
        return True
    except ClientError as e:
        print(f"Erro ao criar pasta no R2: {e}")
        return False



# ================================================================
# CATEGORIAS MODIFICADAS - COM PASTAS AUTOMÁTICAS
# ================================================================
class CategoriaVideo(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    pasta = models.CharField(max_length=100, blank=True, null=True, help_text="Nome da pasta no Cloudflare R2")

    def save(self, *args, **kwargs):
        # Gera o nome da pasta se não existir
        if not self.pasta:
            # Remove acentos e caracteres especiais, converte para minúsculas
            import unicodedata
            import re
            nome_normalizado = unicodedata.normalize('NFKD', self.nome).encode('ASCII', 'ignore').decode('ASCII')
            self.pasta = re.sub(r'[^a-zA-Z0-9_]', '_', nome_normalizado).lower()
        
        # Chama o save original primeiro
        super().save(*args, **kwargs)
        
        # Cria a pasta no Cloudflare R2 após salvar
        caminho_pasta_videos = f"media/videos_base/{self.pasta}"
        criar_pasta_no_r2(caminho_pasta_videos)

    def __str__(self):
        return self.nome

class CategoriaMusica(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    pasta = models.CharField(max_length=100, blank=True, null=True, help_text="Nome da pasta no Cloudflare R2")

    def save(self, *args, **kwargs):
        # Gera o nome da pasta se não existir
        if not self.pasta:
            import unicodedata
            import re
            nome_normalizado = unicodedata.normalize('NFKD', self.nome).encode('ASCII', 'ignore').decode('ASCII')
            self.pasta = re.sub(r'[^a-zA-Z0-9_]', '_', nome_normalizado).lower()
        
        super().save(*args, **kwargs)
        
        # Cria a pasta no Cloudflare R2
        caminho_pasta_musicas = f"media/musicas_base/{self.pasta}"
        criar_pasta_no_r2(caminho_pasta_musicas)

    def __str__(self):
        return self.nome

# ================================================================
# STORAGE CONFIGURATION (mantém igual)
# ================================================================
class MediaStorage(S3Boto3Storage):
    location = 'media'
    file_overwrite = False




# ================================================================
# FUNÇÕES PARA UPLOAD DINÂMICO
# ================================================================
def upload_video_para_categoria(instance, filename):
    """
    Retorna o caminho dinâmico para upload de vídeos baseado na categoria
    Ex: 'videos_base/news/filename.mp4'
    """
    if instance.categoria and instance.categoria.pasta:
        return f'videos_base/{instance.categoria.pasta}/{filename}'
    return f'videos_base/{filename}'

def upload_musica_para_categoria(instance, filename):
    """
    Retorna o caminho dinâmico para upload de músicas baseado na categoria
    Ex: 'musicas_base/instrumental/filename.mp3'
    """
    if instance.categoria and instance.categoria.pasta:
        return f'musicas_base/{instance.categoria.pasta}/{filename}'
    return f'musicas_base/{filename}'
# ================================================================
# MÍDIA BASE MODIFICADA - UPLOAD DINÂMICO
# ================================================================
class VideoBase(models.Model):
    titulo = models.CharField(max_length=200)
    categoria = models.ForeignKey(CategoriaVideo, on_delete=models.PROTECT)
    arquivo_video = models.FileField(
        storage=MediaStorage(),
        upload_to=upload_video_para_categoria,  # AGORA É DINÂMICO!
        blank=True, 
        null=True
    )
    
    object_key = models.CharField(max_length=500, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.arquivo_video:
            # CORREÇÃO: Usa a pasta da categoria no object_key
            nome_arquivo = os.path.basename(self.arquivo_video.name)
            self.object_key = f'media/videos_base/{self.categoria.pasta}/{nome_arquivo}'
        super().save(*args, **kwargs)
    
    @property
    def video_url(self):
        if self.arquivo_video:
            return self.arquivo_video.url
        return None

    def __str__(self):
        return self.titulo

class MusicaBase(models.Model):
    titulo = models.CharField(max_length=200)
    categoria = models.ForeignKey(CategoriaMusica, on_delete=models.PROTECT)
    arquivo_musica = models.FileField(
        storage=MediaStorage(),
        upload_to=upload_musica_para_categoria,  # AGORA É DINÂMICO!
        blank=True, 
        null=True
    )

    object_key = models.CharField(max_length=500, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.arquivo_musica:
            # CORREÇÃO: Usa a pasta da categoria no object_key
            nome_arquivo = os.path.basename(self.arquivo_musica.name)
            self.object_key = f'media/musicas_base/{self.categoria.pasta}/{nome_arquivo}'
        super().save(*args, **kwargs)
    
    @property
    def musica_url(self):
        if self.arquivo_musica:
            return self.arquivo_musica.url
        return None

    def __str__(self):
        return self.titulo

# ================================================================
# RESTANTE DOS MODELOS (mantém igual)
# ================================================================

# ================================================================
# VÍDEOS GERADOS
# ================================================================
class VideoGerado(models.Model):
    STATUS_CHOICES = [
        ('PROCESSANDO', 'Processando'),
        ('CONCLUIDO', 'Concluído'),
        ('ERRO', 'Erro')
    ]

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROCESSANDO')
    arquivo_final = models.FileField(upload_to='videos_gerados/', blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    duracao_segundos = models.IntegerField(default=30)
    loop = models.BooleanField(default=False)
    plano_de_fundo = models.CharField(max_length=10, default='normal')
    volume_musica = models.IntegerField(default=70)

    texto_overlay = models.TextField(blank=True, null=True)
    narrador_texto = models.TextField(blank=True, null=True)
    texto_tela_final = models.TextField(blank=True, null=True)

    posicao_texto = models.CharField(max_length=10, default='centro')
    cor_da_fonte = models.CharField(max_length=7, default='#FFFFFF')
    texto_fonte = models.CharField(max_length=50, default='arial')
    texto_tamanho = models.IntegerField(default=50)
    texto_negrito = models.BooleanField(default=False)
    texto_sublinhado = models.BooleanField(default=False)

    legenda_sincronizada = models.BooleanField(default=False)
    narrador_voz = models.CharField(max_length=50, default='pt-BR-Wavenet-B')
    narrador_velocidade = models.IntegerField(default=100)
    narrador_tom = models.FloatField(default=0.0)

    def __str__(self):
        return f"Vídeo de {self.usuario.username} - {self.status}"


# ================================================================
# PLANOS E ASSINATURAS
# ================================================================
class Plano(models.Model):
    nome = models.CharField(max_length=100)
    preco = models.DecimalField(max_digits=6, decimal_places=2)
    descricao = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nome


class Assinatura(models.Model):
    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('pendente', 'Pendente'),
        ('cancelado', 'Cancelado'),
    ]

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    plano = models.ForeignKey(Plano, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pendente')
    data_inicio = models.DateTimeField(auto_now_add=True)
    data_expiracao = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.plano.nome} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        """
        Sobrescreve o método save para sincronizar o status do usuário com a assinatura.
        """
        # Primeiro, salva a própria assinatura
        super().save(*args, **kwargs)

        # Agora, atualiza o status do usuário com base no status da assinatura
        if self.status == 'ativo':
            self.usuario.plano_ativo = True
        else:
            # Para qualquer outro status (pendente, cancelado), o plano não está ativo.
            self.usuario.plano_ativo = False
        
        # Salva o usuário, atualizando apenas o campo necessário para maior eficiência.
        self.usuario.save(update_fields=['plano_ativo'])


# ================================================================
# CONFIGURAÇÕES GERAIS DO SITE
# ================================================================
class Configuracao(models.Model):
    nome = models.CharField(max_length=100)
    valor = models.CharField(max_length=255)

    def __str__(self):
        return self.nome


# ================================================================
# PAGAMENTOS
# ================================================================
class Pagamento(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('recusado', 'Recusado'),
    ]

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    plano = models.ForeignKey('Plano', on_delete=models.CASCADE)
    valor = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pendente')
    data_pagamento = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.plano.nome} ({self.status})"