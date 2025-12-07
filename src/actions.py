import json
import subprocess
from pathlib import Path
import re


class ActionRouter:
    def __init__(self, config):
        self.cfg = config.actions
        self.commands_path = Path("commands.json")
        # Cargar comandos desde commands.json si existe, sino usar config
        if self.commands_path.exists():
            self.commands = json.loads(self.commands_path.read_text(encoding="utf-8"))
        else:
            self.commands = self.cfg.get("commands", {})
        self.pending = None  # (intent, command)
        self.config_path = Path("config.json") if Path("config.json").exists() else None
        self.affirmatives = ("si", "sí", "vale", "ok", "okay", "claro", "afirma")
        self.negatives = ("no", "nel", "nunca", "cancela", "cancelar")
        # Alias: "abre discord" -> "discord" para disparar por nombre directo
        self.aliases = {}
        for intent in self.commands:
            alias = intent
            if intent.startswith("abre "):
                alias = intent.replace("abre ", "", 1)
            self.aliases[alias.strip()] = intent

    def handle(self, text: str) -> str | None:
        low = text.lower()
        if self.cfg.get("enable_shutdown") and "apagate" in low:
            return self._shutdown()
        if self.cfg.get("enable_inventory") and ("que lleva mi pc" in low or "que tiene mi pc" in low):
            return self._inventory()

        # Si hay una URL en el texto, abre en navegador por defecto
        url = self._extract_url(low)
        if url:
            return self._run_command(f'start "" "{url}"', label=url)

        # Coincide intents contra un allowlist de comandos
        for intent, command in self.commands.items():
            if intent in low:
                return self._run_command(command, label=intent)

        # Coincide por alias (solo nombre de la app)
        for alias, intent in self.aliases.items():
            if alias and alias in low and intent in self.commands:
                return self._run_command(self.commands[intent], label=alias)

        # Confirmaciones pendientes
        if self.pending:
            if any(word in low for word in self.affirmatives):
                intent, command = self.pending
                self.commands[intent] = command
                self._persist_command(intent, command)
                self.pending = None
                return self._run_command(command)
            if any(word in low for word in self.negatives):
                self.pending = None
                return "No guardo el comando."
            return "Confirma con sí o no."
        return None

    def hints(self):
        hints = []
        if self.cfg.get("enable_shutdown"):
            hints.append("apagate")
        if self.cfg.get("enable_inventory"):
            hints.append("que lleva mi pc")
        hints.extend(self.commands.keys())
        hints.extend(self.aliases.keys())
        return sorted(set(hints))

    def _shutdown(self) -> str:
        subprocess.Popen(["shutdown", "/s", "/t", "3"], shell=True)
        return "Apagando el equipo en 3 segundos."

    def _inventory(self) -> str:
        try:
            script = (
                "Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model;"
                "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors;"
                "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM;"
                "Get-CimInstance Win32_PhysicalMemory | Group-Object -Property Manufacturer,Capacity |"
                " Select-Object @{Name='DIMMs';Expression={$_.Count}}, @{Name='CapacityGB';Expression={[math]::Round(($_.Group | Measure-Object -Property Capacity -Sum).Sum/1GB,2)}};"
                "Get-Volume | Where-Object {$_.DriveLetter} | Select-Object DriveLetter,SizeRemaining,Size"
            )
            result = subprocess.check_output([
                "powershell",
                "-Command",
                script,
            ], text=True, timeout=10)
            return "Resumen del PC:\n" + result.strip()
        except Exception:
            return "No pude leer el inventario ahora."

    def _run_command(self, command: str, label: str | None = None) -> str:
        try:
            subprocess.Popen(command, shell=True)
            if label:
                return f"Se ha abierto {label}"
            return f"Ejecutando: {command}"
        except Exception:
            return "No pude ejecutar el comando autorizado."


    def cancel_pending(self):
        self.pending = None

    def _persist_command(self, intent: str, command: str):
        try:
            self.commands_path.write_text(
                json.dumps(self.commands, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    def _extract_url(self, text: str) -> str | None:
        match = re.search(r"https?://\S+", text)
        if match:
            return match.group(0)
        return None
