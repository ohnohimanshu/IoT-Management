/**
 * Alerts Management JavaScript
 * Handles fetching, displaying, and marking alerts as read
 */

// Fetch alerts from the server
async function fetchAlerts() {
    try {
        const response = await fetch('/mailer/alerts/');
        if (!response.ok) {
            throw new Error(`Failed to fetch alerts: ${response.status}`);
        }
        const alerts = await response.json();
        displayAlerts(alerts);
        updateAlertCount(alerts.filter(alert => !alert.is_read).length);
        updateUnreadAlertsBadge();
        return alerts;
    } catch (error) {
        console.error('Error fetching alerts:', error);
        return [];
    }
}

// Display alerts in the alerts container
function displayAlerts(alerts) {
    const alertsContainer = document.getElementById('alertsContainer');
    if (!alertsContainer) return;
    
    // Clear existing alerts
    alertsContainer.innerHTML = '';
    
    if (alerts.length === 0) {
        alertsContainer.innerHTML = '<div class="p-4 text-gray-500 text-center">No alerts found</div>';
        return;
    }
    
    // Group alerts by date
    const groupedAlerts = groupAlertsByDate(alerts);
    
    // Create alert elements
    for (const [date, dateAlerts] of Object.entries(groupedAlerts)) {
        // Add date header
        const dateHeader = document.createElement('div');
        dateHeader.className = 'px-4 py-2 bg-gray-100 font-semibold text-sm';
        dateHeader.textContent = date;
        alertsContainer.appendChild(dateHeader);
        
        // Add alerts for this date
        dateAlerts.forEach(alert => {
            const alertElement = createAlertElement(alert);
            alertsContainer.appendChild(alertElement);
        });
    }
}

// Group alerts by date
function groupAlertsByDate(alerts) {
    const grouped = {};
    
    alerts.forEach(alert => {
        const date = new Date(alert.timestamp);
        const dateString = date.toLocaleDateString();
        
        if (!grouped[dateString]) {
            grouped[dateString] = [];
        }
        
        grouped[dateString].push(alert);
    });
    
    return grouped;
}

// Create a single alert element
function createAlertElement(alert) {
    const alertElement = document.createElement('div');
    alertElement.className = `p-4 border-b border-gray-200 ${alert.is_read ? 'bg-white' : 'bg-blue-50'}`;
    alertElement.dataset.alertId = alert.id;
    
    // Set severity class
    let severityClass = '';
    switch (alert.severity) {
        case 'high':
            severityClass = 'text-red-600';
            break;
        case 'medium':
            severityClass = 'text-orange-500';
            break;
        case 'low':
            severityClass = 'text-blue-500';
            break;
        default:
            severityClass = 'text-gray-600';
    }
    
    // Format timestamp
    const timestamp = new Date(alert.timestamp);
    const timeString = timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    // Create alert content
    alertElement.innerHTML = `
        <div class="flex justify-between items-start">
            <div>
                <h3 class="font-semibold ${severityClass}">${alert.title}</h3>
                <p class="text-sm text-gray-600 mt-1">${alert.message}</p>
                <div class="flex items-center mt-2">
                    <span class="text-xs text-gray-500">${timeString}</span>
                    ${alert.device_name ? `<span class="text-xs bg-gray-200 rounded-full px-2 py-1 ml-2">${alert.device_name}</span>` : ''}
                </div>
            </div>
            <button class="mark-read-btn text-sm text-indigo-600 hover:text-indigo-800" 
                    ${alert.is_read ? 'style="display:none;"' : ''}
                    onclick="markAlertAsRead(${alert.id})">
                Mark as Read
            </button>
        </div>
    `;
    
    return alertElement;
}

