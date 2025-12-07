import threading
import queue
from src.config import load_config
from src.sounds import SoundPlayer
from src.wake import WakeController
from src.stt import SpeechToText
from src.llm import LlmEngine
from src.tts import TextToSpeech
from src.actions import ActionRouter
from src.pipeline import Pipeline
from src.model_downloader import ensure_models


def main() -> None:
    config = load_config()
    ensure_models(config)

    events: queue.Queue = queue.Queue()
    sound_player = SoundPlayer(config)

    wake = WakeController(config, events, sound_player)
    stt = SpeechToText(config, sound_player)
    llm = LlmEngine(config)
    tts = TextToSpeech(config)
    actions = ActionRouter(config)
    pipeline = Pipeline(config, events, stt, llm, tts, actions, sound_player)

    threads = [
        threading.Thread(target=wake.run, daemon=True),
        threading.Thread(target=pipeline.run, daemon=True),
    ]

    for t in threads:
        t.start()

    print("Asistente activo. Usa wake-word o hotkey. (Ctrl+C para salir)")
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\nCerrando asistente...")


if __name__ == "__main__":
    main()
