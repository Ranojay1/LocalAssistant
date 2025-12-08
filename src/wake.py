import threading
import struct
from pathlib import Path
import keyboard
import sounddevice as sd
from queue import Queue
from src.tts import TextToSpeech


class WakeController:
    def __init__(self, config, events: Queue, sound_player):
        self.hotkey = config.app.get("hotkey", "F9")
        self.porcupine_key = config.app.get("porcupine_access_key", "")
        self.porcupine_kw = Path(config.app.get("porcupine_keyword_path", ""))
        self.wake_word = config.app.get("wake_word", "").strip().lower()
        self.events = events
        self.sound_player = sound_player
        self.stop_event = threading.Event()
        self._porcupine = None

        if self.porcupine_key:
            keyword_paths = []
            keywords = []
            if self.porcupine_kw.exists():
                keyword_paths = [str(self.porcupine_kw)]
            elif self.wake_word:
                keywords = [self.wake_word]

            if keyword_paths or keywords:
                try:
                    import pvporcupine

                    self._porcupine = pvporcupine.create(
                        access_key=self.porcupine_key,
                        keyword_paths=keyword_paths or None,
                        keywords=keywords or None,
                    )
                    print(f"[Wake] Porcupine activo con wake-word: {self.wake_word or self.porcupine_kw.name}")
                except Exception as err:
                    print(f"[Wake] No se pudo iniciar Porcupine: {err}")
                    self._porcupine = None
            else:
                print("[Wake] Sin keyword path ni wake_word configurado; usando solo hotkey.")
        else:
            print("[Wake] porcupine_access_key vacío; usando solo hotkey.")

    def run(self):
        keyboard.add_hotkey(self.hotkey, self._trigger)
        if self._porcupine:
            threading.Thread(target=self._run_porcupine, daemon=True).start()
        self.stop_event.wait()

    def _trigger(self):
        # Si está sonando TTS, solicitar parada
        TextToSpeech.request_stop()
        self.events.put({"type": "wake"})
        self.sound_player.play_listening()

    def _run_porcupine(self):
        porcupine = self._porcupine
        frame_len = porcupine.frame_length
        sample_rate = porcupine.sample_rate

        def callback(indata, frames, _time, status):
            if status:
                return
            pcm = struct.unpack_from(
                "h" * frame_len, indata[: frame_len * 2]
            )
            result = porcupine.process(pcm)
            if result >= 0:
                self._trigger()

        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=frame_len,
            dtype="int16",
            channels=1,
            callback=callback,
        ):
            self.stop_event.wait()
