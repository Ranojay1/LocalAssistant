import json
from pathlib import Path
from datetime import datetime


class UserMemory:
    def __init__(self, data_path="data.json"):
        self.data_path = Path(data_path)
        self.data = self._load()
        self.onboarding_questions = [
            ("name", "¿Cómo te llamas?"),
            ("age", "¿Cuántos años tienes?"),
            ("occupation", "¿A qué te dedicas?"),
            ("location", "¿Dónde vives?"),
            ("interests", "¿Cuáles son tus intereses? Di varios separados por comas."),
            ("preferences", "¿Tienes alguna preferencia que deba recordar?")
        ]
        self.current_question_index = 0
    
    def _load(self):
        if not self.data_path.exists():
            return self._default_data()
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return self._default_data()
    
    def _default_data(self):
        return {
            "user": {
                "name": "",
                "age": "",
                "occupation": "",
                "location": "",
                "interests": [],
                "preferences": {}
            },
            "system": {
                "last_updated": "",
                "interaction_count": 0
            }
        }
    
    def save(self):
        self.data["system"]["last_updated"] = datetime.now().isoformat()
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def is_complete(self):
        """Verifica si los datos básicos están completos"""
        user = self.data.get("user", {})
        return all([
            user.get("name"),
            user.get("age"),
            user.get("occupation"),
            user.get("location"),
            user.get("interests"),
            user.get("preferences")
        ])
    
    def get_next_question(self):
        """Obtiene la siguiente pregunta de onboarding"""
        user = self.data.get("user", {})
        for field, question in self.onboarding_questions:
            if not user.get(field):
                return field, question
        return None, None
    
    def update_field(self, field, value):
        """Actualiza un campo de usuario"""
        if field in self.data["user"]:
            # Para interests, convertir a lista
            if field == "interests" and isinstance(value, str):
                value = [item.strip() for item in value.split(",") if item.strip()]
            self.data["user"][field] = value
            self.save()
            return True
        return False
    
    def get_context(self):
        """Obtiene resumen de datos del usuario para el LLM"""
        user = self.data.get("user", {})
        parts = []
        if user.get("name"):
            parts.append(f"Usuario: {user['name']}")
        if user.get("age"):
            parts.append(f"Edad: {user['age']}")
        if user.get("occupation"):
            parts.append(f"Ocupación: {user['occupation']}")
        if user.get("location"):
            parts.append(f"Ubicación: {user['location']}")
        if user.get("interests"):
            parts.append(f"Intereses: {', '.join(user['interests'])}")
        
        return "\n".join(parts) if parts else ""
    
    def increment_interactions(self):
        self.data["system"]["interaction_count"] = self.data["system"].get("interaction_count", 0) + 1
        self.save()
