from typing import Any, Callable, List, Optional, Union

def run(app: Any, host: str = "127.0.0.1", port: int = 8000, 
       debug: bool = False, reload: bool = False, 
       workers: int = 1, **kwargs: Any) -> None: ...

class Config:
    app: Any
    host: str
    port: int
    reload: bool
    workers: int
    log_level: str
    access_log: bool
    proxy_headers: bool
    forwarded_allow_ips: Optional[str]
    root_path: str
    limit_concurrency: Optional[int]
    limit_max_requests: Optional[int]
    timeout_keep_alive: int
    
    def __init__(self, app: Any, **kwargs: Any): ...