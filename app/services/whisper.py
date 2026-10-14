class WhisperTranscriber:
    """Интерфейс распознавания речи.

    В первой версии на каждом рендере не вызывается: субтитры берутся из текста voiceover.
    """

    def transcribe(self, audio_path: str) -> str:
        raise NotImplementedError(
            "Whisper не запускается в первой версии. Субтитры пишутся из текста озвучки."
        )
