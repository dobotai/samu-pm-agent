// App State
let conversationHistory = [];
let autoScroll = true;
let currentTab = 'chat';
let dailyUpdateData = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    adjustTextareaHeight();

    // Check server connection on load
    checkServerConnection();

    // Auto-resize textarea
    const textarea = document.getElementById('message-input');
    textarea.addEventListener('input', adjustTextareaHeight);

    // Handle Shift+Enter for new line, Enter for send
    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(e);
        }
    });

    // Initialize tab event listeners
    initializeTabs();
});

// Check if server is running
async function checkServerConnection() {
    try {
        const response = await fetch('/health', { method: 'GET' });
        if (response.ok) {
            console.log('Server connection OK');
        } else {
            showNotification('Server returned an error. Check server logs.', 'error');
        }
    } catch (error) {
        showNotification('Cannot connect to server. Is it running?', 'error');
        addMessage('assistant', '⚠️ **Server not connected**\n\nThe API server is not running. Please start it with:\n```\npython execution/api_server.py\n```\nOr run the `start_server.bat` file.');
    }
}

// Tab Initialization
function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const tab = btn.getAttribute('data-tab');
            switchTab(tab);
        });
    });
}

// Settings Management
function loadSettings() {
    const savedAutoScroll = localStorage.getItem('auto_scroll');
    if (savedAutoScroll !== null) {
        autoScroll = savedAutoScroll === 'true';
        document.getElementById('auto-scroll').checked = autoScroll;
    }
}

function saveSettings() {
    const newAutoScroll = document.getElementById('auto-scroll').checked;

    autoScroll = newAutoScroll;
    localStorage.setItem('auto_scroll', newAutoScroll);

    toggleSettings();
    showNotification('Settings saved successfully', 'success');
}

function toggleSettings() {
    const modal = document.getElementById('settings-modal');
    modal.classList.toggle('active');
}

// Chat Functions
async function sendMessage(event) {
    if (event) event.preventDefault();

    const input = document.getElementById('message-input');
    const message = input.value.trim();

    if (!message) return;

    // Add user message to chat
    addMessage('user', message);

    // Clear input
    input.value = '';
    adjustTextareaHeight();

    // Disable send button
    const sendBtn = document.getElementById('send-btn');
    const sendIcon = document.getElementById('send-icon');
    sendBtn.disabled = true;
    sendIcon.textContent = '⏳';

    // Show loading indicator
    const loadingId = showLoading();

    try {
        // Set up timeout (5 minutes for complex queries)
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 min timeout

        // Send request to API (no API key needed, using server-side auth)
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                client_name: 'youtube_agency'
            }),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        // Remove loading indicator
        removeLoading(loadingId);

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to get response');
        }

        const data = await response.json();

        // Add assistant response
        addMessage('assistant', data.response);

        // Store in conversation history
        conversationHistory.push({
            user: message,
            assistant: data.response
        });

    } catch (error) {
        removeLoading(loadingId);

        // Better error messages based on error type
        let errorMessage = error.message;
        if (error.name === 'AbortError') {
            errorMessage = 'Request timed out (5 min limit). Try a simpler query.';
        } else if (error.message === 'Failed to fetch') {
            errorMessage = 'Cannot connect to server. Make sure the server is running.';
        }

        showNotification(`Error: ${errorMessage}`, 'error');
        addMessage('assistant', `❌ Error: ${errorMessage}`);
    } finally {
        // Re-enable send button
        sendBtn.disabled = false;
        sendIcon.textContent = '📤';
        input.focus();
    }
}

function quickQuery(query) {
    const input = document.getElementById('message-input');
    input.value = query;
    input.focus();
    sendMessage();
}

function addMessage(role, text) {
    const chatContainer = document.getElementById('chat-container');

    // Remove welcome message if present
    const welcomeMessage = chatContainer.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const avatar = role === 'user' ? '👤' : '🤖';
    const author = role === 'user' ? 'You' : 'PM Assistant';
    const time = new Date().toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });

    messageDiv.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-author">${author}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-text">${formatText(text)}</div>
        </div>
    `;

    chatContainer.appendChild(messageDiv);

    if (autoScroll) {
        scrollToBottom();
    }
}

function showLoading() {
    const chatContainer = document.getElementById('chat-container');
    const loadingDiv = document.createElement('div');
    const loadingId = 'loading-' + Date.now();
    loadingDiv.id = loadingId;
    loadingDiv.className = 'message assistant';

    loadingDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-author">PM Assistant</span>
                <span class="message-time">typing...</span>
            </div>
            <div class="message-text">
                <div class="message-loading">
                    <div class="dot"></div>
                    <div class="dot"></div>
                    <div class="dot"></div>
                </div>
            </div>
        </div>
    `;

    chatContainer.appendChild(loadingDiv);

    if (autoScroll) {
        scrollToBottom();
    }

    return loadingId;
}

