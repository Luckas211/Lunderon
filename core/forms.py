from django import forms
from django.forms import formset_factory
from django.contrib.auth.forms import UserCreationForm
from .models import Usuario, CategoriaVideo, CategoriaMusica, Plano, Assinatura, Configuracao

# ================================================================
# FORMULÁRIOS DE USUÁRIO E ADMIN
# ================================================================
# Definindo as vozes do Kokoro primeiro para evitar duplicação
# Definindo as vozes do Kokoro para português brasileiro
VOZES_KOKORO = [
    ('pf_dora', 'Feminina - Dora'),
    ('pm_alex', 'Masculina - Alex'),
    ('pm_santa', 'Masculina - Santa'),
]

# Opções de velocidade para a narração
VELOCIDADE_NARRACAO = [
    (80, 'Lenta (80%)'),
    (90, 'Um pouco lenta (90%)'),
    (100, 'Normal (100%)'),
    (110, 'Um pouco rápida (110%)'),
    (120, 'Rápida (120%)'),
]

# --- CORREÇÃO APLICADA AQUI ---
# A opção 'LIMITE_VIDEOS_MES' foi removida pois o limite agora é definido por plano.
CONFIG_CHOICES = [
    ('DURACAO_ASSINATURA_DIAS', 'Duração da Assinatura (em dias)'),
    ('LIMITE_TESTES_GRATIS', 'Limite de Testes Grátis para Novos Usuários'),
]

