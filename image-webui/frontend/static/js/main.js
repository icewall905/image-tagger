/**
 * Main JavaScript file for Image Tagger WebUI
 * Contains shared functionality across all pages
 */

// Initialize tooltips
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
});

/**
 * Helper function to show alerts
 * @param {string} type - Bootstrap alert type (success, danger, warning, info)
 * @param {string} message - Alert message
 * @param {string} container - CSS selector for the container to append the alert to
 * @param {number} timeout - Time in ms before the alert is automatically closed
 */
function showAlert(type, message, container = '.card-body:first', timeout = 5000) {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    // Insert at the top of the specified container
    $(container).prepend(alertHtml);
    
    // Auto-dismiss after specified timeout
    if (timeout > 0) {
        setTimeout(function() {
            $('.alert').alert('close');
        }, timeout);
    }
}

/**
 * Format a file path for display
 * If the path is too long, it will be truncated in the middle
 * @param {string} path - File path
 * @param {number} maxLength - Maximum length of the path
 * @returns {string} Formatted path
 */
function formatFilePath(path, maxLength = 40) {
    if (path.length <= maxLength) {
        return path;
    }
    
    const parts = path.split('/');
    const fileName = parts.pop();
    const extension = fileName.split('.').pop();
    
    // Always show the file name
    let displayPath = fileName;
    
    // Add as many parent directories as will fit
    let i = parts.length - 1;
    while (i >= 0 && (displayPath.length + parts[i].length + 4) <= maxLength) {
        displayPath = parts[i] + '/' + displayPath;
        i--;
    }
    
    // If we didn't include all directories, add an ellipsis
    if (i >= 0) {
        displayPath = '.../' + displayPath;
    }
    
    return displayPath;
}

/**
 * Generate a thumbnail element for an image
 * @param {string} src - Image source URL
 * @param {string} alt - Alt text for the image
 * @returns {HTMLElement} Image element
 */
function createThumbnail(src, alt = 'Image thumbnail') {
    const img = document.createElement('img');
    img.className = 'img-thumbnail placeholder';
    img.alt = alt;
    
    // Create a loading spinner
    const spinner = document.createElement('div');
    spinner.className = 'spinner-border text-primary';
    spinner.setAttribute('role', 'status');
    spinner.innerHTML = '<span class="visually-hidden">Loading...</span>';
    img.appendChild(spinner);
    
    // Load the actual image
    const actualImg = new Image();
    actualImg.onload = function() {
        img.src = src;
        img.classList.remove('placeholder');
        spinner.remove();
    };
    actualImg.onerror = function() {
        img.classList.remove('placeholder');
        img.classList.add('bg-secondary');
        spinner.remove();
        img.innerText = 'Image not found';
    };
    actualImg.src = src;
    
    return img;
}

/**
 * Convert a file size in bytes to a human-readable string
 * @param {number} bytes - File size in bytes
 * @returns {string} Human-readable file size
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Format a date string to a human-readable format
 * @param {string} dateString - ISO date string
 * @returns {string} Formatted date string
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString();
}

/**
 * Universal Status Indicator System
 * Provides a floating status indicator that persists across page navigation
 */
class UniversalStatusIndicator {
    constructor() {
        this.statusKey = 'universalProcessingStatus';
        this.pollInterval = null;
        this.isVisible = false;
        this.initializeElements();
        this.bindEvents();
        this.checkStoredStatus();
    }

    initializeElements() {
        this.indicator = document.getElementById('universal-status-indicator');
        this.progressBar = document.getElementById('status-progress-bar');
        this.currentTask = document.getElementById('status-current-task');
        this.progressText = document.getElementById('status-progress-text');
        this.closeButton = document.getElementById('status-indicator-close');
    }

