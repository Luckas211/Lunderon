FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Instalação de dependências do sistema (FFmpeg e outros)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# AQUI ESTÁ A CORREÇÃO: --default-timeout=1000
# Isso evita que o download do PyTorch falhe se a internet oscilar
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

COPY . .

# Coleta estáticos e define o comando de execução
RUN python manage.py collectstatic --noinput

CMD exec gunicorn gerador_videos.wsgi:application --bind "0.0.0.0:8000" --threads 8 --timeout 3600