from queue import Queue
import platform
import os
import shutil
import subprocess


class Pipeline:
    def __init__(self, config, events: Queue, stt, llm, tts, actions, sound_player):
        self.events = events
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.actions = actions
        self.sound_player = sound_player
        self.intent_hints = getattr(actions, "hints", lambda: [])
        self.system_context = self._system_summary()

    def run(self):
        while True:
            event = self.events.get()
            if event.get("type") == "wake":
                self._handle_wake()

    def _handle_wake(self):
        try:
            print("[Pipeline] Grabando audio...")
            text = self.stt.transcribe()
            print(f"[Pipeline] Transcrito: {text}")
            
            if not text:
                print("[Pipeline] Sin texto, finalizando")
                return

            action_reply = self.actions.handle(text)
            if action_reply:
                print(f"[Pipeline] Acción ejecutada: {action_reply}")
                self.tts.speak(action_reply)
                # Si la acción pidió confirmación (actions.pending), escuchar sí/no y procesar
                attempts = 0
                while getattr(self.actions, "pending", None) and attempts < 2:
                    print("[Pipeline] Esperando confirmación...")
                    confirm = self.stt.transcribe()
                    self.sound_player.play_stopped()
                    print(f"[Pipeline] Confirmación: {confirm}")
                    if not confirm:
                        if hasattr(self.actions, "cancel_pending"):
                            self.actions.cancel_pending()
                        break
                    follow = self.actions.handle(confirm)
                    if follow:
                        print(f"[Pipeline] Acción ejecutada: {follow}")
                        self.tts.speak(follow)
                    attempts += 1
                return

            # Si no se ejecutó acción directa, pedir al LLM que clasifique a intent conocido
            predicted_intent = self._classify_intent(text)
            if predicted_intent:
                action_reply = self.actions.handle(predicted_intent)
                if action_reply:
                    print(f"[Pipeline] Acción por LLM: {action_reply}")
                    self.tts.speak(action_reply)
                    return

            print("[Pipeline] Generando respuesta LLM...")
            system_prompt = self.llm.config.get("system_prompt", "Responde breve.")
            hints = getattr(self.actions, "hints", lambda: [])()
            if hints:
                system_prompt = f"{system_prompt}\nAcciones disponibles: {', '.join(hints)}. Si el usuario pide una de ellas, responde ejecutando la acción en lugar de usar el LLM."
            if self.system_context:
                system_prompt = f"{system_prompt}\nDatos del equipo: {self.system_context}"
            system_prompt += "\n\nCRÍTICO: SOLO puedes usar comandos de esta lista EXACTA: " + ", ".join(hints or []) + ". Si necesitas ejecutar uno, escribe [CMD:nombre_exacto] AL PRINCIPIO. Ejemplo: '[CMD:administrador tareas] Revisa los procesos aquí.' NUNCA inventes comandos que no estén en la lista. Si no hay comando adecuado, responde sin ejecutar nada."
            reply = self.llm.generate(text, system_prompt=system_prompt)
            
            # Clean up if model continues dialogue
            if "Usuario:" in reply or "Pregunta:" in reply:
                reply = reply.split("Usuario:")[0].split("Pregunta:")[0].strip()
            
            print(f"[Pipeline] LLM respondió: {reply}")
            # Parsear comandos embebidos [CMD:...] y validar que existan
            cleaned_reply, embedded_cmds = self._extract_commands(reply)
            valid_hints = set(self.intent_hints())
            for cmd_name in embedded_cmds:
                if cmd_name in valid_hints:
                    executed = self.actions.handle(cmd_name)
                    if executed:
                        print(f"[Pipeline] Comando embebido ejecutado: {cmd_name}")
                else:
                    print(f"[Pipeline] Comando embebido ignorado (no existe): {cmd_name}")
            self.tts.speak(cleaned_reply)
            print("[Pipeline] Ciclo completado")
        except Exception as e:
            import traceback
            print(f"[Pipeline] Error: {e}")
            traceback.print_exc()

    def _classify_intent(self, text: str) -> str | None:
        hints = self.intent_hints()
        if not hints:
            return None

        norm_text = self._norm(text)

        # Filtra hints que aparezcan en el texto normalizado; si no hay ninguno, no clasifica
        candidate_hints = [h for h in hints if self._norm(h) in norm_text]
        if not candidate_hints:
            return None

        # Coincidencia directa
        for hint in candidate_hints:
            norm_hint = self._norm(hint)
            if norm_hint in norm_text:
                return hint

        options = ", ".join(candidate_hints)
        prompt = (
            "Opciones: "
            + options
            + ". Usuario: "
            + text
            + ". Responde solo una de las opciones exacta o 'none'."
        )
        try:
            prediction = self.llm.generate(
                prompt,
                system_prompt="Devuelve solo una opción exacta de la lista o 'none'.",
            )
            norm_pred = self._norm(prediction)
            if norm_pred in ("none", "ninguna"):
                return None

            # Empareja por igualdad normalizada
            for hint in candidate_hints:
                if self._norm(hint) == norm_pred:
                    return hint
        except Exception:
            return None
        return None

    def _norm(self, text: str) -> str:
        clean = text.lower().strip()
        for art in ("el ", "la ", "los ", "las ", "al ", "del "):
            if clean.startswith(art):
                clean = clean[len(art):]
                break
        return clean.strip(".,!? ")

    def _system_summary(self) -> str:
        try:
            uname = platform.uname()
            os_name = f"{uname.system} {uname.release}".strip()
            cpu, cores = self._cpu_info()

            # RAM y disco (best-effort, sin deps externas)
            total_ram_gb = None
            try:
                import psutil  # type: ignore

                total_ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
            except Exception:
                total_ram_gb = None

            disk_total = None
            disk_free = None
            try:
                drive = os.path.splitdrive(os.getcwd())[0] or "/"
                usage = shutil.disk_usage(drive)
                disk_total = round(usage.total / (1024 ** 3), 1)
                disk_free = round(usage.free / (1024 ** 3), 1)
            except Exception:
                pass

            gpus = self._gpu_names()

            parts = [f"OS: {os_name}", f"CPU: {cpu} ({cores} hilos)"]
            if total_ram_gb:
                parts.append(f"RAM: {total_ram_gb} GB")
            if disk_total and disk_free is not None:
                parts.append(f"Disco: {disk_free} GB libres de {disk_total} GB")
            if gpus:
                parts.append(f"GPU: {', '.join(gpus)}")
            return ", ".join(parts)
        except Exception:
            return ""

    def _gpu_names(self):
        try:
            cmd = [
                "powershell",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"
            ]
            out = subprocess.check_output(cmd, text=True, timeout=5)
            names = [line.strip() for line in out.splitlines() if line.strip()]
            return names[:3]  # limitar para no alargar el prompt
        except Exception:
            return []

    def _cpu_info(self):
        # Intento 1: PowerShell para obtener el nombre amigable
        try:
            cmd = [
                "powershell",
                "-Command",
                "Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name"
            ]
            out = subprocess.check_output(cmd, text=True, timeout=5).strip()
            name = out if out else "cpu-desconocido"
        except Exception:
            name = platform.uname().processor or "cpu-desconocido"

        cores = os.cpu_count() or 0
        return name, cores

    def _extract_commands(self, text: str):
        """Extrae comandos embebidos [CMD:nombre] y devuelve texto limpio + lista de comandos."""
        import re
        pattern = r"\[CMD:([^\]]+)\]"
        commands = re.findall(pattern, text)
        cleaned = re.sub(pattern, "", text).strip()
        return cleaned, commands
