from queue import Queue
import platform
import os
import shutil
import subprocess
from collections import deque
from datetime import datetime, timedelta
from src.user_memory import UserMemory


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
        self.conversation_history = deque(maxlen=20)  # Últimos 20 turnos (10 min aprox)
        self.user_memory = UserMemory()
        self.onboarding_mode = not self.user_memory.is_complete()
        self.waiting_for_field = None
        self.onboarding_started = False

    def run(self):
        while True:
            event = self.events.get()
            if event.get("type") == "wake":
                # Onboarding en la primera llamada
                if self.onboarding_mode and not self.onboarding_started:
                    self._run_onboarding()
                else:
                    self._handle_wake()

    def _handle_wake(self):
        try:
            print("[Pipeline] Grabando audio...")
            text = self.stt.transcribe()
            print(f"[Pipeline] Transcrito: {text}")
            
            if not text:
                print("[Pipeline] Sin texto, finalizando")
                return

            # LLM decide TODO (sin clasificación previa)
            print("[Pipeline] Generando respuesta LLM...")
            system_prompt = self.llm.config.get("system_prompt", "Responde breve.")
            hints = getattr(self.actions, "hints", lambda: [])()
            
            if self.system_context:
                system_prompt = f"{system_prompt}\nDatos del equipo: {self.system_context}"
            
            # Instrucciones claras para comandos
            if hints:
                system_prompt += f"\n\nPuedes ejecutar estos comandos: {', '.join(hints)}."
                system_prompt += "\n\nPara ABRIR/EJECUTAR una aplicación: escribe [CMD:nombre_exacto]."
                system_prompt += "\nEjemplo: 'Abre Discord' → '[CMD:discord] Abriendo Discord'"
                system_prompt += "\nEjemplo: 'Necesito el administrador de tareas' → '[CMD:administrador tareas] Aquí está'"
            
            # Instrucciones para búsquedas web
            web_enabled = self.llm.config.get("web_search", False)
            if web_enabled:
                system_prompt += "\n\nPara BUSCAR EN INTERNET: escribe [SEARCH:consulta]."
                system_prompt += "\nEjemplo: 'Busca qué es GitHub' → '[SEARCH:qué es GitHub]'"
                system_prompt += "\nEjemplo: '¿Quién ganó el mundial?' → '[SEARCH:mundial fútbol ganador 2022]'"
                system_prompt += "\n\nDISTINGUE: 'Abre Epic Games' = [CMD:epic games] | 'Busca qué es Epic Games' = [SEARCH:qué es Epic Games]"
            
            system_prompt += "\n\nNUNCA inventes comandos que no estén en la lista."
            
            # Añadir memoria del usuario
            user_context = self.user_memory.get_context()
            if user_context:
                system_prompt += f"\n\nDatos del usuario:\n{user_context}"
            
            # Añadir historial de conversación
            history_context = self._get_recent_history()
            if history_context:
                system_prompt += f"\n\nHistorial reciente:\n{history_context}"
            
            reply = self.llm.generate(text, system_prompt=system_prompt)
            
            # Guardar en historial e incrementar interacciones
            self._add_to_history(text, reply)
            self.user_memory.increment_interactions()
            
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
        lower_text = text.lower()
        
        # Detectar búsquedas web y preguntas (no ejecutar comandos)
        search_words = ["busca", "búsqueda", "investiga", "consulta en", "mira en internet", "en internet", "en la web"]
        question_words = ["qué es", "quién", "cómo", "cuándo", "dónde", "por qué", "cuál", "explica", "dime sobre", "qué significa", "para qué"]
        
        is_search = any(sw in lower_text for sw in search_words)
        is_question = any(qw in lower_text for qw in question_words)
        
        if is_search or is_question:
            return None

        # Filtra hints que aparezcan en el texto normalizado; si no hay ninguno, no clasifica
        candidate_hints = [h for h in hints if self._norm(h) in norm_text]
        if not candidate_hints:
            return None

        # Coincidencia directa solo si es comando explícito
        action_words = ["abre", "abrir", "inicia", "ejecuta", "lanza", "cierra", "activa"]
        has_action = any(aw in lower_text for aw in action_words)
        
        if has_action:
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
            + ". Si es pregunta, responde 'none'. Si es comando para ejecutar, responde la opción exacta."
        )
        try:
            prediction = self.llm.generate(
                prompt,
                system_prompt="Si es pregunta sobre algo, devuelve 'none'. Si es comando para ejecutar, devuelve la opción exacta de la lista.",
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
    
    def _run_onboarding(self):
        """Ejecuta proceso de onboarding completo al inicio"""
        self.onboarding_started = True
        print("[Memory] Iniciando onboarding...")
        
        # Mensaje de bienvenida
        welcome = "Hola. Voy a hacerte unas preguntas para conocerte mejor. Sé breve y conciso."
        self.tts.speak(welcome)
        
        # Iterar por cada pregunta
        for field, question in self.user_memory.onboarding_questions:
            print(f"[Memory] Pregunta: {question}")
            self.tts.speak(question)
            
            # Escuchar respuesta (sin sonido de listening)
            answer = self.stt.transcribe()
            
            if answer:
                self.user_memory.update_field(field, answer)
                print(f"[Memory] Guardado: {field} = {answer}")
            else:
                print(f"[Memory] Sin respuesta para: {field}")
        
        # Completar onboarding
        self.onboarding_mode = False
        completion_msg = "Perfecto. Ya te conozco mejor."
        print("[Memory] Onboarding completo")
        self.tts.speak(completion_msg)
    
    def _add_to_history(self, user_text: str, assistant_reply: str):
        """Añade una interacción al historial con timestamp"""
        timestamp = datetime.now()
        self.conversation_history.append({
            "time": timestamp,
            "user": user_text,
            "assistant": assistant_reply
        })
    
    def _get_recent_history(self) -> str:
        """Obtiene historial de los últimos 10 minutos"""
        if not self.conversation_history:
            return ""
        
        cutoff_time = datetime.now() - timedelta(minutes=10)
        recent = [entry for entry in self.conversation_history if entry["time"] > cutoff_time]
        
        if not recent:
            return ""
        
        history_lines = []
        for entry in recent[-10:]:  # Máximo 10 interacciones
            history_lines.append(f"Usuario: {entry['user']}")
            history_lines.append(f"Tú: {entry['assistant']}")
        
        return "\n".join(history_lines)

    def _extract_commands(self, text: str):
        """Extrae comandos embebidos [CMD:nombre] y devuelve texto limpio + lista de comandos."""
        import re
        pattern = r"\[CMD:([^\]]+)\]"
        commands = re.findall(pattern, text)
        cleaned = re.sub(pattern, "", text).strip()
        return cleaned, commands
