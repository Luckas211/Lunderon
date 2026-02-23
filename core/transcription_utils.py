import os
import subprocess
import tempfile
from faster_whisper import WhisperModel
from django.conf import settings

# Define o modelo Whisper a ser usado. 'base' é um bom equilíbrio entre velocidade e precisão.
WHISPER_MODEL_SIZE = "medium"
_model = None

def get_whisper_model():
    """Carrega o modelo Whisper uma única vez para reutilização."""
    global _model
    if _model is None:
        # Para produção no Cloud Run, 'cpu' e 'int8' são as melhores opções
        # para equilibrar performance e consumo de recursos.
        _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model

def extract_audio_from_video(video_path):
    """
    Extrai o áudio de um arquivo de vídeo usando ffmpeg.
    Retorna o caminho para o arquivo de áudio temporário.
    """
    audio_temp_dir = os.path.join(settings.MEDIA_ROOT, "audio_temp")
    os.makedirs(audio_temp_dir, exist_ok=True)
    
    audio_filename = os.path.basename(video_path).rsplit('.', 1)[0] + ".wav"
    audio_path = os.path.join(audio_temp_dir, audio_filename)

    cmd = [
        "ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", 
        "-ar", "16000", "-ac", "1", "-y", audio_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', stdin=subprocess.DEVNULL)
        return audio_path
    except subprocess.CalledProcessError as e:
        print(f"Erro ao extrair áudio: {e.stderr}")
        raise

def transcribe_audio_to_srt(audio_path, language="pt"):
    """
    Transcreve um arquivo de áudio para um arquivo SRT (formato de legenda simples).
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

# ================================================================
#          FUNÇÃO ADICIONADA PARA LEGENDAS PRECISAS
# ================================================================
def get_word_timestamps(audio_path, language="pt"):
    """
    Transcreve um áudio e retorna uma lista de palavras com seus tempos
    de início e fim, essencial para a legenda karaokê.
    """
    model = get_whisper_model()
    segments, info = model.transcribe(audio_path, language=language, word_timestamps=True)

    all_words = []
    for segment in segments:
        for word in segment.words:
            all_words.append({
                'word': word.word,
                'start': word.start,
                'end': word.end
            })
    return all_words
# ================================================================

def format_timestamp(seconds):
    """Formata segundos para o formato SRT (HH:MM:SS,ms)."""
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)
    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000
    minutes = milliseconds // 60_000
    milliseconds %= 60_000
    seconds = milliseconds // 1_000
    milliseconds %= 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"