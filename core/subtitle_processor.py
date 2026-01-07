"""
Módulo para processamento de legendas automáticas usando Whisper
Recursos 100% gratuitos para transcrição de áudio
"""

import os
import tempfile
import subprocess

try:
    import whisper
except ImportError:
    print(
        "AVISO: Biblioteca whisper não encontrada. Instale com: pip install openai-whisper"
    )
    whisper = None
import json
from typing import List, Dict, Tuple, Optional
from django.conf import settings
import random


class SubtitleProcessor:
    """Processador de legendas automáticas usando Whisper"""

    def __init__(self):
        # Carrega o modelo Whisper (pequeno para ser mais rápido)
        if whisper is not None:
            try:
                self.model = whisper.load_model("large-v3")
            except Exception as e:
                print(f"Erro ao carregar modelo Whisper: {e}")
                self.model = None
        else:
            self.model = None

    def extract_audio_from_video(self, video_path: str) -> str:
        """
        Extrai áudio de um vídeo usando FFmpeg

        Args:
            video_path: Caminho para o arquivo de vídeo

        Returns:
            Caminho para o arquivo de áudio extraído
        """
        if not os.path.exists(video_path):
            print(f"Erro: Arquivo de vídeo não encontrado: {video_path}")
            return None

        # Cria arquivo temporário para o áudio
        audio_temp_dir = os.path.join(settings.MEDIA_ROOT, "audio_temp")
        os.makedirs(audio_temp_dir, exist_ok=True)

        audio_path = os.path.join(
            audio_temp_dir, f"extracted_audio_{random.randint(1000, 9999)}.wav"
        )

        # Comando FFmpeg para extrair áudio
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vn",  # Sem vídeo
            "-acodec",
            "pcm_s16le",  # Codec de áudio
            "-ar",
            "16000",  # Sample rate para Whisper
            "-ac",
            "1",  # Mono
            audio_path,
        ]

        try:
            subprocess.run(
                cmd, check=True, capture_output=True, text=True, encoding="utf-8"
            )
            return audio_path
        except subprocess.CalledProcessError as e:
            print(f"Erro ao extrair áudio: {e}")
            print(f"STDERR: {e.stderr}")
            return None
        except FileNotFoundError:
            print(
                "Erro: FFmpeg não encontrado. Certifique-se de que está instalado e no PATH."
            )
            return None

    def transcribe_audio(self, audio_path: str) -> Optional[Dict]:
        """
        Transcreve áudio usando Whisper

        Args:
            audio_path: Caminho para o arquivo de áudio

        Returns:
            Resultado da transcrição com timestamps
        """
        if self.model is None:
            print("Erro: Modelo Whisper não carregado")
            return None

        if not os.path.exists(audio_path):
            print(f"Erro: Arquivo de áudio não encontrado: {audio_path}")
            return None

        try:
            # Transcreve com timestamps de palavras
            result = self.model.transcribe(
                audio_path,
                language="pt",  # Português
                word_timestamps=True,
                verbose=False,
            )
            return result
        except Exception as e:
            print(f"Erro na transcrição: {e}")
            return None

    def create_subtitle_segments(
        self, transcription: Dict, max_chars_per_line: int = 40
    ) -> List[Dict]:
        """
        Cria segmentos de legenda a partir da transcrição

        Args:
            transcription: Resultado da transcrição do Whisper
            max_chars_per_line: Máximo de caracteres por linha

        Returns:
            Lista de segmentos de legenda
        """
        segments = []

        for segment in transcription.get("segments", []):
            text = segment["text"].strip()
            start_time = segment["start"]
            end_time = segment["end"]

            # Quebra texto longo em múltiplas linhas
            if len(text) > max_chars_per_line:
                words = text.split()
                lines = []
                current_line = ""

                for word in words:
                    if len(current_line + " " + word) <= max_chars_per_line:
                        current_line += (" " + word) if current_line else word
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word

                if current_line:
                    lines.append(current_line)

                text = "\\N".join(lines)  # \\N é quebra de linha no formato ASS

            segments.append({"start": start_time, "end": end_time, "text": text})

        return segments

    def format_time_ass(self, seconds: float) -> str:
        """
        Formata tempo para o formato ASS

        Args:
            seconds: Tempo em segundos

        Returns:
            Tempo formatado (H:MM:SS.CC)
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds - int(seconds)) * 100)

        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

    def generate_ass_subtitle(
        self, segments: List[Dict], video_width: int = 1080, video_height: int = 1920
    ) -> str:
        """
        Gera arquivo de legenda no formato ASS

        Args:
            segments: Lista de segmentos de legenda
            video_width: Largura do vídeo
            video_height: Altura do vídeo

        Returns:
            Caminho para o arquivo de legenda gerado
        """
        # Configurações de estilo para legendas
        style_config = {
            "fontname": "Arial",
            "fontsize": 24,
            "primary_color": "&H00FFFFFF",  # Branco
            "secondary_color": "&H00FFFFFF",
            "outline_color": "&H00000000",  # Preto
            "back_color": "&H80000000",  # Preto semi-transparente
            "bold": -1,  # Negrito
            "italic": 0,
            "underline": 0,
            "strikeout": 0,
            "scale_x": 100,
            "scale_y": 100,
            "spacing": 0,
            "angle": 0,
            "border_style": 1,
            "outline": 2,
            "shadow": 2,
            "alignment": 2,  # Centralizado na parte inferior
            "margin_l": 10,
            "margin_r": 10,
            "margin_v": 80,  # Margem vertical para ficar fora do vídeo
            "encoding": 1,
        }

        # Cabeçalho do arquivo ASS
        ass_header = f"""[Script Info]
