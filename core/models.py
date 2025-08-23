from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models

# ================================================================
# USUÁRIO CUSTOMIZADO
# ================================================================
class Usuario(AbstractUser):
    email = models.EmailField(unique=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)

    plano_ativo = models.BooleanField(default=False)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.username


# ================================================================
# CATEGORIAS E MÍDIA BASE
# ================================================================
class CategoriaVideo(models.Model):
    nome = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nome


class CategoriaMusica(models.Model):
    nome = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nome


class VideoBase(models.Model):
    titulo = models.CharField(max_length=200)
    categoria = models.ForeignKey(CategoriaVideo, on_delete=models.PROTECT)
    arquivo_video = models.FileField(upload_to='videos_base/')

    def __str__(self):
        return self.titulo


class MusicaBase(models.Model):
    titulo = models.CharField(max_length=200)
    categoria = models.ForeignKey(CategoriaMusica, on_delete=models.PROTECT)
    arquivo_musica = models.FileField(upload_to='musicas_base/')

    def __str__(self):
        return self.titulo


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
        # Melhoria: Usar get_status_display() para mostrar o rótulo amigável (ex: "Ativo" em vez de "ativo")
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

    def __str__(self):
        return f"{self.usuario.username} - {self.plano.nome} ({self.status})"


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

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plano = models.ForeignKey('Plano', on_delete=models.CASCADE)  # 'Plano' se estiver no mesmo app
    valor = models.DecimalField(max_digits=8, decimal_places=2)  # permite valores até 999,999.99
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pendente')
    data_pagamento = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.plano.nome} ({self.status})"