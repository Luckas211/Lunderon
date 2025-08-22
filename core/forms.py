from django import forms
from django.forms import formset_factory
from django.contrib.auth.forms import UserCreationForm
from .models import Usuario, CategoriaVideo, CategoriaMusica, Plano, Assinatura, Configuracao


# ================================================================
# FORMULÁRIOS DE USUÁRIO E ADMIN
# ================================================================
class EditarConfiguracaoForm(forms.ModelForm):
    class Meta:
        model = Configuracao
        fields = ['nome', 'valor']
        labels = {
            'nome': 'Nome da Configuração (Chave)',
            'valor': 'Valor da Configuração',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'valor': forms.TextInput(attrs={'class': 'form-control'}),
        }
class ConfiguracaoForm(forms.ModelForm):
    class Meta:
        model = Configuracao
        fields = ['nome', 'valor']
        labels = {
            'nome': 'Nome da Chave (ex: DURACAO_ASSINATURA_DIAS)',
            'valor': 'Valor',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'valor': forms.TextInput(attrs={'class': 'form-control'}),
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
        widget=forms.TextInput(attrs={'class': 'form-control'}) # Classe adicionada
    )
    email = forms.EmailField(
        label="Email de Cadastro",
        widget=forms.EmailInput(attrs={'class': 'form-control'}) # Classe adicionada
    )
    is_staff = forms.BooleanField(
        label="É um administrador? (Pode acessar o painel)", 
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}) # Classe adicionada
    )

    # Campos do modelo Assinatura
    plano = forms.ModelChoiceField(
        queryset=Plano.objects.all(),
        label="Plano da Assinatura",
        required=False,
        empty_label="-- Sem Plano --",
        widget=forms.Select(attrs={'class': 'form-control'}) # Classe adicionada
    )
    status = forms.ChoiceField(
        choices=Assinatura.STATUS_CHOICES,
        label="Status da Assinatura",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}) # Classe adicionada
    )

class EditarPerfilForm(forms.ModelForm):
    """
    Formulário para o usuário editar suas próprias informações.
    """
    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'email']
        labels = {
            'first_name': 'Nome',
            'last_name': 'Sobrenome',
            'email': 'Email de Cadastro',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Seu primeiro nome'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Seu sobrenome'}),
            'email': forms.EmailInput(attrs={'placeholder': 'seu.email@exemplo.com'}),
        }

class EditarAssinaturaForm(forms.ModelForm):
    class Meta:
        model = Assinatura
        fields = ['plano', 'status']
        labels = {
            'plano': 'Mudar para o Plano',
            'status': 'Mudar Status da Assinatura',
        }
        # ADICIONADO: Define a classe CSS para os campos
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

VOZES_NARRADOR = [
    ('pt-BR-Wavenet-A', 'Feminina - Voz A (Padrão)'),
    ('pt-BR-Wavenet-C', 'Feminina - Voz C'),
    ('pt-BR-Wavenet-D', 'Feminina - Voz D'),
    ('pt-BR-Wavenet-B', 'Masculina - Voz B (Padrão)'),
    ('pt-BR-Neural2-B', 'Masculina - Voz Neural'),
]

TONS_VOZ = [(2.0, 'Agudo'), (0.0, 'Normal'), (-2.0, 'Grave')]
PLANO_DE_FUNDO_CHOICES = [('normal', 'Normal / Escuro'), ('claro', 'Claro')]

FONTES_TEXTO = [
    ('cunia', 'Cunia (Decorativa)'),
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
    ('estatico', 'Texto Estático (Duração Manual)'),
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
    texto_overlay = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), required=False, label="Texto Estático")
    narrador_texto = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), required=False, label="Texto para Narração")
    
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
        label='Ativar Legenda Karaokê',
        required=False,
        help_text='Funciona apenas com Narração.'
    )
    narrador_voz = forms.ChoiceField(
        choices=VOZES_NARRADOR,
        required=False,
        label="Voz do Narrador"
    )
    narrador_velocidade = forms.IntegerField(
        min_value=80,
        max_value=120,
        initial=105,
        required=False,
        label="Velocidade (%)"
    )
    narrador_tom = forms.ChoiceField(
        choices=TONS_VOZ,
        initial=0.0,
        required=False,
        label="Tom da Voz"
    )

    # 4. MÍDIA DE FUNDO E DURAÇÃO
    categoria_video = forms.ModelChoiceField(queryset=CategoriaVideo.objects.all(), label="Categoria do Vídeo")
    categoria_musica = forms.ModelChoiceField(queryset=CategoriaMusica.objects.all(), label="Categoria da Música")
    volume_musica = forms.IntegerField(
        min_value=0,
        max_value=100,
        initial=50,
        label="Volume da Música (%)",
    )
    loop_video = forms.BooleanField(required=False, label="Repetir o vídeo (loop)?", initial=True)
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


# Cria o FormSet a partir do formulário
GeradorFormSet = formset_factory(GeradorForm, extra=1, max_num=3)