function removeLoading(loadingId) {
    const loadingDiv = document.getElementById(loadingId);
    if (loadingDiv) {
        loadingDiv.remove();
    }
}

function formatText(text) {
    // Convert markdown-style formatting to HTML
    let formatted = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // Bold
        .replace(/\*(.*?)\*/g, '<em>$1</em>')              // Italic
        .replace(/`(.*?)`/g, '<code>$1</code>')            // Inline code
        .replace(/\n/g, '<br>');                           // Line breaks

    return formatted;
}

function clearChat() {
    if (!confirm('Are you sure you want to clear the chat history?')) {
        return;
    }

    const chatContainer = document.getElementById('chat-container');
    chatContainer.innerHTML = `
        <div class="welcome-message">
            <h2>👋 Welcome to your PM Dashboard</h2>
            <p>Ask me anything about your projects, clients, or team:</p>
            <ul>
                <li>"Which editors are active today?"</li>
                <li>"Summarize the Taylor client channel"</li>
                <li>"Which clients need immediate attention?"</li>
                <li>"Show me recent messages from #suhaib-editing"</li>
                <li>"Send a message to Suhaib about the deadline"</li>
            </ul>
        </div>
    `;

    conversationHistory = [];
    showNotification('Chat cleared', 'success');
}

function scrollToBottom() {
    const chatContainer = document.getElementById('chat-container');
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function adjustTextareaHeight() {
    const textarea = document.getElementById('message-input');
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}

function showNotification(message, type = 'info') {
    // Simple notification system
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 2rem;
        right: 2rem;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#4f46e5'};
        color: white;
        border-radius: 0.5rem;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        z-index: 2000;
        animation: slideIn 0.3s ease-out;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add animation styles
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Tab Switching
function switchTab(tab) {
    currentTab = tab;

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tab) {
            btn.classList.add('active');
        }
    });

    // Show/hide containers
    const chatContainer = document.getElementById('chat-container');
    const dailyUpdateContainer = document.getElementById('daily-update-container');
    const inputContainer = document.querySelector('.input-container');
    const clearBtn = document.getElementById('clear-btn');
    const refreshBtn = document.getElementById('refresh-btn');

    if (tab === 'chat') {
        chatContainer.style.display = 'block';
        dailyUpdateContainer.style.display = 'none';
        inputContainer.style.display = 'block';
        clearBtn.style.display = 'inline-flex';
        refreshBtn.style.display = 'none';
    } else if (tab === 'daily-update') {
        chatContainer.style.display = 'none';
        dailyUpdateContainer.style.display = 'flex';
        inputContainer.style.display = 'none';
        clearBtn.style.display = 'none';
        refreshBtn.style.display = 'inline-flex';
    }
}

// Daily Update Functions
async function refreshDailyUpdate() {
    const refreshBtn = document.getElementById('refresh-btn');
    const contentDiv = document.getElementById('daily-update-content');

    // Disable button and show loading
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = '⏳ Updating...';

    contentDiv.innerHTML = `
        <div class="loading-state">
            <div class="message-loading">
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
            </div>
            <p>Fetching daily updates from Slack...</p>
        </div>
    `;

    try {
        // Send request to get daily update
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: 'Give me a comprehensive daily update. Summarize all important messages, activities, and updates across all Slack channels from today. Include any urgent items, deadlines, and status changes.',
                client_name: 'youtube_agency'
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to get daily update');
        }

        const data = await response.json();
        dailyUpdateData = data.response;

        // Update the timestamp
        const now = new Date();
        const timeStr = now.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
        document.getElementById('last-update-time').textContent = timeStr;

        // Display the update
        renderDailyUpdate(data.response);

        showNotification('Daily update refreshed', 'success');

    } catch (error) {
        contentDiv.innerHTML = `
            <div class="error-state">
                <h3>❌ Error</h3>
                <p>${error.message}</p>
                <p>Please try again or check the API connection.</p>
            </div>
        `;
        showNotification(`Error: ${error.message}`, 'error');
    } finally {
        // Re-enable button
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = '🔄 Update Dashboard';
    }
}

function renderDailyUpdate(content) {
    const contentDiv = document.getElementById('daily-update-content');

    // Format the content with proper styling
    const formattedContent = formatText(content);

    contentDiv.innerHTML = `
        <div class="update-card">
            <div class="update-card-header">
                <span class="update-card-icon">📊</span>
                <h3>Daily Summary</h3>
            </div>
            <div class="update-card-body">
                ${formattedContent}
            </div>
        </div>
    `;
}
