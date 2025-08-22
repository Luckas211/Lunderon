from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Usuario, CategoriaVideo, CategoriaMusica, VideoBase, MusicaBase,
    VideoGerado, Plano, Assinatura, Configuracao, Pagamento
)

# 1. Registro do modelo de usuário customizado
# ----------------------------------------------------
class CustomUserAdmin(UserAdmin):
    model = Usuario
    list_display = ('username', 'email', 'plano_ativo', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'plano_ativo')
    # Adicionando 'plano_ativo' aos fieldsets para visualização e edição
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

@admin.register(MusicaBase)
class MusicaBaseAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'categoria', 'arquivo_musica')
    list_filter = ('categoria',)
    search_fields = ('titulo',)


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
    actions = ['ativar_assinaturas', 'cancelar_assinaturas'] # Ações devem ser listadas aqui

    # CORREÇÃO: As ações foram movidas para DENTRO da classe
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

    # CORREÇÃO: As ações foram movidas para DENTRO da classe
    def aprovar_pagamentos(self, request, queryset):
        queryset.update(status='aprovado')
    aprovar_pagamentos.short_description = "Aprovar pagamentos selecionados"

    def recusar_pagamentos(self, request, queryset):
        queryset.update(status='recusado')
    recusar_pagamentos.short_description = "Recusar pagamentos selecionados"