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
