from pathlib import Path
import pynvml
import re


def _free_vram_gb() -> float:
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return info.free / (1024 ** 3)
    except Exception:
        return 0.0


class LlmEngine:
    def __init__(self, config):
        cfg = config.llm
        self.config = cfg
        self.provider = cfg.get("provider", "local")
        self.web_search_enabled = cfg.get("web_search", False)
        self.searcher = None
        
        if self.web_search_enabled:
            from src.web_search import WebSearch
            self.searcher = WebSearch()
        
        if self.provider == "gemini":
            self._init_gemini(cfg)
        else:
            self._init_local(cfg)
    
    def _init_local(self, cfg):
        from llama_cpp import Llama
        
        model_path = Path(cfg["model_path"])
        free_gb = _free_vram_gb()
        n_gpu_layers = 0
        if free_gb >= cfg.get("vram_min_free_gb", 4):
            n_gpu_layers = cfg.get("n_gpu_layers_max", 0)

        self.llm = Llama(
            model_path=str(model_path),
            n_ctx=cfg.get("context_length", 4096),
            n_threads=cfg.get("n_threads", 8),
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
    
    def _init_gemini(self, cfg):
        import google.generativeai as genai
        
        api_key = cfg.get("gemini_api_key", "")
        if not api_key:
            raise ValueError("gemini_api_key requerida cuando provider='gemini'")
        
        genai.configure(api_key=api_key)
        model_name = cfg.get("gemini_model", "gemini-2.0-flash-exp")
        max_tokens = cfg.get("max_tokens", 256)
        self.gemini_model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": cfg.get("temperature", 0.7),
                "top_p": cfg.get("top_p", 0.9),
                "max_output_tokens": max_tokens,
            },
        )

    def generate(self, prompt: str, system_prompt: str = None) -> str:
        max_tokens = self.config.get("max_tokens", 256)
        temperature = self.config.get("temperature", 0.7)
        top_p = self.config.get("top_p", 0.9)
        
        if system_prompt is None:
            system_prompt = self.config.get("system_prompt", "")
        
        # Añadir capacidad de búsqueda al system prompt
        if self.web_search_enabled and self.searcher:
            system_prompt += "\n\nSi no conoces información actual o necesitas datos específicos, escribe [SEARCH:tu consulta aquí] y recibirás resultados de búsqueda."
        
        # Primera generación: detectar si pide búsqueda
        if self.provider == "gemini":
            full_prompt = f"{system_prompt} {prompt}" if system_prompt else prompt
            response = self.gemini_model.generate_content(full_prompt)
            reply = response.text.strip()
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            out = self.llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
                top_p=0.5,
                stop=["Usuario:", "Pregunta:", "\nHola", "modelo de", "asistente de IA"],
                repeat_penalty=1.2,
            )
            reply = out["choices"][0]["message"]["content"].strip()
        
        # Detectar y procesar búsquedas
        if self.web_search_enabled and self.searcher:
            search_pattern = r'\[SEARCH:(.*?)\]'
            searches = re.findall(search_pattern, reply, re.IGNORECASE)
            
            if searches:
                print(f"[LLM] Búsquedas detectadas: {searches}")
                search_results = []
                for query in searches:
                    query = query.strip()
                    result = self.searcher.search(query)
                    search_results.append(f"Búsqueda '{query}':\n{result}")
                
                # Segunda generación con contexto de búsqueda
                context = "\n\n".join(search_results)
                enhanced_prompt = f"Pregunta original: {prompt}\n\nResultados de búsqueda:\n{context}\n\nResponde basándote en esta información:"
                
                if self.provider == "gemini":
                    response = self.gemini_model.generate_content(enhanced_prompt)
                    reply = response.text.strip()
                else:
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": enhanced_prompt}
                    ]
                    out = self.llm.create_chat_completion(
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=0.3,
                        top_p=0.5,
                        stop=["Usuario:", "Pregunta:", "\nHola", "modelo de", "asistente de IA"],
                        repeat_penalty=1.2,
                    )
                    reply = out["choices"][0]["message"]["content"].strip()
        
        return reply
