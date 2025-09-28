# 1. Comece com uma imagem oficial do Python
FROM python:3.11-slim

# 2. Defina variáveis de ambiente para otimização
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Instale o ffmpeg e outras dependências do sistema
RUN apt-get update && apt-get install -y ffmpeg

# 4. Configure o diretório de trabalho
WORKDIR /app

# 5. Copie e instale as dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copie o resto do seu código para o contêiner
COPY . .

# 7. Colete os arquivos estáticos para o WhiteNoise servir
RUN python manage.py collectstatic --noinput

# 8. Comando para iniciar seu servidor web de produção
#    O Cloud Run define a variável de ambiente $PORT, que usamos aqui.
#    --timeout 0 desativa o timeout do worker do gunicorn, deixando o Cloud Run gerenciar o tempo limite da requisição
CMD exec gunicorn gerador_videos.wsgi:application --bind "0.0.0.0:$PORT" --workers 1 --threads 8 --timeout 0