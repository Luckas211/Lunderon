from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.shortcuts import redirect
from django.urls import reverse
from .models import (
    Usuario, CategoriaVideo, CategoriaMusica, VideoBase, MusicaBase,
    VideoGerado, Plano, Assinatura, Configuracao, Pagamento
)
from itertools import zip_longest

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


# 2. Registros de modelos de Mídia e Categorias
# ----------------------------------------------------
@admin.register(CategoriaVideo)
class CategoriaVideoAdmin(admin.ModelAdmin):
    list_display = ('nome',)
    search_fields = ('nome',)

@admin.register(CategoriaMusica)
class CategoriaMusicaAdmin(admin.ModelAdmin):
    list_display = ('nome',)
    search_fields = ('nome',)

@admin.register(VideoBase)
class VideoBaseAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'categoria', 'arquivo_video')
    list_filter = ('categoria',)
    search_fields = ('titulo',)
    change_form_template = 'admin/core/videobase/change_form.html'

    def add_view(self, request, form_url='', extra_context=None):
        if request.method == 'POST':
            files = request.FILES.getlist('arquivo_video_multiple')
            # Pega a lista de títulos customizados
            titles = request.POST.getlist('titulos_customizados')
            categoria_id = request.POST.get('categoria')
            
            if files and categoria_id:
                categoria = CategoriaVideo.objects.get(pk=categoria_id)
                
                # Combina os arquivos com os títulos. fillvalue=None para caso um título não seja preenchido
                for file, title in zip_longest(files, titles, fillvalue=None):
                    # Se o título estiver em branco ou não for fornecido, usa o nome do arquivo
                    final_title = title if title else file.name

                    VideoBase.objects.create(
                        titulo=final_title,
                        categoria=categoria,
                        arquivo_video=file
                    )
                
                self.message_user(request, f"{len(files)} vídeos foram adicionados com sucesso.")
                return redirect(reverse('admin:core_videobase_changelist'))
        
        return super().add_view(request, form_url, extra_context)


@admin.register(MusicaBase)
class MusicaBaseAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'categoria', 'arquivo_musica')
    list_filter = ('categoria',)
    search_fields = ('titulo',)
    change_form_template = 'admin/core/musicabase/change_form.html'

    def add_view(self, request, form_url='', extra_context=None):
        if request.method == 'POST':
            files = request.FILES.getlist('arquivo_musica_multiple')
            titles = request.POST.getlist('titulos_customizados')
            categoria_id = request.POST.get('categoria')

            if files and categoria_id:
                categoria = CategoriaMusica.objects.get(pk=categoria_id)
                
                for file, title in zip_longest(files, titles, fillvalue=None):
                    final_title = title if title else file.name
                    MusicaBase.objects.create(
                        titulo=final_title,
                        categoria=categoria,
                        arquivo_musica=file
                    )
                
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