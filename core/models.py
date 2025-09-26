# Em core/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage
import boto3
from botocore.exceptions import ClientError
import os
import unicodedata  # <-- IMPORT MOVIDO PARA CIMA
import re          # <-- IMPORT MOVIDO PARA CIMA


# ================================================================
# STORAGE CONFIGURATION
# ================================================================
class MediaStorage(S3Boto3Storage):
    location = "media"
    file_overwrite = False


# ================================================================
# USUÁRIO CUSTOMIZADO
# ================================================================
class Usuario(AbstractUser):
    # Campos para verificação de e-mail
    email_verificado = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=64, blank=True, null=True)
    email_verification_token_created = models.DateTimeField(blank=True, null=True)
    
    email = models.EmailField(unique=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)

    plano_ativo = models.BooleanField(default=False)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)

    # Campos para teste grátis
    testes_gratis_utilizados = models.IntegerField(default=0)

    # Campo para logomarca
    logomarca = models.ImageField(
        storage=MediaStorage(),
        upload_to="logomarcas_usuarios/",
        blank=True,
        null=True,
        help_text="Logomarca para adicionar na tela final dos vídeos",
    )
    posicao_logomarca = models.CharField(
        max_length=20,
        choices=[
            ("superior_esquerdo", "Superior Esquerdo"),
            ("superior_direito", "Superior Direito"),
            ("inferior_esquerdo", "Inferior Esquerdo"),
            ("inferior_direito", "Inferior Direito"),
            ("centro", "Centro"),
        ],
        default="inferior_direito",
        blank=True,
    )

    def __str__(self):
        return self.username


# ================================================================
# FUNÇÃO AUXILIAR PARA CRIAR PASTA NO R2
# ================================================================
def criar_pasta_no_r2(caminho_pasta):
    """
    Cria uma pasta (objeto vazio) no Cloudflare R2
    """
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        s3_client.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=f"{caminho_pasta}/",
            Body=b"",
        )
        return True
    except ClientError as e:
        print(f"Erro ao criar pasta no R2: {e}")
        return False


# ================================================================
# MODELOS ABSTRATOS PARA EVITAR REPETIÇÃO DE CÓDIGO
# ================================================================
class BaseCategoria(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    pasta = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Nome da pasta no Cloudflare R2 (gerado automaticamente se deixado em branco).",
    )

    class Meta:
        abstract = True # Define este modelo como abstrato

    def save(self, *args, **kwargs):
        if not self.pasta:
            nome_normalizado = (
                unicodedata.normalize("NFKD", self.nome)
                .encode("ASCII", "ignore")
                .decode("ASCII")
            )
            self.pasta = re.sub(r"[^a-zA-Z0-9_]", "_", nome_normalizado).lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome

# ================================================================
# CATEGORIAS (AGORA USANDO O MODELO ABSTRATO)
# ================================================================
class CategoriaVideo(BaseCategoria):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs) # Chama o save da classe Base
        caminho_pasta_videos = f"media/videos_base/{self.pasta}"
        criar_pasta_no_r2(caminho_pasta_videos)

class CategoriaMusica(BaseCategoria):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs) # Chama o save da classe Base
        caminho_pasta_musicas = f"media/musicas_base/{self.pasta}"
        criar_pasta_no_r2(caminho_pasta_musicas)


# ================================================================
# FUNÇÕES PARA UPLOAD DINÂMICO
# ================================================================
def upload_video_para_categoria(instance, filename):
    return f"videos_base/{instance.categoria.pasta}/{filename}"

def upload_musica_para_categoria(instance, filename):
    return f"musicas_base/{instance.categoria.pasta}/{filename}"


# ================================================================
# MÍDIA BASE (USANDO UM MODELO ABSTRATO)
# ================================================================
class BaseMedia(models.Model):
    titulo = models.CharField(max_length=200)
    object_key = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.titulo

class VideoBase(BaseMedia):
    categoria = models.ForeignKey(CategoriaVideo, on_delete=models.PROTECT)
    arquivo_video = models.FileField(
        storage=MediaStorage(),
        upload_to=upload_video_para_categoria,
        blank=True,
        null=True,
    )

    def save(self, *args, **kwargs):
        if self.arquivo_video:
            nome_arquivo = os.path.basename(self.arquivo_video.name)
            self.object_key = f"media/videos_base/{self.categoria.pasta}/{nome_arquivo}"
        super().save(*args, **kwargs)

    @property
    def video_url(self):
        return self.arquivo_video.url if self.arquivo_video else None

