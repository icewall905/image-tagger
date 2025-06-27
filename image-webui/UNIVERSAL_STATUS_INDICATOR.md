# Universal Status Indicator

## Overview

The Universal Status Indicator is a floating popup component that provides real-time progress updates for long-running operations across all pages of the Image Tagger WebUI. It persists during page navigation and automatically synchronizes with backend processing status.

## Features

- **Universal**: Works across all pages (folders, gallery, search, settings)
- **Persistent**: Maintains state during page navigation using localStorage
- **Real-time**: Updates progress every 2 seconds with live status from backend
- **Responsive**: Automatically appears when operations start and disappears when complete
- **Dismissible**: Users can manually close the indicator if needed

## Supported Operations

1. **Process All Images with AI** (`/api/settings/process-all-images`)
   - Processes all images without descriptions using AI vision models
   - Shows progress as: completed images / total images

2. **Scan All Folders for New Images** (`/api/settings/scan-all-folders`)
   - Scans all active folders for new images to add to the database
   - Shows progress as: completed folders / total folders

3. **Individual Folder Scan** (`/api/folders/{folder_id}/scan`)
   - Scans a specific folder for new images
   - Shows progress as: completed operations / total operations

## How It Works

### Frontend Components

1. **HTML Structure** (in `layout.html`):
   ```html
   <div id="universal-status-indicator" class="position-fixed d-none">
     <!-- Card with progress bar, status text, and close button -->
   </div>
   ```

2. **JavaScript Class** (`UniversalStatusIndicator`):
   - Manages show/hide functionality
   - Handles progress updates and polling
   - Persists state in localStorage
   - Provides API for starting operations

3. **CSS Styling** (in `style.css`):
   - Dark theme compatible
   - Smooth animations
   - Proper z-index for floating behavior

### Backend Integration

The indicator polls `/api/settings/processing-status` every 2 seconds to get:
```json
{
  "active": true,
  "progress": 45.5,
  "current_task": "Processing image 123 of 270",
  "total_tasks": 270,
  "completed_tasks": 123
}
```

### Usage

#### Starting Operations

Use the provided helper functions:

```javascript
// For "Process All Images with AI" button
startProcessAllImages();

// For "Scan All Folders" button  
startScanAllFolders();

// For individual folder scan
startScanFolder(folderId);
```

#### Manual Control

```javascript
// Show indicator manually
window.universalStatusIndicator.show();

// Hide indicator manually
window.universalStatusIndicator.hide();

// Start custom operation tracking
window.universalStatusIndicator.startProcessing('Custom Operation');
```

## Testing

### Test the Universal Status Indicator

1. **Navigate to Settings Page**: http://localhost:8491/settings

2. **Start an Operation**:
   - Click "Process All Images with AI" or "Scan All Folders for New Images"
   - The universal status indicator should appear in the top-right corner

3. **Test Persistence**:
   - While an operation is running, navigate to another page (e.g., Folders, Gallery)
   - The status indicator should remain visible and continue updating

4. **Test Individual Folder Scan**:
   - Go to Folders page: http://localhost:8491/folders
   - Click "Scan now" on any folder
   - The universal status indicator should appear and track progress

5. **Test Manual Dismissal**:
   - Click the "×" button on the status indicator
   - It should hide and clear the stored status

### Browser Console Testing

Open browser developer tools and check console for:
- "Universal Status Indicator initialized"
- "Found element: [element-id]" messages
- No error messages about missing elements

### API Testing

Test the status endpoint directly:
```bash
curl http://localhost:8491/api/settings/processing-status
```

Should return processing status JSON.

## Implementation Details

### localStorage Persistence

The indicator stores processing state in `localStorage` with key `universalProcessingStatus`:

```json
{
  "active": true,
  "progress": 45.5,
  "current_task": "Processing image 123 of 270",
  "total_tasks": 270,
  "completed_tasks": 123,
  "operation_type": "AI Processing"
}
```

### Polling Strategy

- Polls every 2 seconds when indicator is visible
- Stops polling when processing completes or indicator is hidden
- Handles network errors gracefully by continuing to poll

### Visual States

1. **Hidden**: `d-none` class, not visible
2. **Active**: Visible with spinning loader and animated progress bar
3. **Completed**: Shows 100% progress briefly before hiding (2-second delay)

## Customization

### Styling

Modify CSS in `frontend/static/css/style.css` under the `/* Universal Status Indicator Styles */` section.

### Positioning

Change the positioning by modifying the inline styles in `layout.html`:
```html
<div id="universal-status-indicator" class="position-fixed d-none" 
     style="top: 20px; right: 20px; z-index: 1060;">
```

### Polling Interval

Modify the polling interval in `main.js`:
```javascript
this.pollInterval = setInterval(() => {
    this.fetchStatus();
}, 2000); // Change 2000 to desired milliseconds
```

## Troubleshooting

### Indicator Not Appearing

1. Check browser console for JavaScript errors
2. Verify all required DOM elements exist
3. Check if operations are actually starting (network tab in dev tools)

### Status Not Updating

1. Verify backend API `/api/settings/processing-status` is responding
2. Check network requests in browser dev tools
3. Ensure localStorage is enabled in browser

### Styling Issues

1. Verify CSS is loading properly
2. Check for CSS conflicts with Bootstrap classes
3. Ensure dark theme variables are properly defined

## Future Enhancements

- Support for operation cancellation
- Detailed progress breakdown (e.g., current file being processed)
- Sound notifications when operations complete
- History of completed operations
- Multiple concurrent operation tracking
