from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.shortcuts import redirect
from django.urls import reverse
from .models import (
    Usuario, CategoriaVideo, CategoriaMusica, VideoBase, MusicaBase,
    VideoGerado, Plano, Assinatura, Configuracao, Pagamento
)
from itertools import zip_longest
import os




# 1. Registro do modelo de usuário customizado
# ----------------------------------------------------
class CustomUserAdmin(UserAdmin):
    model = Usuario
    list_display = ('username', 'email', 'plano_ativo', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'plano_ativo')
    fieldsets = UserAdmin.fieldsets + (
        ('Status da Assinatura', {'fields': ('plano_ativo', 'stripe_customer_id', 'stripe_subscription_id')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('email',)}),
    )
    search_fields = ('username', 'email')
    ordering = ('-date_joined',)

admin.site.register(Usuario, CustomUserAdmin)

# 2. AÇÃO PARA CRIAR PASTAS MANUALMENTE
# ----------------------------------------------------



# 2. Registros de modelos de Mídia e Categorias
# ----------------------------------------------------
# 3. ADMIN DAS CATEGORIAS MODIFICADO
# ----------------------------------------------------
# Adicione ações para forçar criação de pastas
def criar_pastas_categorias(modeladmin, request, queryset):
    for categoria in queryset:
        categoria.save()  # Isso vai forçar a criação da pasta
    modeladmin.message_user(request, f"Pastas criadas para {queryset.count()} categorias.")
criar_pastas_categorias.short_description = "Criar pastas no Cloudflare R2"

@admin.register(CategoriaVideo)
class CategoriaVideoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'pasta')
    search_fields = ('nome', 'pasta')
    actions = [criar_pastas_categorias]

@admin.register(CategoriaMusica)
class CategoriaMusicaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'pasta')
    search_fields = ('nome', 'pasta')
    actions = [criar_pastas_categorias]

# Ação para corrigir object_keys - VERSÃO DEFINITIVA CORRIGIDA
def corrigir_object_keys(modeladmin, request, queryset):
    corrigidos = 0
    for midia in queryset:
        current_key = midia.object_key or ''
        
        # Extrai apenas o nome do arquivo (remove qualquer caminho existente)
        filename = os.path.basename(current_key)
        
        # Define o caminho correto baseado no tipo de mídia
        if isinstance(midia, VideoBase):
            correct_key = f'media/videos_base/{filename}'
        elif isinstance(midia, MusicaBase):
            correct_key = f'media/musicas_base/{filename}'
        else:
            continue
        
        # Atualiza SEMPRE para o caminho correto (mesmo que já esteja "correto" mas sem media/)
        if current_key != correct_key:
            midia.object_key = correct_key
            midia.save()
            corrigidos += 1
            print(f"Corrigido: {current_key} -> {correct_key}")  # Debug
    
    modeladmin.message_user(request, f"Object keys de {corrigidos} mídias foram corrigidos.")
corrigir_object_keys.short_description = "Corrigir object_keys para incluir caminho completo"

# Ação para forçar recálculo das URLs
def recalc_urls(modeladmin, request, queryset):
    for midia in queryset:
        midia.save()  # Isso força o recálculo da URL
    modeladmin.message_user(request, f"URLs de {queryset.count()} mídias foram recalculadas.")
recalc_urls.short_description = "Recalcular URLs"

@admin.register(VideoBase)
class VideoBaseAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'categoria', 'object_key', 'get_video_url')
    readonly_fields = ('get_video_url',)
    actions = [corrigir_object_keys, recalc_urls]
    
    def get_video_url(self, obj):
        return obj.video_url if hasattr(obj, 'video_url') else 'N/A'
    get_video_url.short_description = 'URL do Vídeo'

@admin.register(MusicaBase)
class MusicaBaseAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'categoria', 'object_key', 'get_musica_url')
    readonly_fields = ('get_musica_url',)
    actions = [corrigir_object_keys, recalc_urls]
    
    def get_musica_url(self, obj):
        return obj.musica_url if hasattr(obj, 'musica_url') else 'N/A'
    get_musica_url.short_description = 'URL da Música'

    def add_view(self, request, form_url='', extra_context=None):
        if request.method == 'POST':
            files = request.FILES.getlist('arquivo_musica_multiple')
            titles = request.POST.getlist('titulos_customizados')
            categoria_id = request.POST.get('categoria')

            if files and categoria_id:
                categoria = CategoriaMusica.objects.get(pk=categoria_id)
                
                for file, title in zip_longest(files, titles, fillvalue=None):
                    final_title = title if title else file.name
                    # Salva com object_key correto
                    musica = MusicaBase(
                        titulo=final_title,
                        categoria=categoria,
                        arquivo_musica=file
                    )
                    musica.save()  # Isso automaticamente seta o object_key correto
                
                self.message_user(request, f"{len(files)} músicas foram adicionadas com sucesso.")
                return redirect(reverse('admin:core_musicabase_changelist'))
        
        return super().add_view(request, form_url, extra_context)


# 3. Registros de modelos da Aplicação (Vídeos, Planos, Assinaturas, etc.)
# ----------------------------------------------------
@admin.register(VideoGerado)
class VideoGeradoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'status', 'criado_em', 'arquivo_final')
    list_filter = ('status', 'usuario')
    search_fields = ('usuario__username',)
    readonly_fields = ('criado_em',)

@admin.register(Plano)
class PlanoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'preco',)
    search_fields = ('nome',)

@admin.register(Assinatura)
class AssinaturaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'plano', 'status', 'data_inicio', 'data_expiracao')
    list_filter = ('status', 'plano')
    search_fields = ('usuario__username', 'usuario__email')
    actions = ['ativar_assinaturas', 'cancelar_assinaturas']

    def ativar_assinaturas(self, request, queryset):
        queryset.update(status='ativo')
    ativar_assinaturas.short_description = "Ativar assinaturas selecionadas"

    def cancelar_assinaturas(self, request, queryset):
        queryset.update(status='cancelado')
    cancelar_assinaturas.short_description = "Cancelar assinaturas selecionadas"


@admin.register(Configuracao)
class ConfiguracaoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'valor')
    search_fields = ('nome',)


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'plano', 'valor', 'status', 'data_pagamento')
    list_filter = ('status', 'plano')
    search_fields = ('usuario__username',)
    actions = ['aprovar_pagamentos', 'recusar_pagamentos']

    def aprovar_pagamentos(self, request, queryset):
        queryset.update(status='aprovado')
    aprovar_pagamentos.short_description = "Aprovar pagamentos selecionados"

    def recusar_pagamentos(self, request, queryset):
        queryset.update(status='recusado')
    recusar_pagamentos.short_description = "Recusar pagamentos selecionados"