    bindEvents() {
        // Handle close button
        this.closeButton.addEventListener('click', () => {
            this.hide();
            this.clearStoredStatus();
        });

        // Handle page visibility change to resume polling when page becomes visible
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.isVisible) {
                this.startPolling();
            }
        });
    }

    checkStoredStatus() {
        const storedStatus = localStorage.getItem(this.statusKey);
        if (storedStatus) {
            const status = JSON.parse(storedStatus);
            if (status.active) {
                this.show();
                this.startPolling();
            }
        }
    }

    show() {
        this.indicator.classList.remove('d-none');
        this.isVisible = true;
    }

    hide() {
        this.indicator.classList.add('d-none');
        this.isVisible = false;
        this.stopPolling();
    }

    updateProgress(status) {
        console.log('updateProgress called with:', status);
        // Update progress bar
        this.progressBar.style.width = `${status.progress}%`;
        this.progressBar.setAttribute('aria-valuenow', status.progress);

        // Update current task
        this.currentTask.textContent = status.current_task || 'Processing...';

        // Update progress text
        const progressText = `${status.completed_tasks || 0} / ${status.total_tasks || 0} completed`;
        console.log('Setting progress text to:', progressText);
        this.progressText.textContent = progressText;

        // Store status in localStorage for persistence
        localStorage.setItem(this.statusKey, JSON.stringify(status));

        // If processing is complete, hide the indicator after a brief delay
        if (!status.active && status.progress >= 100) {
            setTimeout(() => {
                this.hide();
                this.clearStoredStatus();
            }, 2000);
        }
    }

    startProcessing(operationType) {
        // Store initial processing state
        const initialStatus = {
            active: true,
            progress: 0,
            current_task: `Starting ${operationType}...`,
            total_tasks: 0,
            completed_tasks: 0,
            operation_type: operationType
        };
        
        localStorage.setItem(this.statusKey, JSON.stringify(initialStatus));
        this.show();
        this.updateProgress(initialStatus);
        this.startPolling();
    }

    startPolling() {
        this.stopPolling(); // Ensure no duplicate polling
        
        this.pollInterval = setInterval(() => {
            this.fetchStatus();
        }, 2000); // Poll every 2 seconds
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    fetchStatus() {
        console.log('fetchStatus called');
        fetch('/api/settings/processing-status')
            .then(response => response.json())
            .then(status => {
                console.log('Status received:', status);
                if (status.active) {
                    this.updateProgress(status);
                } else {
                    // Processing completed
                    status.progress = 100;
                    this.updateProgress(status);
                    this.stopPolling();
                }
            })
            .catch(error => {
                console.error('Error fetching status:', error);
                // Continue polling in case of temporary network issues
            });
    }

    clearStoredStatus() {
        localStorage.removeItem(this.statusKey);
    }
}

// Initialize the universal status indicator when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.universalStatusIndicator = new UniversalStatusIndicator();
    
    // Debug logging
    console.log('Universal Status Indicator initialized');
    
    // Test if all required elements exist
    const requiredElements = [
        'universal-status-indicator',
        'status-progress-bar', 
        'status-current-task',
        'status-progress-text',
        'status-indicator-close'
    ];
    
    requiredElements.forEach(id => {
        const element = document.getElementById(id);
        if (!element) {
            console.error(`Required element not found: ${id}`);
        } else {
            console.log(`Found element: ${id}`);
        }
    });
});

/**
 * Helper functions to start operations with universal status tracking
 */
function startUniversalOperation(operationType, apiEndpoint, successMessage) {
    // Start the status indicator
    window.universalStatusIndicator.startProcessing(operationType);
    
    // Make the API call
    return fetch(apiEndpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showAlert('success', successMessage || data.message);
        } else {
            throw new Error(data.message || 'Operation failed');
        }
        return data;
    })
    .catch(error => {
        console.error('Operation failed:', error);
        window.universalStatusIndicator.hide();
        window.universalStatusIndicator.clearStoredStatus();
        showAlert('danger', 'Error: ' + error.message);
        throw error;
    });
}

// Universal operation starters
function startProcessAllImages() {
    return startUniversalOperation(
        'AI Processing',
        '/api/settings/process-all-images',
        'AI processing started for all images without descriptions.'
    );
}

function startScanAllFolders() {
    return startUniversalOperation(
        'Folder Scanning',
        '/api/settings/scan-all-folders',
        'Started scanning all folders for new images.'
    );
}

function startScanFolder(folderId) {
    return startUniversalOperation(
        'Folder Scanning',
        `/api/folders/${folderId}/scan`,
        'Folder scan started in the background.'
    );
}