class MusicaBase(BaseMedia):
    categoria = models.ForeignKey(CategoriaMusica, on_delete=models.PROTECT)
    arquivo_musica = models.FileField(
        storage=MediaStorage(),
        upload_to=upload_musica_para_categoria,
        blank=True,
        null=True,
    )

    def save(self, *args, **kwargs):
        if self.arquivo_musica:
            nome_arquivo = os.path.basename(self.arquivo_musica.name)
            self.object_key = f"media/musicas_base/{self.categoria.pasta}/{nome_arquivo}"
        super().save(*args, **kwargs)

    @property
    def musica_url(self):
        return self.arquivo_musica.url if self.arquivo_musica else None


# ================================================================
# VÍDEOS GERADOS (SEM ALTERAÇÕES NECESSÁRIAS)
# ================================================================
class VideoGerado(models.Model):
    STATUS_CHOICES = [
        ("PROCESSANDO", "Processando"),
        ("CONCLUIDO", "Concluído"),
        ("ERRO", "Erro"),
    ]
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PROCESSANDO")
    arquivo_final = models.CharField(max_length=500, blank=True, null=True, help_text="Caminho do vídeo gerado (local ou R2)")
    criado_em = models.DateTimeField(auto_now_add=True)
    duracao_segundos = models.IntegerField(blank=True, null=True)
    loop = models.BooleanField(default=False)
    plano_de_fundo = models.CharField(max_length=10, default="normal")
    volume_musica = models.IntegerField(default=70)
    texto_overlay = models.TextField(blank=True, null=True)
    narrador_texto = models.TextField(blank=True, null=True)
    texto_tela_final = models.TextField(blank=True, null=True)
    posicao_texto = models.CharField(max_length=10, default="centro")
    cor_da_fonte = models.CharField(max_length=7, default="#FFFFFF")
    texto_fonte = models.CharField(max_length=50, default="arial")
    texto_tamanho = models.IntegerField(default=50)
    texto_negrito = models.BooleanField(default=False)
    texto_sublinhado = models.BooleanField(default=False)
    legenda_sincronizada = models.BooleanField(default=False)
    narrador_voz = models.CharField(max_length=50, default="pt-BR-Wavenet-B")
    narrador_velocidade = models.IntegerField(default=100)
    narrador_tom = models.FloatField(default=0.0)
    caminho_audio_narrador = models.CharField(max_length=500, blank=True, null=True, help_text="Caminho do áudio de narração gerado")
    caminho_legenda_ass = models.CharField(max_length=500, blank=True, null=True, help_text="Caminho da legenda ASS gerada")
    caminho_imagem_texto = models.CharField(max_length=500, blank=True, null=True, help_text="Caminho da imagem de texto gerada")

    def __str__(self):
        return f"Vídeo de {self.usuario.username} - {self.status}"


# ================================================================
# PLANOS E ASSINATURAS (COM CORREÇÃO NO MODELO 'Plano')
# ================================================================
class Plano(models.Model):
    nome = models.CharField(max_length=100)
    preco = models.DecimalField(max_digits=6, decimal_places=2)
    descricao = models.TextField(blank=True, null=True)
    
    # --- CAMPOS DA NOVA ESTRUTURA ---
    limite_videos_mensal = models.IntegerField(default=30, help_text="Quantos vídeos o assinante deste plano pode gerar por mês.")
    link_pdf_dicas = models.URLField(max_length=500, blank=True, null=True, help_text="Link para o PDF de dicas (apenas para o plano Pro).")
    
    # --- CORREÇÃO ADICIONADA AQUI ---
    stripe_price_id = models.CharField(max_length=255, blank=True, null=True, help_text="ID do Preço deste plano no Stripe (ex: price_123abc...)")

    def __str__(self):
        return self.nome


class Assinatura(models.Model):
    STATUS_CHOICES = [("ativo", "Ativo"), ("pendente", "Pendente"), ("cancelado", "Cancelado")]
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    plano = models.ForeignKey(Plano, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pendente")
    data_inicio = models.DateTimeField(auto_now_add=True)
    data_expiracao = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.plano.nome} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.status == "ativo":
            self.usuario.plano_ativo = True
        else:
            self.usuario.plano_ativo = False
        self.usuario.save(update_fields=["plano_ativo"])


# ================================================================
# CONFIGURAÇÕES GERAIS DO SITE (SEM ALTERAÇÕES)
# ================================================================
class Configuracao(models.Model):
    nome = models.CharField(max_length=100)
    valor = models.CharField(max_length=255)

    def __str__(self):
        return self.nome


# ================================================================
# PAGAMENTOS (SEM ALTERAÇÕES)
# ================================================================
class Pagamento(models.Model):
    STATUS_CHOICES = [("pendente", "Pendente"), ("aprovado", "Aprovado"), ("recusado", "Recusado")]
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    plano = models.ForeignKey("Plano", on_delete=models.CASCADE)
    valor = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pendente")
    data_pagamento = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.plano.nome} ({self.status})"