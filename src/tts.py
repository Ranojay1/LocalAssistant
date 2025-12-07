import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice
import threading


class TextToSpeech:
    stop_event = threading.Event()

    def __init__(self, config):
        cfg = config.tts
        self.voice = PiperVoice.load(cfg["voice_path"])
        self.sample_rate = cfg.get("sample_rate", 22050)
        self.speaker = cfg.get("speaker")

    def speak(self, text: str):
        self.stop_event.clear()

        # Streaming playback to allow interruption
        def gen_audio():
            for audio_chunk in self.voice.synthesize(text):
                if self.stop_event.is_set():
                    break
                if audio_chunk is not None:
                    yield audio_chunk.audio_int16_array

        stream = sd.OutputStream(
            samplerate=self.voice.config.sample_rate,
            channels=1,
            dtype="int16",
        )

        try:
            with stream:
                for chunk in gen_audio():
                    if chunk is None or len(chunk) == 0:
                        continue
                    if self.stop_event.is_set():
                        break
                    stream.write(chunk.reshape(-1, 1))
        except Exception as e:
            print(f"[TTS] Error: {e}")

    @classmethod
    def request_stop(cls):
        cls.stop_event.set()
        try:
            sd.stop()
        except Exception:
            pass
