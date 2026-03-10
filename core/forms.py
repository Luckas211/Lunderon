from django import forms
from django.forms import formset_factory
from django.contrib.auth.forms import UserCreationForm
from .models import Usuario, CategoriaVideo, CategoriaMusica, Plano, Assinatura, Configuracao
import os

# ================================================================
# FORMULÁRIOS DE USUÁRIO E ADMIN
# ================================================================

VOZES_KOKORO = [
    # --- Vozes Exclusivas (Misturadas) ---
    ('br_imperador',   '👑 Imperador (Grave/Épico - Dark)'),
    ('br_jornalista', '📰 Jornalista (Sério - News)'),
    ('br_influencer', '🤳 Influencer (Animada - TikTok)'),
    ('br_podcast',    '🎙️ Podcast (Suave - Relaxante)'),

    # --- Vozes Padrão (Originais) ---
    ('pf_dora',       '👩 Dora (Padrão Feminino)'),
    ('pm_alex',       '👨 Alex (Padrão Masculino)'),
    ('pm_santa',      '🎅 Santa (Extra Grave)'),
]

VELOCIDADE_NARRACAO = [
    ('85', 'Lenta'),
    ('100', 'Normal'),
    ('115', 'Rápida'),
]

CONFIG_CHOICES = [
    ('DURACAO_ASSINATURA_DIAS', 'Duração da Assinatura (em dias)'),
    ('LIMITE_TESTES_GRATIS', 'Limite de Testes Grátis para Novos Usuários'),
]

class ConfiguracaoForm(forms.ModelForm):
    nome = forms.ChoiceField(
        choices=CONFIG_CHOICES,
        label="Nome da Chave de Configuração",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Configuracao
        fields = ['nome', 'valor']
        labels = {'valor': 'Valor'}
        widgets = {
            'valor': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 100'}),
        }

class EditarConfiguracaoForm(forms.ModelForm):
    class Meta:
        model = Configuracao
        fields = ['nome', 'valor']
        labels = {
            'nome': 'Nome da Configuração (Chave)',
            'valor': 'Valor da Configuração',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-input', 'readonly': True}),
            'valor': forms.TextInput(attrs={'class': 'form-input'}),
        }
        
class CadastroUsuarioForm(UserCreationForm):
    email = forms.EmailField(required=True)
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("username", "email")

class AdminUsuarioForm(forms.Form):
    username = forms.CharField(
        label="Nome de Usuário",
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        label="Email de Cadastro",
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    is_staff = forms.BooleanField(
        label="É um administrador?",
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    plano = forms.ModelChoiceField(
        queryset=Plano.objects.all(),
        label="Plano da Assinatura",
        required=False,
        empty_label="-- Sem Plano --",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    status = forms.ChoiceField(
        choices=Assinatura.STATUS_CHOICES,
        label="Status da Assinatura",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

class EditarPerfilForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'email', 'data_nascimento']
        labels = {
            'first_name': 'Nome',
            'last_name': 'Sobrenome',
            'email': 'Email de Cadastro',
            'data_nascimento': 'Data de Nascimento',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Seu primeiro nome'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Seu sobrenome'}),
            'email': forms.EmailInput(attrs={'placeholder': 'seu.email@exemplo.com'}),
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}),
        }

