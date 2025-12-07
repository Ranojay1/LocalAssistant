from pathlib import Path
import winsound


class SoundPlayer:
    def __init__(self, config):
        self.listening = Path(config.app.get("listening_sound", ""))
        self.stopped = Path(config.app.get("stopped_sound", ""))

    def play_listening(self):
        self._play(self.listening)

    def play_stopped(self):
        self._play(self.stopped)

    def _play(self, path: Path):
        if not path or not path.exists():
            return
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
        except Exception:
            pass