class ConfiguracaoForm(forms.ModelForm):
    """
    Formulário para ADICIONAR uma nova configuração.
    O campo 'nome' é um dropdown para evitar erros de digitação.
    """
    nome = forms.ChoiceField(
        choices=CONFIG_CHOICES,
        label="Nome da Chave de Configuração",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Configuracao
        fields = ['nome', 'valor']
        labels = {
            'valor': 'Valor',
        }
        widgets = {
            'valor': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 100'}),
        }

class EditarConfiguracaoForm(forms.ModelForm):
    """
    Formulário para EDITAR uma configuração existente.
    O campo 'nome' é somente leitura para impedir a alteração da chave.
    """
    class Meta:
        model = Configuracao
        fields = ['nome', 'valor']
        labels = {
            'nome': 'Nome da Configuração (Chave)',
            'valor': 'Valor da Configuração',
        }
        widgets = {
            # Torna o campo 'nome' não editável
            'nome': forms.TextInput(attrs={'class': 'form-input', 'readonly': True}),
            'valor': forms.TextInput(attrs={'class': 'form-input'}),
        }
class CadastroUsuarioForm(UserCreationForm):
    email = forms.EmailField(required=True)
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("username", "email")

class AdminUsuarioForm(forms.Form):
    """
    Um formulário customizado para o admin editar dados do usuário e sua assinatura.
    """
    # Campos do modelo Usuario
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
        label="É um administrador? (Pode acessar o painel)",
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    # Campos do modelo Assinatura
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
    """
    Formulário para o usuário editar suas próprias informações.
    """
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
# FORMULÁRIO DO GERADOR DE VÍDEO
# ================================================================

# --- Listas de Opções (Choices) ---
COR_FONTE_CHOICES = [
    ('#FFFFFF', 'Branco'),
    ('#FFFF00', 'Amarelo'),
    ('#000000', 'Preto'),
    ('#FF0000', 'Vermelho'),
    ('#00FF00', 'Verde Limão'),
    ('#00FFFF', 'Ciano (Azul Claro)'),
    ('#FF69B4', 'Rosa Choque'),
]

TONS_VOZ = [(2.0, 'Agudo'), (0.0, 'Normal'), (-2.0, 'Grave')]
PLANO_DE_FUNDO_CHOICES = [('normal', 'Normal / Escuro'), ('claro', 'Claro')]

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

# --- Classe do Formulário do Gerador ---
class GeradorForm(forms.Form):
    # 1. TIPO DE CONTEÚDO
    tipo_conteudo = forms.ChoiceField(
        choices=TIPO_CONTEUDO_CHOICES,
        label="Tipo de Conteúdo de Texto",
        widget=forms.RadioSelect,
        initial='narrador'
    )

    # 2. CONTEÚDO E ESTILO DO TEXTO
    texto_overlay = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
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
        label="Cor de Destaque da Legenda (Karaokê)",
        initial='#FFFF00',
        required=False,
        help_text="A cor que a palavra assume quando é falada."
    )
    texto_fonte = forms.ChoiceField(
        choices=FONTES_TEXTO,
        required=False,
        label="Tipo de Letra"
    )
    texto_tamanho = forms.IntegerField(
        min_value=20,
        max_value=100,
        initial=70,
        required=False,
        label="Tamanho da Letra"
    )
    texto_negrito = forms.BooleanField(required=False, label="Negrito")
    texto_sublinhado = forms.BooleanField(required=False, label="Sublinhado")

    # 3. OPÇÕES DE NARRAÇÃO
    legenda_sincronizada = forms.BooleanField(
        label='Ativar Legenda Sincronizada',
        required=False,
        help_text=(
            "Aumente o engajamento exibindo o que está sendo narrado. "
            "Ativada: O vídeo terá a narração e também legendas dinâmicas na tela. "
            "Desativada: O vídeo terá apenas a narração, sem texto. "
            "Atenção: A sincronia da legenda com a voz é uma estimativa."
        )
    )

    narrador_voz = forms.ChoiceField(
        choices=VOZES_KOKORO,
        required=False,
        label="Voz do Narrador"
    )
    narrador_velocidade = forms.ChoiceField(
        choices=VELOCIDADE_NARRACAO,
        initial=100,
        required=False,
        label="Velocidade da Narração"
    )

    # 4. MÍDIA DE FUNDO E DURAÇÃO
    categoria_video = forms.ModelChoiceField(
        queryset=CategoriaVideo.objects.all(),
        label="Categoria do Vídeo",
        required=False
    )
    categoria_musica = forms.ModelChoiceField(
        queryset=CategoriaMusica.objects.all(),
        label="Categoria da Música",
        required=False
    )
    video_upload = forms.FileField(
        label="Upload do Vídeo do Produto",
        required=False,
        help_text="Selecione um vídeo local do seu produto (MP4, AVI, MOV, etc.)"
    )
    volume_musica = forms.IntegerField(
        min_value=0,
        max_value=100,
        initial=50,
        label="Volume da Música (%)",
    )
    loop_video = forms.BooleanField(
        required=False,
        label="Repetir o vídeo (loop)?",
        initial=True,
        help_text="O vídeo de fundo ficará em loop durante toda a narração"
    )
    duracao_segundos = forms.IntegerField(
        min_value=10,
        max_value=60,
        initial=30,
        label="Duração (segundos)",
        required=False,
        help_text="Apenas para Texto Estático."
    )

    # --- CAMPO DE TELA FINAL ATUALIZADO PARA TEXTO ---
    texto_tela_final = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Texto da Tela de Encerramento (Opcional)",
        help_text="Ex: Siga e compartilhe!"
    )

    def clean(self):
        cleaned_data = super().clean()
        tipo_conteudo = cleaned_data.get('tipo_conteudo')
        categoria_video = cleaned_data.get('categoria_video')
        video_upload = cleaned_data.get('video_upload')
        texto_overlay = cleaned_data.get('texto_overlay')
        narrador_texto = cleaned_data.get('narrador_texto')

        if tipo_conteudo == 'vendedor':
            if not video_upload:
                raise forms.ValidationError("Para o tipo 'Vendedor', você deve fazer upload de um vídeo.")
            if not narrador_texto:
                raise forms.ValidationError("Para o tipo 'Vendedor', o texto para narração é obrigatório.")
        elif tipo_conteudo == 'narrador':
            if not categoria_video:
                raise forms.ValidationError("Para o tipo 'Narração', você deve selecionar uma categoria de vídeo.")
            if not narrador_texto:
                raise forms.ValidationError("Para o tipo 'Narração', o texto para narração é obrigatório.")
        elif tipo_conteudo == 'texto':
            if not categoria_video:
                raise forms.ValidationError("Para o tipo 'Texto Estático', você deve selecionar uma categoria de vídeo.")
            if not texto_overlay:
                raise forms.ValidationError("Para o tipo 'Texto Estático', o texto é obrigatório.")

        return cleaned_data

# Cria o FormSet a partir do formulário
#GeradorFormSet = formset_factory(GeradorForm, extra=1, max_num=3)

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
        initial=20, # Começa com um volume mais baixo por padrão
        label="Volume da Música de Fundo (%)",
        help_text="Ajuste o volume da música para não sobrepor o áudio original do vídeo."
    )
    gerar_legendas = forms.BooleanField(
        label="Gerar Legendas (transcrição automática)",
        required=False,
        help_text="Ativa a transcrição automática do áudio do vídeo para legendas."
    )
    segments = forms.CharField(widget=forms.HiddenInput(), required=True)