class EditarAssinaturaForm(forms.ModelForm):
    class Meta:
        model = Assinatura
        fields = ['plano', 'status']
        labels = {
            'plano': 'Mudar para o Plano',
            'status': 'Mudar Status da Assinatura',
        }
        widgets = {
            'plano': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

# ================================================================
# FORMULÁRIO DO GERADOR DE VÍDEO (ATUALIZADO)
# ================================================================

COR_FONTE_CHOICES = [
    ('#FFFFFF', 'Branco'),
    ('#FFFF00', 'Amarelo'),
    ('#000000', 'Preto'),
    ('#FF0000', 'Vermelho'),
    ('#00FF00', 'Verde Limão'),
    ('#00FFFF', 'Ciano (Azul Claro)'),
    ('#FF69B4', 'Rosa Choque'),
]

FONTES_TEXTO = [
    ('arial', 'Arial'),
    ('times', 'Times New Roman'),
    ('courier', 'Courier New'),
    ('impact', 'Impact'),
    ('verdana', 'Verdana'),
    ('georgia', 'Georgia'),
    ('alfa_slab_one', 'Alfa Slab One (Impacto)'),
]

TIPO_CONTEUDO_CHOICES = [
    ('narrador', 'Narração (Duração Automática)'),
    ('texto', 'Texto Estático (Duração Manual)'),
    ('vendedor', 'Vendedor (Upload de Vídeo)'),
]

POSICAO_TEXTO_CHOICES = [
    ('centro', 'Centro da Tela'),
    ('inferior', 'Parte Inferior (Estilo Legenda)'),
]

# --- NOVAS OPÇÕES DE VISUAL DUAL ---
TIPO_VISUAL_IA_CHOICES = [
    ('imagem', 'Imagens Animadas (IA Flux + Movimento)'),
    ('video', 'Vídeos Reais (Cinematográficos - Pexels)')
]

class GeradorForm(forms.Form):
    # 1. TIPO DE CONTEÚDO
    tipo_conteudo = forms.ChoiceField(
        choices=TIPO_CONTEUDO_CHOICES,
        label="Tipo de Conteúdo",
        widget=forms.RadioSelect,
        initial='narrador'
    )

    # 2. CONTEÚDO E ESTILO
    texto_overlay = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'maxlength': '250'}),
        required=False,
        label="Texto Estático"
    )
    narrador_texto = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label="Texto para Narração"
    )
    posicao_texto = forms.ChoiceField(
        choices=POSICAO_TEXTO_CHOICES,
        label="Posição do Texto",
        widget=forms.RadioSelect,
        initial='centro',
        required=False
    )
    cor_da_fonte = forms.ChoiceField(
        choices=COR_FONTE_CHOICES,
        label="Cor da Fonte",
        initial='#FFFFFF',
        required=False
    )
    cor_destaque_legenda = forms.ChoiceField(
        choices=COR_FONTE_CHOICES,
        label="Cor de Destaque (Karaokê)",
        initial='#FFFF00',
        required=False
    )
    texto_fonte = forms.ChoiceField(
        choices=FONTES_TEXTO,
        required=False,
        label="Tipo de Letra"
    )
    texto_tamanho = forms.TypedChoiceField(
        choices=[(10, '10'), (20, '20'), (30, '30'), (35, '35')],
        coerce=int,
        initial=20,
        required=False,
        label="Tamanho da Letra"
    )
    texto_negrito = forms.BooleanField(required=False, label="Negrito")
    texto_sublinhado = forms.BooleanField(required=False, label="Sublinhado")

    # 3. NARRAÇÃO
    legenda_sincronizada = forms.BooleanField(
        label='Ativar Legenda Sincronizada',
        required=False,
        initial=True
    )
    narrador_voz = forms.ChoiceField(
        choices=VOZES_KOKORO,
        required=False,
        label="Voz do Narrador"
    )
    narrador_velocidade = forms.TypedChoiceField(
        choices=VELOCIDADE_NARRACAO,
        coerce=int,
        initial=100,
        required=False,
        label="Velocidade da Narração"
    )

    # 4. FUNDO DINÂMICO (IA / PEXELS)
    gerar_fundo_ia = forms.BooleanField(
        required=False,
        label="Gerar Fundo Dinâmico com IA"
    )
    
    # --- NOVO CAMPO DE FORMATO IA ---
    tipo_visual_ia = forms.ChoiceField(
        choices=TIPO_VISUAL_IA_CHOICES,
        initial='imagem',
        widget=forms.RadioSelect,
        label="Formato do Fundo Dinâmico",
        required=False,
        help_text="Imagens usam IA para criar a cena. Vídeos buscam filmagens reais."
    )
    # --------------------------------

    categoria_video = forms.ModelChoiceField(
        queryset=CategoriaVideo.objects.all(),
        label="Categoria do Vídeo (Manual)",
        required=False
    )
    video_base_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    categoria_musica = forms.ModelChoiceField(
        queryset=CategoriaMusica.objects.all(),
        required=False
    )
    video_upload = forms.FileField(
        label="Upload do Vídeo (Produto)",
        required=False
    )
    volume_musica = forms.TypedChoiceField(
        choices=[(0, 'Sem Som'), (25, 'Baixo'), (50, 'Médio'), (75, 'Alto'), (100, 'Máximo')],
        coerce=int,
        initial=50,
        label="Volume da Música",
    )
    loop_video = forms.BooleanField(
        required=False,
        label="Repetir vídeo (loop)?",
        initial=True
    )
    duracao_segundos = forms.IntegerField(
        min_value=10,
        max_value=120, # Aumentado para suportar vídeos mais longos
        initial=30,
        label="Duração (segundos)",
        required=False
    )
    texto_tela_final = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Texto da Tela Final"
    )

    def clean(self):
        cleaned_data = super().clean()
        tipo_conteudo = cleaned_data.get('tipo_conteudo')
        gerar_fundo_ia = cleaned_data.get('gerar_fundo_ia')
        categoria_video = cleaned_data.get('categoria_video')
        video_upload = cleaned_data.get('video_upload')
        narrador_texto = cleaned_data.get('narrador_texto')
        texto_overlay = cleaned_data.get('texto_overlay')

        # Validação de Fundo: Se não for IA, precisa de categoria ou upload
        if tipo_conteudo == 'narrador' and not gerar_fundo_ia and not categoria_video:
            self.add_error('categoria_video', "Selecione uma categoria de vídeo ou ative o Fundo Dinâmico com IA.")

        if tipo_conteudo == 'vendedor' and not video_upload:
            self.add_error('video_upload', "Para o modo Vendedor, o upload do vídeo é obrigatório.")

        if (tipo_conteudo == 'narrador' or tipo_conteudo == 'vendedor') and not narrador_texto:
            self.add_error('narrador_texto', "O texto para narração é obrigatório neste modo.")

        if tipo_conteudo == 'texto' and not texto_overlay:
            self.add_error('texto_overlay', "O texto estático é obrigatório neste modo.")

        return cleaned_data

# ================================================================
# FORMULÁRIO DE CORTES DO YOUTUBE
# ================================================================
class CortesYouTubeForm(forms.Form):
    youtube_url = forms.URLField(
        label="URL do Vídeo do YouTube",
        widget=forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://www.youtube.com/watch?v=...'}),
        required=True
    )
    categoria_musica = forms.ModelChoiceField(
        queryset=CategoriaMusica.objects.all(),
        label="Categoria da Música de Fundo",
        required=True
    )
    volume_musica = forms.IntegerField(
        min_value=0,
        max_value=100,
        initial=20,
        label="Volume da Música de Fundo",
        help_text="Ajuste o volume da música para não sobrepor o áudio original do vídeo."
    )
    gerar_legendas = forms.BooleanField(
        label="Gerar Legendas (transcrição automática)",
        required=False,
        help_text="Ativa a transcrição automática do áudio do vídeo para legendas."
    )
    segments = forms.CharField(widget=forms.HiddenInput(), required=True)