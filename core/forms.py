from django import forms
from django.forms import formset_factory
from .models import CategoriaVideo, CategoriaMusica

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
    ('arial', 'Arial'),
    ('arialbd', 'arialbd'),
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


# --- Classe do Formulário Final ---
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