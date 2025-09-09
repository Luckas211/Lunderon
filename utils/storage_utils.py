import boto3
from botocore.exceptions import ClientError
from django.conf import settings

def criar_pasta_r2(caminho_completo):
    """
    Cria uma pasta no Cloudflare R2
    """
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        
        # Cria objeto vazio para simular pasta
        s3_client.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=f"{caminho_completo}/",
            Body=b'',
            ContentLength=0
        )
        return True
    except Exception as e:
        print(f"Erro ao criar pasta {caminho_completo}: {e}")
        return False

def listar_arquivos_na_pasta(caminho_pasta):
    """
    Lista todos os arquivos em uma pasta do R2
    """
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        
        response = s3_client.list_objects_v2(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Prefix=caminho_pasta
        )
        
        arquivos = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if not obj['Key'].endswith('/'):  # Ignora pastas
                    arquivos.append(obj['Key'])
        
        return arquivos
    except Exception as e:
        print(f"Erro ao listar arquivos em {caminho_pasta}: {e}")
        return []