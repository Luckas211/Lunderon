import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from core.models import VideoBase, MusicaBase

def check_r2_files():
    s3_client = boto3.client(
        's3',
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )
    
    # Verificar vídeos
    print("Verificando vídeos...")
    videos = VideoBase.objects.all()
    for video in videos:
        if video.object_key:
            try:
                s3_client.head_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=video.object_key
                )
                print(f"✓ Vídeo OK: {video.object_key}")
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    print(f"✗ Vídeo FALTANDO: {video.object_key} - {video.titulo}")
                else:
                    print(f"? Erro ao verificar vídeo {video.object_key}: {e}")
    
    # Verificar músicas
    print("\nVerificando músicas...")
    musicas = MusicaBase.objects.all()
    for musica in musicas:
        if musica.object_key:
            try:
                s3_client.head_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=musica.object_key
                )
                print(f"✓ Música OK: {musica.object_key}")
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    print(f"✗ Música FALTANDO: {musica.object_key} - {musica.titulo}")
                else:
                    print(f"? Erro ao verificar música {musica.object_key}: {e}")

if __name__ == "__main__":
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'seu_projeto.settings')
    django.setup()
    check_r2_files()