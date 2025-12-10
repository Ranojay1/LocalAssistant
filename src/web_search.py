import requests
from bs4 import BeautifulSoup


class WebSearch:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    
    def search(self, query: str, max_results: int = 3) -> str:
        """Busca en DuckDuckGo y devuelve resumen de resultados"""
        print(f"[WebSearch] Buscando: '{query}'")
        try:
            url = "https://html.duckduckgo.com/html/"
            params = {"q": query}
            response = requests.post(url, data=params, headers=self.headers, timeout=5)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            
            for result in soup.select(".result")[:max_results]:
                title_elem = result.select_one(".result__title")
                snippet_elem = result.select_one(".result__snippet")
                
                if title_elem and snippet_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True)
                    results.append(f"{title}: {snippet}")
            
            if not results:
                print("[WebSearch] No se encontraron resultados")
                return "No se encontraron resultados relevantes."
            
            print(f"[WebSearch] Encontrados {len(results)} resultados")
            return "\n\n".join(results)
        
        except Exception as e:
            print(f"[WebSearch] Error: {e}")
            return f"Error al buscar: {e}"
