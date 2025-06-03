"""Global variables for application state"""
from typing import Optional, Union

class AppState:
    """Class to store global application state"""
    def __init__(self):
        self.is_scanning = False
        self.current_task: Optional[str] = None
        self.task_progress: Union[int, float] = 0
        self.task_total = 0
        self.last_error: Optional[str] = None

# Global application state
app_state = AppState()

# Global observer for watching folders
observer = None
