"""Global variables for application state"""
from typing import Optional, Union

class AppState:
    """Class to store global application state"""
    def __init__(self):
        self.is_scanning = False
        self.current_task: Optional[str] = None
        self.task_progress: Union[int, float] = 0
        self.task_total = 0
        self.completed_tasks = 0
        self.last_error: Optional[str] = None
    
    def update(self, data: dict):
        """Update the app state with new data"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

# Global application state
app_state = AppState()

# Global observer for watching folders
observer = None
