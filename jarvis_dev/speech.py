"""Push-to-talk recording and transcription through Google's Gemini API."""

from __future__ import annotations

import base64
import io
import threading
import time
import wave
from typing import Callable

import sounddevice as sd

from .gemini import GeminiClient, GeminiError, response_text


class SpeechError(Exception):
    pass


def record_wav(stop_event: threading.Event, progress: Callable[[str], None], max_seconds: int = 30) -> bytes:
    chunks: list[bytes] = []
    stream_errors: list[str] = []

    def callback(indata, frames, time_info, status):
        del frames, time_info
        if status:
            stream_errors.append(str(status))
        chunks.append(bytes(indata))

    try:
        with sd.RawInputStream(samplerate=16000, channels=1, dtype="int16", callback=callback,
                               blocksize=1600):
            progress("Ouvindo: clique em Encerrar gravação ao terminar")
            deadline = time.monotonic() + max_seconds
            while not stop_event.wait(0.1) and time.monotonic() < deadline:
                pass
    except (sd.PortAudioError, OSError) as exc:
        raise SpeechError(f"Não foi possível acessar o microfone: {exc}") from exc
    if not chunks:
        raise SpeechError("Nenhum áudio foi capturado. Verifique o microfone e tente novamente.")
    if stream_errors:
        progress("O dispositivo relatou uma instabilidade durante a gravação")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"".join(chunks))
    return buffer.getvalue()


def transcribe_wav(audio: bytes, api_key: str | None = None) -> str:
    if not audio:
        raise SpeechError("Nenhum áudio foi capturado. Tente gravar novamente.")
    parts = [{"text": "Transcreva literalmente a fala deste áudio no idioma original. Retorne somente a transcrição, sem comentários. Se não houver fala compreensível, retorne texto vazio."},
             {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(audio).decode("ascii")}}]
    try:
        content = GeminiClient(api_key=api_key).generate([{"role": "user", "parts": parts}])
        transcript = response_text(content)
    except GeminiError as exc:
        raise SpeechError(str(exc)) from exc
    if not transcript:
        raise SpeechError("A transcrição não encontrou fala. Tente gravar novamente.")
    return transcript