// Mark a single alert as read
async function markAlertAsRead(alertId) {
    try {
        const response = await fetch(`/mailer/alerts/${alertId}/mark-read/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        if (!response.ok) {
            throw new Error(`Failed to mark alert as read: ${response.status}`);
        }
        
        // Update UI
        const alertElement = document.querySelector(`[data-alert-id="${alertId}"]`);
        if (alertElement) {
            alertElement.classList.remove('bg-blue-50');
            alertElement.classList.add('bg-white');
            const markReadBtn = alertElement.querySelector('.mark-read-btn');
            if (markReadBtn) markReadBtn.style.display = 'none';
        }
        
        // Update unread count
        updateUnreadCount();
        
        return true;
    } catch (error) {
        console.error('Error marking alert as read:', error);
        return false;
    }
}

// Mark all alerts as read
async function markAllAlertsAsRead() {
    try {
        const response = await fetch('/mailer/alerts/mark-all-read/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        if (!response.ok) {
            throw new Error(`Failed to mark all alerts as read: ${response.status}`);
        }
        
        // Update UI
        const alertElements = document.querySelectorAll('[data-alert-id]');
        alertElements.forEach(element => {
            element.classList.remove('bg-blue-50');
            element.classList.add('bg-white');
            const markReadBtn = element.querySelector('.mark-read-btn');
            if (markReadBtn) markReadBtn.style.display = 'none';
        });
        
        // Update unread count
        updateUnreadCount(0);
        
        return true;
    } catch (error) {
        console.error('Error marking all alerts as read:', error);
        return false;
    }
}

// Filter alerts by severity
function filterAlerts(severity) {
    const alertElements = document.querySelectorAll('[data-alert-id]');
    let visibleCount = 0;
    
    alertElements.forEach(element => {
        const alertTitle = element.querySelector('h3');
        const isSeverityMatch = 
            (severity === 'all') ||
            (severity === 'high' && alertTitle.classList.contains('text-red-600')) ||
            (severity === 'medium' && alertTitle.classList.contains('text-orange-500')) ||
            (severity === 'low' && alertTitle.classList.contains('text-blue-500'));
        
        if (isSeverityMatch) {
            element.style.display = 'block';
            visibleCount++;
        } else {
            element.style.display = 'none';
        }
    });
    
    // Update visible count
    const visibleCountElement = document.getElementById('visibleAlertCount');
    if (visibleCountElement) {
        visibleCountElement.textContent = visibleCount;
    }
    
    // Show/hide date headers based on visible alerts
    updateDateHeadersVisibility();
}

// Update date headers visibility based on visible alerts
function updateDateHeadersVisibility() {
    const alertsContainer = document.getElementById('alertsContainer');
    if (!alertsContainer) return;
    
    const dateHeaders = alertsContainer.querySelectorAll('.bg-gray-100');
    
    dateHeaders.forEach(header => {
        let nextElement = header.nextElementSibling;
        let hasVisibleAlert = false;
        
        // Check all alerts until the next date header
        while (nextElement && !nextElement.classList.contains('bg-gray-100')) {
            if (nextElement.style.display !== 'none' && nextElement.hasAttribute('data-alert-id')) {
                hasVisibleAlert = true;
                break;
            }
            nextElement = nextElement.nextElementSibling;
        }
        
        header.style.display = hasVisibleAlert ? 'block' : 'none';
    });
}

// Update the unread alert count in the alerts section
function updateUnreadCount(count = null) {
    if (count === null) {
        // Count unread alerts in the DOM
        const unreadAlerts = document.querySelectorAll('[data-alert-id].bg-blue-50');
        count = unreadAlerts.length;
    }
    
    // Update badge count in the alerts section
    const unreadBadge = document.getElementById('unreadAlertBadge');
    if (unreadBadge) {
        unreadBadge.textContent = count;
        unreadBadge.style.display = count > 0 ? 'flex' : 'none';
    }
    
    // Also update the sidebar badge
    updateUnreadAlertsBadge(count);
}

// Update the unread alerts badge in the sidebar
function updateUnreadAlertsBadge(count = null) {
    if (count === null) {
        // If count not provided, fetch it from the server
        fetch('/mailer/alerts/unread-count/')
            .then(response => response.json())
            .then(data => {
                updateSidebarBadge(data.count);
            })
            .catch(error => {
                console.error('Error fetching unread count:', error);
            });
    } else {
        updateSidebarBadge(count);
    }
}

// Update the sidebar badge with the given count
function updateSidebarBadge(count) {
    const sidebarBadge = document.getElementById('unreadAlertBadge');
    if (sidebarBadge) {
        sidebarBadge.textContent = count;
        sidebarBadge.style.display = count > 0 ? 'flex' : 'none';
    }
}

// Get CSRF token from cookies
function getCsrfToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Initialize alerts when the page loads
document.addEventListener('DOMContentLoaded', () => {
    // Initial fetch
    fetchAlerts();
    
    // Set up event listeners for filter buttons
    const filterButtons = document.querySelectorAll('.alert-filter-btn');
    filterButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove active class from all buttons
            filterButtons.forEach(btn => btn.classList.remove('bg-indigo-600', 'text-white'));
            filterButtons.forEach(btn => btn.classList.add('bg-gray-200', 'text-gray-700'));
            
            // Add active class to clicked button
            button.classList.remove('bg-gray-200', 'text-gray-700');
            button.classList.add('bg-indigo-600', 'text-white');
            
            // Filter alerts
            filterAlerts(button.dataset.severity);
        });
    });
    
    // Set up event listener for mark all as read button
    const markAllReadBtn = document.getElementById('markAllReadBtn');
    if (markAllReadBtn) {
        markAllReadBtn.addEventListener('click', markAllAlertsAsRead);
    }
    
    // Refresh alerts periodically (every 60 seconds)
    setInterval(fetchAlerts, 60000);
});