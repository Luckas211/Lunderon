# core/management/commands/check_template.py

from django.core.management.base import BaseCommand
from django.template import loader
from django.template.exceptions import TemplateDoesNotExist

class Command(BaseCommand):
    help = 'Verifica se um template específico pode ser encontrado pelo Django.'

    def handle(self, *args, **options):
        template_path = 'core/planos/planos.html'
        self.stdout.write(f"Procurando pelo template: {template_path}")

        try:
            loader.get_template(template_path)
            self.stdout.write(self.style.SUCCESS(f'\n✅ SUCESSO: O template "{template_path}" foi encontrado!'))
            self.stdout.write("Isso significa que sua configuração e estrutura de pastas estão corretas.")

        except TemplateDoesNotExist as e:
            self.stdout.write(self.style.ERROR(f'\n❌ ERRO: O template "{template_path}" NÃO foi encontrado.'))
            self.stdout.write("O Django procurou nos seguintes locais:")

            # --- INÍCIO DA CORREÇÃO ---
            if e.chain:
                for backend in e.chain:
                    self.stdout.write(f"  - Usando o carregador: {backend.__class__.__name__}")
                    for directory in backend.get_dirs():
                        self.stdout.write(f"    - Verificou o diretório: {directory}")
            # --- FIM DA CORREÇÃO ---
            else:
                self.stdout.write("Nenhum caminho de busca foi retornado. Verifique a configuração TEMPLATES em settings.py.")