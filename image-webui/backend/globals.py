"""Global variables for application state"""

class AppState:
    """Class to store global application state"""
    def __init__(self):
        self.is_scanning = False
        self.current_task = None
        self.task_progress = 0
        self.task_total = 0
        self.last_error = None

# Global application state
app_state = AppState()

# Global observer for watching folders
observer = None
