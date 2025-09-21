from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Rotas Públicas
    path('', views.index, name='index'),
    path('como-funciona/', views.como_funciona, name='como_funciona'),
    path('planos/', views.planos, name='planos'),
    path('suporte/', views.suporte, name='suporte'),
    path('termos-de-servico/', views.termos_de_servico, name='termos_de_servico'),
    path('politica-de-privacidade/', views.politica_de_privacidade, name='politica_de_privacidade'),
    path('pagamento/sucesso/', views.pagamento_sucesso, name='pagamento_sucesso'),
    path('pagamento/falha/', views.pagamento_falho, name='pagamento_falho'),

    # Rotas de Autenticação
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('cadastre-se/', views.cadastre_se, name='cadastre_se'),
    path('verificar-email/<str:token>/', views.verificar_email, name='verify_email'),
    path('reenviar-verificacao/<int:user_id>/', views.reenviar_verificacao_email, name='reenviar_verificacao'),
    
    # Rotas de Redefinição de Senha
    path('redefinir-senha/', auth_views.PasswordResetView.as_view(template_name='core/password_reset_form.html'), name='password_reset'),
    path('redefinir-senha/enviado/', auth_views.PasswordResetDoneView.as_view(template_name='core/password_reset_done.html'), name='password_reset_done'),
    path('redefinir-senha/confirmar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='core/password_reset_confirm.html'), name='password_reset_confirm'),
    path('redefinir-senha/completo/', auth_views.PasswordResetCompleteView.as_view(template_name='core/password_reset_complete.html'), name='password_reset_complete'),

    # Rotas do Webhook do Stripe
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),

    # Rotas da Aplicação (Requerem Login)
    path('meu-perfil/', views.meu_perfil, name='meu_perfil'),
    path('meu-perfil/editar/', views.editar_perfil, name='editar_perfil'),
    path('meu-perfil/assinatura/', views.gerenciar_assinatura_redirect, name='gerenciar_assinatura'),
    path('meus-videos/', views.meus_videos, name='meus_videos'),
    path('video/<int:video_id>/download/', views.video_download_page, name='video_download_page'),
    path('video/<int:video_id>/download-direto/', views.download_video_direto, name='download_video_direto'),
    path('video/<int:video_id>/excluir/', views.delete_video_file, name='delete_video_file'),
    path('gerador/', views.pagina_gerador, name='pagina_gerador'),
    path('cortes-youtube/', views.cortes_youtube_view, name='cortes_youtube'),

    # Endpoints AJAX
    path('api/estimativa-narracao/', views.estimativa_narracao, name='estimativa_narracao'),
    path('api/preview-voz/<str:nome_da_voz>/', views.preview_voz, name='preview_voz'),
    path('api/youtube-segments/', views.get_youtube_segments, name='get_youtube_segments'),
    path('api/preview-video/<int:categoria_id>/', views.preview_video_base, name='preview_video_base'), # NOVA ROTA

    # Rotas de Pagamento
    path('criar-checkout/<int:plano_id>/', views.criar_checkout_session, name='criar_checkout_session'),

    # Rotas do Painel Admin
    path('painel-admin/assinaturas/', views.admin_assinaturas, name='admin_assinaturas'),
    path('painel-admin/assinaturas/ativar/<int:id>/', views.ativar_assinatura, name='ativar_assinatura'),
    path('painel-admin/assinaturas/cancelar/<int:id>/', views.cancelar_assinatura, name='cancelar_assinatura'),
    path('painel-admin/assinaturas/editar/<int:id>/', views.editar_assinatura, name='editar_assinatura'),
    path('painel-admin/assinaturas/excluir/<int:id>/', views.excluir_assinatura, name='excluir_assinatura'),
    path('painel-admin/usuarios/', views.admin_usuarios, name='admin_usuarios'),
    path('painel-admin/usuarios/editar/<int:user_id>/', views.editar_usuario, name='editar_usuario'),
    path('painel-admin/usuarios/deletar/<int:user_id>/', views.deletar_usuario, name='deletar_usuario'),
    path('painel-admin/usuarios/ativar/<int:user_id>/', views.admin_ativar_usuario, name='admin_ativar_usuario'),
    path('painel-admin/usuarios/reenviar-verificacao/<int:user_id>/', views.admin_reenviar_verificacao, name='admin_reenviar_verificacao'),
    path('painel-admin/configuracoes/', views.admin_configuracoes, name='admin_configuracoes'),
    path('painel-admin/configuracoes/adicionar/', views.adicionar_configuracao, name='adicionar_configuracao'),
    path('painel-admin/configuracoes/editar/<int:id>/', views.editar_configuracao, name='editar_configuracao'),
    path('painel-admin/configuracoes/deletar/<int:id>/', views.deletar_configuracao, name='deletar_configuracao'),
    path('painel-admin/pagamentos/', views.admin_pagamentos, name='admin_pagamentos'),
    path('painel-admin/pagamentos/aprovar/<int:id>/', views.aprovar_pagamento, name='aprovar_pagamento'),
    path('painel-admin/pagamentos/recusar/<int:id>/', views.recusar_pagamento, name='recusar_pagamento'),
    path('painel-admin/pagamentos/deletar/<int:id>/', views.deletar_pagamento, name='deletar_pagamento'),
    path('painel-admin/relatorios/', views.admin_relatorios, name='admin_relatorios'),
    path('painel-admin/assinatura/<int:assinatura_id>/deixar-pendente/', views.deixar_assinatura_pendente, name='deixar_assinatura_pendente'),
    path('painel-admin/assinatura/<int:assinatura_id>/cancelar-admin/', views.cancelar_assinatura_admin, name='cancelar_assinatura_admin'),
]