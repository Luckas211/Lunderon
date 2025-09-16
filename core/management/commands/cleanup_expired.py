from django.core.management.base import BaseCommand
from core.models import VideoGerado, VideoCorte
from django.utils import timezone
import boto3
from django.conf import settings

class Command(BaseCommand):
    help = 'Remove arquivos expirados (vídeos e cortes) do R2'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        for model in [VideoGerado, VideoCorte]:
            expired = model.objects.filter(expiracao_em__lte=now, arquivo_final__isnull=False)
            s3_client = boto3.client(
                's3',
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
            )
            for item in expired:
                try:
                    s3_client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=item.arquivo_final.name)
                    item.arquivo_final = None
                    item.save()
                    self.stdout.write(self.style.SUCCESS(f'Removido: {item}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Erro ao remover {item}: {e}'))