Title: Legendas Automáticas
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style_config['fontname']},{style_config['fontsize']},{style_config['primary_color']},{style_config['secondary_color']},{style_config['outline_color']},{style_config['back_color']},{style_config['bold']},{style_config['italic']},{style_config['underline']},{style_config['strikeout']},{style_config['scale_x']},{style_config['scale_y']},{style_config['spacing']},{style_config['angle']},{style_config['border_style']},{style_config['outline']},{style_config['shadow']},{style_config['alignment']},{style_config['margin_l']},{style_config['margin_r']},{style_config['margin_v']},{style_config['encoding']}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # Gera os diálogos
        dialogues = []
        for segment in segments:
            start_time = self.format_time_ass(segment["start"])
            end_time = self.format_time_ass(segment["end"])
            text = segment["text"]

            dialogue = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
            dialogues.append(dialogue)

        # Conteúdo completo do arquivo ASS
        ass_content = ass_header + "\n".join(dialogues)

        # Salva o arquivo
        subtitle_temp_dir = os.path.join(settings.MEDIA_ROOT, "subtitle_temp")
        os.makedirs(subtitle_temp_dir, exist_ok=True)

        subtitle_path = os.path.join(
            subtitle_temp_dir, f"auto_subtitle_{random.randint(1000, 9999)}.ass"
        )

        with open(subtitle_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        return subtitle_path

    def process_video_subtitles(self, video_path: str) -> Optional[str]:
        """
        Processa um vídeo completo para gerar legendas automáticas

        Args:
            video_path: Caminho para o arquivo de vídeo

        Returns:
            Caminho para o arquivo de legenda gerado ou None se houver erro
        """
        if self.model is None:
            print("Erro: Modelo Whisper não disponível")
            return None

        audio_path = None
        try:
            print(f"Extraindo áudio de: {video_path}")
            # 1. Extrai áudio do vídeo
            audio_path = self.extract_audio_from_video(video_path)
            if not audio_path:
                print("Falha na extração de áudio")
                return None

            print(f"Transcrevendo áudio: {audio_path}")
            # 2. Transcreve o áudio
            transcription = self.transcribe_audio(audio_path)
            if not transcription:
                print("Falha na transcrição")
                return None

            print("Criando segmentos de legenda")
            # 3. Cria segmentos de legenda
            segments = self.create_subtitle_segments(transcription)
            if not segments:
                print("Nenhum segmento de legenda criado")
                return None

            print(f"Gerando arquivo ASS com {len(segments)} segmentos")
            # 4. Gera arquivo de legenda
            subtitle_path = self.generate_ass_subtitle(segments)

            print(f"Legendas geradas com sucesso: {subtitle_path}")
            return subtitle_path

        except Exception as e:
            print(f"Erro no processamento de legendas: {e}")
            return None
        finally:
            # Limpa arquivo de áudio temporário
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except:
                    pass

    def has_speech(self, video_path: str, min_speech_duration: float = 2.0) -> bool:
        """
        Verifica se o vídeo tem fala suficiente para gerar legendas

        Args:
            video_path: Caminho para o arquivo de vídeo
            min_speech_duration: Duração mínima de fala em segundos

        Returns:
            True se o vídeo tem fala suficiente
        """
        if self.model is None:
            print("Erro: Modelo Whisper não disponível")
            return False

        audio_path = None
        try:
            # Extrai áudio
            audio_path = self.extract_audio_from_video(video_path)
            if not audio_path:
                return False

            # Transcreve apenas para verificar
            result = self.model.transcribe(audio_path, language="pt")

            # Calcula duração total de fala
            total_speech_duration = 0
            for segment in result.get("segments", []):
                total_speech_duration += segment["end"] - segment["start"]

            return total_speech_duration >= min_speech_duration

        except Exception as e:
            print(f"Erro ao verificar fala: {e}")
            return False
        finally:
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except:
                    pass


# Instância global do processador
try:
    subtitle_processor = SubtitleProcessor()
except Exception as e:
    print(f"Erro ao inicializar SubtitleProcessor: {e}")
    subtitle_processor = None
