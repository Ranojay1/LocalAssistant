import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
import torch
from pathlib import Path
import queue
import threading


class SpeechToText:
    def __init__(self, config, sound_player=None):
        self.cfg = config.stt
        self.sound_player = sound_player
        self.language = self.cfg.get("language", "es")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_path = Path(self.cfg["model_path"])
        if not model_path.exists():
            raise FileNotFoundError(
                f"STT model not found at {model_path}. Descarga el modelo CTranslate2 y colócalo ahí."
            )
        self.model = WhisperModel(
            str(model_path),
            device=device,
            local_files_only=True,
            compute_type="int8" if device == "cpu" else "float16",
        )
        self.sample_rate = config.app.get("sample_rate", 16000)
        self.silence_threshold = self.cfg.get("silence_threshold", 0.01)
        self.silence_duration = self.cfg.get("silence_duration", 1.5)
        self.max_record_seconds = self.cfg.get("max_record_seconds", 15)

    def record(self):
        audio_queue = queue.Queue()
        audio_chunks = []
        silence_samples = 0
        silence_limit = int(self.silence_duration * self.sample_rate)
        speech_detected = False
        speech_threshold = self.silence_threshold * 2  # Umbral más alto para detectar habla real
        
        def callback(indata, frames, time, status):
            if status:
                print(f"[STT] Audio status: {status}")
            audio_queue.put(indata.copy())
        
        stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=callback,
            blocksize=int(0.5 * self.sample_rate)
        )
        
        import time
        with stream:
            start_time = time.time()
            while True:
                try:
                    chunk = audio_queue.get(timeout=0.1)
                    audio_chunks.append(chunk[:, 0])
                    
                    # Check if silence
                    rms = np.sqrt(np.mean(chunk ** 2))
                    
                    # Detectar si hay habla real
                    if rms >= speech_threshold:
                        speech_detected = True
                        silence_samples = 0
                    elif speech_detected:
                        silence_samples += len(chunk)
                    
                    # Stop if silence detected (después de haber detectado habla) o max time
                    elapsed = time.time() - start_time
                    if speech_detected and silence_samples >= silence_limit and len(audio_chunks) > 3:
                        print("[STT] Silencio detectado, finalizando grabación")
                        if self.sound_player:
                            self.sound_player.play_stopped()
                        break
                    if elapsed >= self.max_record_seconds:
                        print("[STT] Tiempo máximo alcanzado")
                        break
                        
                except queue.Empty:
                    continue
        
        if not audio_chunks or not speech_detected:
            print("[STT] Sin habla detectada")
            return np.array([])
        
        return np.concatenate(audio_chunks)

    def transcribe(self):
        audio = self.record()
        if len(audio) == 0:
            print("[STT] Audio vacío, no enviando")
            return ""
        
        segments, _ = self.model.transcribe(
            audio,
            beam_size=self.cfg.get("beam_size", 5),
            language=self.language,
            task="transcribe",
        )
        text = " ".join(seg.text for seg in segments).strip()
        if not text:
            print("[STT] Texto vacío después de transcribir")
            return ""
        return text
