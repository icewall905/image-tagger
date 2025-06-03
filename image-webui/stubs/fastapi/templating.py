# Type stubs for FastAPI templating
from typing import Any, Dict, Optional

class Jinja2Templates:
    def __init__(self, directory: str): ...
    def TemplateResponse(self, name: str, context: Dict[str, Any], 
                       status_code: int = 200, 
                       headers: Optional[Dict[str, str]] = None, 
                       media_type: Optional[str] = None, 
                       background: Optional[Any] = None): ...