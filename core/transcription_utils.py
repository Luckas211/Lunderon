import os
import subprocess
import tempfile
from faster_whisper import WhisperModel
from django.conf import settings

# Define o modelo Whisper a ser usado. 'base' é um bom equilíbrio entre velocidade e precisão.
# Para produção em Cloud Run, pode ser necessário ajustar para 'tiny' ou 'base-int8'
# dependendo dos recursos disponíveis e da performance desejada.
WHISPER_MODEL_SIZE = "base"
_model = None

def get_whisper_model():
    """Carrega o modelo Whisper uma única vez."""
    global _model
    if _model is None:
        # O dispositivo 'cuda' pode ser usado se houver GPU disponível, caso contrário 'cpu'
        # Para Cloud Run, geralmente será 'cpu'
        _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model

def extract_audio_from_video(video_path):
    """
    Extrai o áudio de um arquivo de vídeo usando ffmpeg.
    Retorna o caminho para o arquivo de áudio temporário.
    """
    audio_temp_dir = os.path.join(settings.MEDIA_ROOT, "audio_temp")
    os.makedirs(audio_temp_dir, exist_ok=True)
    
    # Cria um nome de arquivo temporário para o áudio
    audio_filename = os.path.basename(video_path).rsplit('.', 1)[0] + ".wav"
    audio_path = os.path.join(audio_temp_dir, audio_filename)

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # Desabilita o stream de vídeo
        "-acodec", "pcm_s16le",  # Codec de áudio PCM de 16 bits (sem compressão)
        "-ar", "16000",  # Taxa de amostragem de 16 kHz (ótimo para Whisper)
        "-ac", "1",  # Mono
        audio_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        return audio_path
    except subprocess.CalledProcessError as e:
        print(f"Erro ao extrair áudio: {e.stderr}")
        raise
    except FileNotFoundError:
        print("FFmpeg não encontrado. Certifique-se de que está instalado e no PATH.")
        raise

def transcribe_audio_to_srt(audio_path, language="pt"):
    """
    Transcreve um arquivo de áudio para um arquivo SRT usando Faster Whisper.
    Retorna o caminho para o arquivo SRT gerado.
    """
    model = get_whisper_model()
    
    segments, info = model.transcribe(audio_path, language=language, beam_size=5)

    srt_temp_dir = os.path.join(settings.MEDIA_ROOT, "legenda_temp")
    os.makedirs(srt_temp_dir, exist_ok=True)
    
    srt_filename = os.path.basename(audio_path).rsplit('.', 1)[0] + ".srt"
    srt_path = os.path.join(srt_temp_dir, srt_filename)

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments):
            start_time = format_timestamp(segment.start)
            end_time = format_timestamp(segment.end)
            f.write(f"{i + 1}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{segment.text.strip()}\n\n")
            
    return srt_path

def format_timestamp(seconds):
    """Formata segundos para o formato SRT HH:MM:SS,ms."""
    milliseconds = int((seconds - int(seconds)) * 1000)
    seconds = int(seconds)
    minutes = seconds // 60
    hours = minutes // 60
    return f"{hours:02d}:{minutes % 60:02d}:{seconds % 60:02d},{milliseconds:03d}"
