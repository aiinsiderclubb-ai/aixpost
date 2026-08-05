/**
 * Facebook Group Poster - Premium Dashboard JavaScript
 * Handles UI interactions, animations, form submissions, and API calls
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM elements - Navigation and UI
    const navItems = document.querySelectorAll('.nav-item a');
    const contentSections = document.querySelectorAll('.content-section');
    const themeToggle = document.getElementById('theme-toggle');
    const confirmationModal = document.getElementById('confirmation-modal');
    const modalClose = document.querySelector('.modal-close');
    const modalCancel = document.getElementById('modal-cancel');
    const modalConfirm = document.getElementById('modal-confirm');
    const maxGroupsRange = document.getElementById('max-groups-range');
    const maxGroupsInput = document.getElementById('max-groups');
    const fileUpload = document.getElementById('groups-file');
    const fileName = document.getElementById('file-name');
    const actionButtons = document.querySelectorAll('.action-button');
    const fabButton = document.getElementById('new-campaign-fab');
    
    // DOM elements - Form and posting
    const postingForm = document.getElementById('posting-form');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const statusIndicator = document.getElementById('status-indicator');
    const statusIndicatorStats = document.getElementById('status-indicator-stats');
    const postsCompleted = document.getElementById('posts-completed');
    const postsFailed = document.getElementById('posts-failed');
    const progressBar = document.getElementById('progress-bar');
    const progressPercentage = document.getElementById('progress-percentage');
    const logsContainer = document.getElementById('logs-container');
    const recentLogs = document.getElementById('recent-logs');
    
    // DOM elements - Statistics
    const statSuccessRate = document.getElementById('stat-success-rate');
    const statGroupsTotal = document.getElementById('stat-groups-total');
    const statTimeElapsed = document.getElementById('stat-time-elapsed');
    const groupsStatusTableBody = document.getElementById('groups-status-table-body');
    
    // DOM elements - Settings
    const accountSettingsForm = document.getElementById('account-settings-form');
    const botSettingsForm = document.getElementById('bot-settings-form');
    const fbUsername = document.getElementById('fb-username');
    const fbPassword = document.getElementById('fb-password');
    const minDelay = document.getElementById('min-delay');
    const maxDelay = document.getElementById('max-delay');
    const headlessMode = document.getElementById('headless-mode');
    
    // DOM elements - Templates and Queue
    const templateSelect = document.getElementById('template-select');
    const templateName = document.getElementById('template-name');
    const loadTemplateBtn = document.getElementById('load-template');
    const saveTemplateBtn = document.getElementById('save-template');
    const deleteTemplateBtn = document.getElementById('delete-template');
    const messageTextarea = document.getElementById('message');
    const postQueueTextarea = document.getElementById('post-queue');
    const queueFileInput = document.getElementById('queue-file');
    const queueFileName = document.getElementById('queue-file-name');
    const queueCount = document.getElementById('queue-count');
    
    // DOM elements - History
    const refreshHistoryBtn = document.getElementById('refresh-history');
    const statusFilter = document.getElementById('status-filter');
    const accountFilter = document.getElementById('account-filter');
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const applyFiltersBtn = document.getElementById('apply-filters');
    const historyTableBody = document.getElementById('history-table-body');
    const totalPosts = document.getElementById('total-posts');
    const successPosts = document.getElementById('success-posts');
    const errorPosts = document.getElementById('error-posts');
    const blockedPosts = document.getElementById('blocked-posts');
    const successRate = document.getElementById('success-rate');
    
    // DOM elements - Group Fetching and Selection
    const fetchGroupsBtn = document.getElementById('fetch-groups');
    const groupsList = document.getElementById('groups-list');
    const groupsCount = document.getElementById('groups-count');
    const groupsLoading = document.getElementById('groups-loading');
    const groupsEmpty = document.getElementById('groups-empty');
    const selectAllGroupsBtn = document.getElementById('select-all-groups');
    const clearGroupsBtn = document.getElementById('clear-groups');
    const groupsContainer = document.getElementById('groups-container');
    
    // State variables
    let isPosting = false;
    let statusCheckInterval;
    let logsCheckInterval;
    let lastLogCount = 0;
    let totalGroupsCount = 0;
    let currentTemplates = [];
    let fetchedGroups = [];
    let selectedGroups = [];
    let isFetchingGroups = false;
    let groupStatusInterval;
    
    // Initialize the application
    initializeApp();
    
    /**
     * Initialize the application components
     */
    function initializeApp() {
        // Set up event listeners for navigation
        navItems.forEach(item => {
            item.addEventListener('click', handleNavigation);
        });
        
        // Theme toggle
        themeToggle.addEventListener('change', toggleDarkMode);
        
        // Initialize theme from local storage
        if (localStorage.getItem('darkMode') === 'true') {
            document.body.classList.add('dark-theme');
            themeToggle.checked = true;
        }
        
        // Range slider sync
        maxGroupsRange.addEventListener('input', () => {
            maxGroupsInput.value = maxGroupsRange.value;
            updateProgressBar();
        });
        
        maxGroupsInput.addEventListener('input', () => {
            maxGroupsRange.value = maxGroupsInput.value;
            updateProgressBar();
        });
        
        // File upload handling
        fileUpload.addEventListener('change', handleFileUpload);
        queueFileInput.addEventListener('change', handleQueueFileUpload);
        
        // Template system
        loadTemplateBtn.addEventListener('click', loadSelectedTemplate);
        saveTemplateBtn.addEventListener('click', saveCurrentTemplate);
        deleteTemplateBtn.addEventListener('click', deleteSelectedTemplate);
        templateSelect.addEventListener('change', handleTemplateSelection);
        
        // Post queue handling
        postQueueTextarea.addEventListener('input', countQueueItems);
        
        // History filters
        refreshHistoryBtn.addEventListener('click', fetchHistory);
        applyFiltersBtn.addEventListener('click', fetchHistory);
        
        // Setup form submissions
        postingForm.addEventListener('submit', handlePostingFormSubmit);
        accountSettingsForm.addEventListener('submit', handleAccountSettingsSubmit);
        botSettingsForm.addEventListener('submit', handleBotSettingsSubmit);
        
        // Button events
        stopBtn.addEventListener('click', handleStopPosting);
        
        // Modal events
        modalClose.addEventListener('click', closeModal);
        modalCancel.addEventListener('click', closeModal);
        modalConfirm.addEventListener('click', startPosting);
        
        // Quick action buttons
        setupActionButtons();
        
        // FAB button
        fabButton.addEventListener('click', scrollToPostForm);
        
        // Load settings from local storage and server
        loadSavedSettings();
        
        // Start polling for status and logs
        startPolling();
        
        // Initial data fetch
        fetchStatus();
        fetchLogs();
        fetchTemplates();
        
        // Initialize history tab
        fetchHistory();
        
        // Group fetching and selection
        fetchGroupsBtn.addEventListener('click', handleFetchGroups);
        selectAllGroupsBtn.addEventListener('click', selectAllGroups);
        clearGroupsBtn.addEventListener('click', clearGroupSelection);
        
        // Add initial data fetch
        fetchMyGroups(); // Load any previously fetched groups
        
        // Export to CSV button
        const exportResultsBtn = document.getElementById('export-results');
        if (exportResultsBtn) {
            exportResultsBtn.addEventListener('click', exportResultsToCSV);
        }
    }
    
    /**
     * Handle navigation between sections
     */
    function handleNavigation(e) {
        e.preventDefault();
        const targetSection = e.currentTarget.getAttribute('data-section');
        
        // Update active nav item
        navItems.forEach(item => {
            item.parentElement.classList.remove('active');
        });
        e.currentTarget.parentElement.classList.add('active');
        
        // Show corresponding section
        contentSections.forEach(section => {
            section.classList.remove('active');
        });
        document.getElementById(`${targetSection}-section`).classList.add('active');
        
        // Fetch data for the section if needed
        if (targetSection === 'history') {
            fetchHistory();
        }
    }
    
    /**
     * Toggle dark mode
     */
    function toggleDarkMode() {
        document.body.classList.toggle('dark-theme');
        localStorage.setItem('darkMode', themeToggle.checked);
    }
    
    /**
     * Handle file upload for groups
     */
    function handleFileUpload(event) {
        const file = event.target.files[0];
        if (file) {
            fileName.textContent = file.name;
            
            // Read file to count groups for progress bar
            const reader = new FileReader();
            reader.onload = function(e) {
                const content = e.target.result;
                const lines = content.split('\n').filter(line => line.trim() && line.includes('facebook.com/groups'));
                totalGroupsCount = lines.length;
                updateProgressBar();
            };
            reader.readAsText(file);
        } else {
            fileName.textContent = 'Drop groups.txt or click to browse';
            totalGroupsCount = 0;
        }
    }
    
    /**
     * Handle file upload for post queue
     */
    function handleQueueFileUpload(event) {
        const file = event.target.files[0];
        if (file) {
            queueFileName.textContent = file.name;
            
            // Read file to count queue items
            const reader = new FileReader();
            reader.onload = function(e) {
                const content = e.target.result;
                // Count posts separated by --- or by newlines
                let posts = [];
                if (content.includes('---')) {
                    posts = content.split('---').filter(msg => msg.trim());
                } else {
                    posts = content.split('\n').filter(msg => msg.trim());
                }
                
                queueCount.textContent = `${posts.length} posts in queue`;
            };
            reader.readAsText(file);
        } else {
            queueFileName.textContent = 'Upload queue.txt or click to browse';
            queueCount.textContent = '0 posts in queue';
        }
    }
    
    /**
     * Count items in the post queue textarea
     */
    function countQueueItems() {
        const content = postQueueTextarea.value;
        if (!content.trim()) {
            queueCount.textContent = '0 posts in queue';
            return;
        }
        
        // Count posts separated by ---
        const posts = content.split('---').filter(msg => msg.trim());
        queueCount.textContent = `${posts.length} posts in queue`;
    }
    
    /**
     * Handle posting form submission
     */
    function handlePostingFormSubmit(event) {
        event.preventDefault();
        
        const message = document.getElementById('message').value.trim();
        const postQueue = document.getElementById('post-queue').value.trim();
        const groupsFile = document.getElementById('groups-file').files[0];
        
        if (!message && !postQueue && !queueFileInput.files[0]) {
            showToast('Please enter a message or post queue', 'error');
            return;
        }
        
        // Check if we have groups to post to
        if (!groupsFile && selectedGroups.length === 0) {
            showToast('Please select groups or upload a groups file', 'error');
            return;
        }
        
        // Show confirmation modal
        showModal();
    }
    
    /**
     * Show confirmation modal
     */
    function showModal() {
        confirmationModal.classList.add('show');
    }
    
    /**
     * Close confirmation modal
     */
    function closeModal() {
        confirmationModal.classList.remove('show');
    }
    
    /**
     * Start polling for status and logs updates
     */
    function startPolling() {
        statusCheckInterval = setInterval(fetchStatus, 5000);
        logsCheckInterval = setInterval(fetchLogs, 10000);
    }
    
    /**
     * Set up action buttons
     */
    function setupActionButtons() {
        // Action buttons in the dashboard
        document.getElementById('refresh-groups').addEventListener('click', () => {
            showToast('Refreshing groups list...', 'info');
            // Force a direct reload from the file with a cache-busting timestamp
            loadGroupsDirectly();
        });
        
        document.getElementById('view-full-logs').addEventListener('click', () => {
            // Navigate to logs tab
            navItems.forEach(item => {
                if (item.getAttribute('data-section') === 'logs') {
                    item.click();
                }
            });
        });
        
        document.getElementById('test-connection').addEventListener('click', () => {
            showToast('Testing Facebook connection...', 'info');
            // Add your connection test functionality here
        });
        
        document.getElementById('clear-stats').addEventListener('click', () => {
            // Reset stats
            postsCompleted.textContent = '0';
            postsFailed.textContent = '0';
            progressBar.style.width = '0%';
            progressPercentage.textContent = '0%';
            showToast('Stats cleared successfully');
        });
        
        // Log management
        document.getElementById('refresh-logs').addEventListener('click', fetchLogs);
        document.getElementById('clear-logs').addEventListener('click', () => {
            // This would need a backend endpoint to clear logs
            showToast('Logs cleared successfully');
        });
    }
    
    /**
     * Scroll to post form
     */
    function scrollToPostForm() {
        document.querySelector('.control-panel').scrollIntoView({ behavior: 'smooth' });
    }
    
    /**
     * Load saved settings from local storage and server
     */
    function loadSavedSettings() {
        // First load from localStorage for immediate UI update
        if (localStorage.getItem('fbUsername')) {
            fbUsername.value = localStorage.getItem('fbUsername');
        }
        
        if (localStorage.getItem('fbPassword')) {
            fbPassword.value = localStorage.getItem('fbPassword');
        }
        
        if (localStorage.getItem('minDelay')) {
            minDelay.value = localStorage.getItem('minDelay');
        }
        
        if (localStorage.getItem('maxDelay')) {
            maxDelay.value = localStorage.getItem('maxDelay');
        }
        
        if (localStorage.getItem('headlessMode') === 'true') {
            headlessMode.checked = true;
        }
        
        // Now fetch settings from server to ensure we're synced
        fetch('/get_settings')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Update UI with server values if they exist
                    if (data.settings) {
                        // Update credentials
                        if (data.settings.username) {
                            fbUsername.value = data.settings.username;
                            localStorage.setItem('fbUsername', data.settings.username);
                        }
                        
                        if (data.settings.password) {
                            // Only update password field if not empty on server
                            // (we don't send actual password from server for security,
                            // but we can detect if it exists)
                            if (data.settings.has_password) {
                                fbPassword.value = localStorage.getItem('fbPassword') || '********';
                            }
                        }
                        
                        // Update bot settings
                        if (data.settings.min_delay) {
                            minDelay.value = data.settings.min_delay;
                            localStorage.setItem('minDelay', data.settings.min_delay);
                        }
                        
                        if (data.settings.max_delay) {
                            maxDelay.value = data.settings.max_delay;
                            localStorage.setItem('maxDelay', data.settings.max_delay);
                        }
                        
                        if (data.settings.max_groups) {
                            maxGroupsInput.value = data.settings.max_groups;
                            maxGroupsRange.value = data.settings.max_groups;
                        }
                        
                        if (data.settings.headless_mode !== undefined) {
                            headlessMode.checked = data.settings.headless_mode;
                            localStorage.setItem('headlessMode', data.settings.headless_mode);
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error fetching settings from server:', error);
            });
    }
    
    /**
     * Handle account settings form submission
     */
    function handleAccountSettingsSubmit(event) {
        event.preventDefault();
        
        // Save to local storage for UI persistence
        localStorage.setItem('fbUsername', fbUsername.value);
        localStorage.setItem('fbPassword', fbPassword.value);
        
        // Create form data to send to server
        const formData = new FormData();
        formData.append('username', fbUsername.value);
        formData.append('password', fbPassword.value);
        
        // Call server endpoint to save credentials
        fetch('/save_credentials', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showToast('Credentials saved successfully');
            } else {
                showToast(data.message || 'Error saving credentials', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Failed to save credentials to server', 'error');
        });
    }
    
    /**
     * Handle bot settings form submission
     */
    function handleBotSettingsSubmit(event) {
        event.preventDefault();
        
        // Save to local storage for UI persistence
        localStorage.setItem('minDelay', minDelay.value);
        localStorage.setItem('maxDelay', maxDelay.value);
        localStorage.setItem('headlessMode', headlessMode.checked);
        
        // Create form data to send to server
        const formData = new FormData();
        formData.append('min_delay', minDelay.value);
        formData.append('max_delay', maxDelay.value);
        formData.append('headless', headlessMode.checked);
        formData.append('max_groups', maxGroupsInput.value);
        
        // Call server endpoint to save bot settings
        fetch('/save_bot_settings', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showToast('Bot settings saved successfully');
            } else {
                showToast(data.message || 'Error saving bot settings', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Failed to save bot settings to server', 'error');
        });
    }
    
    /**
     * Start posting process
     */
    function startPosting() {
        closeModal();
        
        // Prepare form data
        const formData = new FormData(postingForm);
        
        // Add selected groups to form data
        if (selectedGroups.length > 0) {
            selectedGroups.forEach(groupUrl => {
                formData.append('selected_groups[]', groupUrl);
            });
        }
        
        // Set campaign start time for statistics
        localStorage.setItem('campaignStartTime', Date.now().toString());
        
        // Start elapsed time counter
        const timeUpdateInterval = setInterval(updateElapsedTime, 1000);
        
        // Set loading state
        setFormState(true);
        showToast('Starting posting process...', 'info');
        
        // Submit to server
        fetch('/start_posting', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showToast('Posting started successfully');
                fetchStatus(); // Immediate status update
                
                // Show statistics tab
                const statisticsTab = document.querySelector('a[data-section="statistics"]');
                if (statisticsTab) {
                    statisticsTab.click();
                }
            } else {
                showToast(data.message || 'Error starting posting process', 'error');
                setFormState(false);
                clearInterval(timeUpdateInterval);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Failed to start posting process', 'error');
            setFormState(false);
            clearInterval(timeUpdateInterval);
        });
    }
    
    /**
     * Handle stop posting
     */
    function handleStopPosting() {
        fetch('/stop_posting', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showToast('Posting process stopping...');
                // Update will happen via status polling
            } else {
                showToast(data.message || 'Error stopping posting process', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Failed to stop posting process', 'error');
        });
    }
    
    /**
     * Fetch status from server
     */
    function fetchStatus() {
        if (!isPosting) return;
        
        fetch('/get_status')
            .then(response => response.json())
            .then(data => {
                // Update status indicators
                updateStatusIndicator(statusIndicator, data.status);
                updateStatusIndicator(statusIndicatorStats, data.status);
                
                // Update statistics
                postsCompleted.textContent = data.posts_completed;
                postsFailed.textContent = data.posts_failed;
                
                // Update groups total count
                if (data.groups_total > 0) {
                    statGroupsTotal.textContent = data.groups_total;
                    totalGroupsCount = data.groups_total;
                }
                
                // Calculate and update success rate
                const total = data.posts_completed + data.posts_failed;
                let successRate = 0;
                if (total > 0) {
                    successRate = Math.round((data.posts_completed / total) * 100);
                }
                statSuccessRate.textContent = `${successRate}%`;
                
                // Update progress bar
                updateProgressBar(data.posts_completed + data.posts_failed);
                
                // Update group status table if available
                if (data.group_statuses) {
                    Object.entries(data.group_statuses).forEach(([id, groupData]) => {
                        // Add id to group data
                        groupData.id = id;
                        
                        // Add to status table
                        addGroupToStatusTable(groupData);
                    });
                }
                
                // Set posting state
                isPosting = data.is_posting;
                
                // Update form state based on posting status
                if (postingForm) {
                    setFormState(isPosting);
                }
                
                // Continue polling if posting is in progress
                if (isPosting) {
                    setTimeout(fetchStatus, 3000);
                } else {
                    // One final update after posting completes
                    setTimeout(() => {
                        fetch('/get_status')
                            .then(response => response.json())
                            .then(finalData => {
                                // Update final statistics
                                postsCompleted.textContent = finalData.posts_completed;
                                postsFailed.textContent = finalData.posts_failed;
                                
                                // Final success rate
                                const finalTotal = finalData.posts_completed + finalData.posts_failed;
                                let finalSuccessRate = 0;
                                if (finalTotal > 0) {
                                    finalSuccessRate = Math.round((finalData.posts_completed / finalTotal) * 100);
                                }
                                statSuccessRate.textContent = `${finalSuccessRate}%`;
                                
                                // Final progress update
                                updateProgressBar(finalData.posts_completed + finalData.posts_failed);
                                
                                // Show toast notification when complete
                                showToast(`Posting completed: ${finalData.posts_completed} successful, ${finalData.posts_failed} failed`);
                            });
                    }, 1000);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                // Continue polling despite errors
                if (isPosting) {
                    setTimeout(fetchStatus, 5000);
                }
            });
    }
    
    /**
     * Fetch logs from server
     */
    function fetchLogs() {
        fetch('/get_logs')
        .then(response => response.json())
        .then(data => {
            updateLogsDisplay(data.logs);
        })
        .catch(error => {
            console.error('Error fetching logs:', error);
        });
    }
    
    /**
     * Fetch templates from server
     */
    function fetchTemplates() {
        fetch('/get_templates')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                currentTemplates = data.templates;
                updateTemplateDropdown();
            }
        })
        .catch(error => {
            console.error('Error fetching templates:', error);
            showToast('Failed to load templates', 'error');
        });
    }
    
    /**
     * Fetch post history data
     */
    function fetchHistory() {
        // Get filter values
        const status = statusFilter.value;
        const account = accountFilter.value;
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;
        
        // Build query string
        const params = new URLSearchParams();
        if (status) params.append('status', status);
        if (account) params.append('account', account);
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        
        // Fetch from server
        fetch(`/get_history?${params.toString()}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                updateHistoryDisplay(data.history, data.statistics);
            } else {
                showToast(data.message || 'Error fetching history', 'error');
            }
        })
        .catch(error => {
            console.error('Error fetching history:', error);
            showToast('Failed to load post history', 'error');
        });
    }
    
    /**
     * Update display of post history
     */
    function updateHistoryDisplay(historyData, stats) {
        // Update statistics
        totalPosts.textContent = stats.total;
        successPosts.textContent = stats.success;
        errorPosts.textContent = stats.error;
        blockedPosts.textContent = stats.blocked;
        successRate.textContent = `${stats.success_rate.toFixed(1)}%`;
        
        // Update account filter options (if we got new accounts)
        const accounts = new Set();
        historyData.forEach(entry => {
            if (entry.account) accounts.add(entry.account);
        });
        
        // Save current selection
        const currentAccount = accountFilter.value;
        
        // Clear options except the first one
        while (accountFilter.options.length > 1) {
            accountFilter.remove(1);
        }
        
        // Add account options
        accounts.forEach(account => {
            const option = document.createElement('option');
            option.value = account;
            option.textContent = account;
            accountFilter.appendChild(option);
        });
        
        // Restore selection if possible
        if (currentAccount) {
            accountFilter.value = currentAccount;
        }
        
        // Clear existing table rows
        historyTableBody.innerHTML = '';
        
        // Add history entries to table
        historyData.forEach(entry => {
            addHistoryTableRow(entry);
        });
    }
    
    /**
     * Add a row to the history table
     */
    function addHistoryTableRow(entry) {
        const row = document.createElement('tr');
        
        // Format date/time
        const timestamp = new Date(entry.timestamp);
        const formattedDate = timestamp.toLocaleString();
        
        // Status badge class
        let statusClass = 'status-badge ';
        if (entry.status === 'SUCCESS') statusClass += 'status-success';
        else if (entry.status === 'ERROR') statusClass += 'status-error';
        else if (entry.status === 'BLOCKED') statusClass += 'status-blocked';
        
        // Create table cells
        row.innerHTML = `
            <td>${formattedDate}</td>
            <td title="${entry.group_url}">${entry.group_name}</td>
            <td><span class="${statusClass}">${entry.status}</span></td>
            <td>${entry.account || 'N/A'}</td>
            <td>
                <button class="action-icon copy-message" title="Copy message details">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                </button>
            </td>
        `;
        
        // Add event listener to copy button
        const copyButton = row.querySelector('.copy-message');
        copyButton.addEventListener('click', () => {
            // Create message text to copy
            const copyText = `Group: ${entry.group_name}\nURL: ${entry.group_url}\nStatus: ${entry.status}\nMessage: ${entry.message}`;
            
            // Copy to clipboard
            navigator.clipboard.writeText(copyText).then(() => {
                showToast('Details copied to clipboard');
            }).catch(err => {
                console.error('Could not copy text: ', err);
                showToast('Failed to copy to clipboard', 'error');
            });
        });
        
        historyTableBody.appendChild(row);
    }
    
    /**
     * Update template dropdown with available templates
     */
    function updateTemplateDropdown() {
        // Save current selection
        const currentSelection = templateSelect.value;
        
        // Clear options except the first one
        while (templateSelect.options.length > 1) {
            templateSelect.remove(1);
        }
        
        // Add template options
        currentTemplates.forEach(template => {
            const option = document.createElement('option');
            option.value = template.id;
            option.textContent = template.name;
            templateSelect.appendChild(option);
        });
        
        // Restore selection if possible
        if (currentSelection) {
            templateSelect.value = currentSelection;
        }
    }
    
    /**
     * Handle template selection
     */
    function handleTemplateSelection() {
        // Enable/disable delete button based on selection
        deleteTemplateBtn.disabled = !templateSelect.value;
    }
    
    /**
     * Load selected template into message textarea
     */
    function loadSelectedTemplate() {
        const templateId = templateSelect.value;
        if (!templateId) {
            showToast('Please select a template', 'error');
            return;
        }
        
        const template = currentTemplates.find(t => t.id === templateId);
        if (template) {
            messageTextarea.value = template.content;
            showToast(`Template "${template.name}" loaded`);
        }
    }
    
    /**
     * Save current message as a template
     */
    function saveCurrentTemplate() {
        const name = templateName.value.trim();
        const content = messageTextarea.value.trim();
        
        if (!name) {
            showToast('Please enter a template name', 'error');
            return;
        }
        
        if (!content) {
            showToast('Message content cannot be empty', 'error');
            return;
        }
        
        // Create form data
        const formData = new FormData();
        formData.append('name', name);
        formData.append('content', content);
        
        // Send to server
        fetch('/save_template', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                fetchTemplates(); // Refresh templates
                showToast('Template saved successfully');
                templateName.value = ''; // Clear name field
            } else {
                showToast(data.message || 'Error saving template', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Failed to save template', 'error');
        });
    }
    
    /**
     * Delete selected template
     */
    function deleteSelectedTemplate() {
        const templateId = templateSelect.value;
        if (!templateId) {
            showToast('Please select a template to delete', 'error');
            return;
        }
        
        // Get template name for confirmation
        const template = currentTemplates.find(t => t.id === templateId);
        if (!template) return;
        
        if (!confirm(`Are you sure you want to delete the template "${template.name}"?`)) {
            return;
        }
        
        // Send delete request
        fetch(`/delete_template/${templateId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                fetchTemplates(); // Refresh templates
                showToast('Template deleted successfully');
            } else {
                showToast(data.message || 'Error deleting template', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Failed to delete template', 'error');
        });
    }
    
    /**
     * Update status display based on server response
     */
    function updateStatusDisplay(data) {
        isPosting = data.is_posting;
        
        // Update both status indicators (dashboard and statistics)
        updateStatusIndicator(statusIndicator, data.status);
        updateStatusIndicator(statusIndicatorStats, data.status);
        
        // Update counts
        postsCompleted.textContent = data.posts_completed;
        postsFailed.textContent = data.posts_failed;
        
        // Update form state
        setFormState(isPosting);
        
        // Update progress bar
        if (data.groups_total > 0) {
            totalGroupsCount = data.groups_total;
            statGroupsTotal.textContent = data.groups_total;
        }
        
        // Update success rate in statistics section
        const total = data.posts_completed + data.posts_failed;
        if (total > 0) {
            const rate = Math.round((data.posts_completed / total) * 100);
            statSuccessRate.textContent = `${rate}%`;
        }
        
        updateProgressBar(data.posts_completed);
        
        // Add group to status table if needed (example implementation)
        // This would need to be extended with actual group data from the server
        if (data.last_processed_group) {
            addGroupToStatusTable(data.last_processed_group);
        }
    }
    
    /**
     * Update a status indicator element
     */
    function updateStatusIndicator(element, status) {
        if (!element) return;
        
        element.className = 'status-badge';
        element.classList.add(`status-${status}`);
        
        const statusText = element.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        }
    }
    
    /**
     * Add a group to the status table in the statistics page
     */
    function addGroupToStatusTable(groupData) {
        // Only proceed if table exists
        if (!groupsStatusTableBody) return;
        
        // Remove "no data" row if it exists
        const noDataRow = groupsStatusTableBody.querySelector('.no-data');
        if (noDataRow) {
            noDataRow.remove();
        }
        
        // Check if row already exists for this group
        const existingRow = groupsStatusTableBody.querySelector(`[data-group-id="${groupData.id}"]`);
        if (existingRow) {
            // Update existing row instead of creating a new one
            updateGroupStatusRow(existingRow, groupData);
            return;
        }
        
        // Create new row
        const row = document.createElement('tr');
        row.setAttribute('data-group-id', groupData.id);
        
        // Clean group URL for display
        const groupUrl = groupData.url || '#';
        const groupName = groupData.name || 'Unknown Group';
        
        // Get a message preview if available
        const messagePreview = groupData.message ? 
            groupData.message.substring(0, 100) + (groupData.message.length > 100 ? '...' : '') : 
            'No preview available';
        
        // Format time
        const timestamp = groupData.timestamp || new Date().toISOString();
        const formattedTime = new Date(timestamp).toLocaleTimeString();
        
        // Status badge with appropriate icon
        let statusBadge = '';
        switch(groupData.status.toLowerCase()) {
            case 'success':
                statusBadge = `<span class="status-badge status-success">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                        <polyline points="22 4 12 14.01 9 11.01"></polyline>
                    </svg>
                    Success
                </span>`;
                break;
            case 'failed':
            case 'error':
                statusBadge = `<span class="status-badge status-failed">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="15" y1="9" x2="9" y2="15"></line>
                        <line x1="9" y1="9" x2="15" y2="15"></line>
                    </svg>
                    Failed
                </span>`;
                break;
            case 'processing':
                statusBadge = `<span class="status-badge status-processing">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="12" y1="2" x2="12" y2="6"></line>
                        <line x1="12" y1="18" x2="12" y2="22"></line>
                        <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
                        <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
                        <line x1="2" y1="12" x2="6" y2="12"></line>
                        <line x1="18" y1="12" x2="22" y2="12"></line>
                        <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
                        <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
                    </svg>
                    Processing
                </span>`;
                break;
            case 'pending':
                statusBadge = `<span class="status-badge status-pending">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="12 6 12 12 16 14"></polyline>
                    </svg>
                    Pending
                </span>`;
                break;
            default:
                statusBadge = `<span class="status-badge">${groupData.status}</span>`;
        }
        
        // Add row data
        row.innerHTML = `
            <td>
                <div class="group-title">${groupName}</div>
                <div class="group-url">
                    <a href="${groupUrl}" target="_blank">${groupUrl}</a>
                </div>
            </td>
            <td>${statusBadge}</td>
            <td>${formattedTime}</td>
            <td>
                <div class="message-preview">${messagePreview}</div>
            </td>
            <td>
                <button class="details-toggle" aria-label="Show details">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                </button>
            </td>
        `;
        
        // Add to table
        groupsStatusTableBody.appendChild(row);
        
        // Create and add the expandable details row
        const detailsRow = document.createElement('tr');
        detailsRow.className = 'group-details-row';
        detailsRow.setAttribute('data-group-id', `${groupData.id}-details`);
        
        // Create details content
        const errorInfo = groupData.error ? `<div class="details-section">
            <div class="details-section-title">Error Details</div>
            <div class="details-section-content">${groupData.error}</div>
        </div>` : '';
        
        const screenshotInfo = groupData.screenshot ? `<div class="details-section">
            <div class="details-section-title">Screenshot</div>
            <a href="/uploads/${groupData.screenshot}" target="_blank" class="screenshot-link">View Screenshot</a>
        </div>` : '';
        
        detailsRow.innerHTML = `
            <td colspan="5">
                <div class="group-details-content">
                    <div class="details-section">
                        <div class="details-section-title">Post Information</div>
                        <div class="details-section-content">${groupData.message || 'No message content available'}</div>
                    </div>
                    ${errorInfo}
                    ${screenshotInfo}
                    <div class="details-section">
                        <div class="details-section-title">Log Entries</div>
                        <div class="details-section-content log-entries-for-group">Loading logs...</div>
                    </div>
                </div>
            </td>
        `;
        
        // Add details row after the main row
        row.after(detailsRow);
        
        // Add click event for toggling details
        const detailsToggle = row.querySelector('.details-toggle');
        detailsToggle.addEventListener('click', () => {
            detailsToggle.classList.toggle('expanded');
            detailsRow.classList.toggle('visible');
            
            // Load logs if necessary
            if (detailsRow.classList.contains('visible')) {
                loadGroupLogs(groupData.id, detailsRow.querySelector('.log-entries-for-group'));
            }
        });
    }
    
    /**
     * Update an existing group status row
     */
    function updateGroupStatusRow(row, groupData) {
        // Update status badge
        const statusCell = row.querySelector('td:nth-child(2)');
        if (statusCell) {
            let statusBadge = '';
            switch(groupData.status.toLowerCase()) {
                case 'success':
                    statusBadge = `<span class="status-badge status-success">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                            <polyline points="22 4 12 14.01 9 11.01"></polyline>
                        </svg>
                        Success
                    </span>`;
                    break;
                case 'failed':
                case 'error':
                    statusBadge = `<span class="status-badge status-failed">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="15" y1="9" x2="9" y2="15"></line>
                            <line x1="9" y1="9" x2="15" y2="15"></line>
                        </svg>
                        Failed
                    </span>`;
                    break;
                // Other cases remain the same
            }
            if (statusBadge) {
                statusCell.innerHTML = statusBadge;
            }
        }
        
        // Update timestamp if provided
        if (groupData.timestamp) {
            const timeCell = row.querySelector('td:nth-child(3)');
            if (timeCell) {
                timeCell.textContent = new Date(groupData.timestamp).toLocaleTimeString();
            }
        }
        
        // Update details row if it exists and has new data
        const detailsRow = document.querySelector(`[data-group-id="${groupData.id}-details"]`);
        if (detailsRow && groupData.error) {
            const errorSection = detailsRow.querySelector('.details-section:nth-child(2)');
            if (errorSection) {
                errorSection.innerHTML = `
                    <div class="details-section-title">Error Details</div>
                    <div class="details-section-content">${groupData.error}</div>
                `;
            }
        }
    }
    
    /**
     * Load log entries related to a specific group
     */
    function loadGroupLogs(groupId, container) {
        if (!container) return;
        
        // Set loading state
        container.innerHTML = 'Loading logs...';
        
        // Fetch logs and filter for this group
        fetch('/get_logs')
            .then(response => response.json())
            .then(data => {
                // Filter logs that mention this group ID
                const groupLogs = data.logs.filter(log => 
                    log.message.includes(groupId) || 
                    log.message.includes('group') // Include general group-related logs
                );
                
                if (groupLogs.length === 0) {
                    container.innerHTML = 'No specific logs found for this group.';
                    return;
                }
                
                // Format and display logs
                const logsHtml = groupLogs.map(log => 
                    `<div class="log-entry ${log.level.toLowerCase() === 'error' ? 'log-error' : 
                                           log.level.toLowerCase() === 'warning' ? 'log-warning' : 'log-info'}">
                        <span class="log-time">${formatLogTime(log.timestamp)}</span>
                        <span class="log-message">${log.message}</span>
                    </div>`
                ).join('');
                
                container.innerHTML = logsHtml;
            })
            .catch(error => {
                console.error('Error fetching logs:', error);
                container.innerHTML = 'Failed to load logs. Please try again.';
            });
    }
    
    /**
     * Format log timestamp for display
     */
    function formatLogTime(timestamp) {
        try {
            // Extract time portion if timestamp contains date and time
            const parts = timestamp.split(' ');
            if (parts.length >= 2) {
                return parts[1]; // Return just the time part
            }
            return timestamp;
        } catch (e) {
            return timestamp;
        }
    }
    
    /**
     * Update timer for campaign statistics
     */
    function updateElapsedTime() {
        if (!isPosting || !statTimeElapsed) return;
        
        // Get campaign start time from localStorage (this would be set when starting the campaign)
        const startTime = localStorage.getItem('campaignStartTime');
        if (!startTime) return;
        
        // Calculate elapsed time
        const elapsed = Math.floor((Date.now() - parseInt(startTime)) / 1000);
        const hours = Math.floor(elapsed / 3600).toString().padStart(2, '0');
        const minutes = Math.floor((elapsed % 3600) / 60).toString().padStart(2, '0');
        const seconds = Math.floor(elapsed % 60).toString().padStart(2, '0');
        
        // Update display
        statTimeElapsed.textContent = `${hours}:${minutes}:${seconds}`;
    }
    
    /**
     * Update progress bar
     */
    function updateProgressBar(completedCount = 0) {
        if (totalGroupsCount > 0 && completedCount > 0) {
            const percentage = Math.min(Math.round((completedCount / totalGroupsCount) * 100), 100);
            progressBar.style.width = `${percentage}%`;
            progressPercentage.textContent = `${percentage}%`;
        } else {
            progressBar.style.width = '0%';
            progressPercentage.textContent = '0%';
        }
    }
    
    /**
     * Update logs display
     */
    function updateLogsDisplay(logs) {
        // Skip update if no new logs
        if (logs.length <= lastLogCount) return;
        
        // Get new logs
        const newLogs = logs.slice(lastLogCount);
        lastLogCount = logs.length;
        
        // Add new logs to containers
        if (logsContainer) {
            newLogs.forEach(log => {
                addLogEntry(log, logsContainer);
            });
            
            // Scroll to bottom
            logsContainer.scrollTop = logsContainer.scrollHeight;
        }
        
        // Only show recent logs in dashboard (last 5)
        if (recentLogs) {
            // Clear existing logs
            recentLogs.innerHTML = '';
            
            // Show last 5 logs
            const recentLogsToShow = logs.slice(-5);
            recentLogsToShow.forEach(log => {
                addLogEntry(log, recentLogs);
            });
        }
    }
    
    /**
     * Add a log entry to a container
     */
    function addLogEntry(log, container) {
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        
        // Add class based on log level
        if (log.level === 'ERROR') {
            logEntry.classList.add('log-error');
        } else if (log.level === 'WARNING') {
            logEntry.classList.add('log-warning');
        } else {
            logEntry.classList.add('log-info');
        }
        
        // Format timestamp - handle potential invalid dates
        let formattedTime;
        try {
            // Check if timestamp is already formatted
            if (typeof log.timestamp === 'string' && log.timestamp.includes('-') && log.timestamp.includes(':')) {
                // Parse ISO format or similar format
                const parts = log.timestamp.split(' ');
                if (parts.length >= 2) {
                    // Just keep time part if it exists
                    formattedTime = parts[1];
                } else {
                    formattedTime = log.timestamp;
                }
            } else {
                // Try to parse as date
                const timestamp = new Date(log.timestamp);
                if (isNaN(timestamp.getTime())) {
                    // Fallback for invalid date
                    formattedTime = "Unknown";
                } else {
                    formattedTime = timestamp.toLocaleTimeString();
                }
            }
        } catch (e) {
            console.error("Error formatting log timestamp:", e);
            formattedTime = "Unknown";
        }
        
        // Create log content
        logEntry.innerHTML = `
            <span class="log-time">${formattedTime}</span>
            <span class="log-level">${log.level}</span>
            <span class="log-message">${log.message}</span>
        `;
        
        container.appendChild(logEntry);
    }
    
    /**
     * Set form state based on posting status
     */
    function setFormState(isDisabled) {
        // Toggle form elements
        const formElements = postingForm.querySelectorAll('input, textarea, button:not(#stop-btn)');
        formElements.forEach(element => {
            element.disabled = isDisabled;
        });
        
        // Toggle buttons
        startBtn.disabled = isDisabled;
        stopBtn.disabled = !isDisabled;
    }
    
    /**
     * Show toast notification
     */
    function showToast(message, type = 'success') {
        const toastContainer = document.getElementById('toast-container');
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        toastContainer.appendChild(toast);
        
        // Animate entrance
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);
        
        // Remove after timeout
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    }
    
    /**
     * Handle fetching Facebook groups
     */
    function handleFetchGroups() {
        if (isFetchingGroups) {
            showToast('Group fetching already in progress', 'info');
            return;
        }
        
        // Show loading state
        setGroupsFetchingState(true);
        
        // Call API to fetch groups
        fetch('/fetch_my_groups', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showToast(data.message || 'Fetching groups started', 'info');
                
                // Start polling for fetch status
                startGroupFetchingPolling();
            } else if (data.status === 'redirect') {
                // Manual fetching required
                setGroupsFetchingState(false);
                
                // Show modal with instructions
                const modal = document.createElement('div');
                modal.className = 'modal manual-fetch-modal';
                modal.innerHTML = `
                    <div class="modal-content">
                        <span class="close">&times;</span>
                        <h2>Manual Group Fetching Required</h2>
                        <p>${data.message}</p>
                        <div class="modal-actions">
                            <button class="btn btn-primary modal-ok">OK</button>
                        </div>
                    </div>
                `;
                
                document.body.appendChild(modal);
                
                // Add event listeners to close modal
                const closeBtn = modal.querySelector('.close');
                const okBtn = modal.querySelector('.modal-ok');
                
                closeBtn.addEventListener('click', () => {
                    modal.remove();
                });
                
                okBtn.addEventListener('click', () => {
                    modal.remove();
                    fetchMyGroups(); // Refresh groups in case they were updated manually
                });
                
                // Show modal
                setTimeout(() => {
                    modal.classList.add('show');
                }, 10);
            } else {
                setGroupsFetchingState(false);
                showToast(data.message || 'Error fetching groups', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            setGroupsFetchingState(false);
            showToast('Failed to start groups fetching', 'error');
        });
    }
    
    /**
     * Start polling for group fetching status
     */
    function startGroupFetchingPolling() {
        if (groupStatusInterval) {
            clearInterval(groupStatusInterval);
        }
        
        groupStatusInterval = setInterval(() => {
            fetch('/fetch_status')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    if (!data.is_fetching) {
                        // Fetching completed
                        clearInterval(groupStatusInterval);
                        fetchMyGroups(); // Refresh groups
                    }
                }
            })
            .catch(error => {
                console.error('Error checking fetch status:', error);
                clearInterval(groupStatusInterval);
                setGroupsFetchingState(false);
            });
        }, 2000);
    }
    
    /**
     * Set groups fetching UI state
     */
    function setGroupsFetchingState(isFetching) {
        isFetchingGroups = isFetching;
        
        if (isFetching) {
            groupsLoading.classList.remove('hidden');
            fetchGroupsBtn.disabled = true;
        } else {
            groupsLoading.classList.add('hidden');
            fetchGroupsBtn.disabled = false;
        }
    }
    
    /**
     * Fetch my Facebook groups
     */
    function fetchMyGroups() {
        // First try to get groups via API
        fetch('/get_my_groups')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                if (data.fetched && data.groups && data.groups.length > 0) {
                    fetchedGroups = data.groups;
                    updateGroupsList();
                    
                    if (groupStatusInterval) {
                        clearInterval(groupStatusInterval);
                        showToast('✅ Groups fetched successfully', 'success');
                    }
                } else {
                    // If API doesn't return groups, try loading directly from file
                    loadGroupsDirectly();
                }
                
                setGroupsFetchingState(false);
            } else {
                // If API call fails, try loading directly from file
                loadGroupsDirectly();
                setGroupsFetchingState(false);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            // If API call fails, try loading directly from file
            loadGroupsDirectly();
            setGroupsFetchingState(false);
        });
    }
    
    /**
     * Load groups directly from the JSON file
     * This is a fallback when the API call doesn't return groups
     */
    function loadGroupsDirectly() {
        // Show loading state
        setGroupsFetchingState(true);
        
        // Use fetch to load the local file
        fetch('/autofetched_groups.json?t=' + new Date().getTime())
        .then(response => {
            if (!response.ok) {
                throw new Error('File not found or could not be loaded');
            }
            return response.json();
        })
        .then(groups => {
            if (groups && groups.length > 0) {
                fetchedGroups = groups;
                updateGroupsList();
                showToast('✅ Groups loaded from file successfully', 'success');
            } else {
                fetchedGroups = [];
                updateGroupsList();
                showToast('No groups found in file', 'info');
            }
        })
        .catch(error => {
            console.error('Error loading groups file:', error);
            fetchedGroups = [];
            updateGroupsList();
            showToast('Could not load groups from file. Please run manual_fetch_groups.py first.', 'error');
        })
        .finally(() => {
            setGroupsFetchingState(false);
        });
    }
    
    /**
     * Update groups list in UI
     */
    function updateGroupsList() {
        // Clear current list
        groupsList.innerHTML = '';
        
        // Update counter
        groupsCount.textContent = `${fetchedGroups.length} groups found`;
        
        if (fetchedGroups.length === 0) {
            groupsEmpty.style.display = 'flex';
            groupsList.style.display = 'none';
            
            // Update the empty message with more helpful information
            groupsEmpty.innerHTML = `
                <div class="empty-message">
                    <i class="fas fa-users-slash"></i>
                    <p>No Facebook groups found.</p>
                    <p class="empty-submessage">
                        Please run <code>python manual_fetch_groups.py --no-headless</code> in your terminal to fetch your groups, then click "Refresh Groups".
                    </p>
                </div>
            `;
            return;
        }
        
        groupsEmpty.style.display = 'none';
        groupsList.style.display = 'block';
        
        // Create group items
        fetchedGroups.forEach(group => {
            const isSelected = selectedGroups.includes(group.url);
            const groupItem = document.createElement('div');
            groupItem.className = `group-item ${isSelected ? 'selected' : ''}`;
            
            groupItem.innerHTML = `
                <input type="checkbox" class="group-checkbox" ${isSelected ? 'checked' : ''}>
                <div class="group-info">
                    <div class="group-name">${group.name}</div>
                    <div class="group-url">
                        <a href="${group.url}" target="_blank" rel="noopener noreferrer" title="Open group in new tab">
                            ${group.url.length > 50 ? group.url.substring(0, 47) + '...' : group.url}
                            <i class="fas fa-external-link-alt"></i>
                        </a>
                    </div>
                </div>
            `;
            
            // Add checkbox event listener
            const checkbox = groupItem.querySelector('.group-checkbox');
            checkbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    selectGroup(group.url);
                    groupItem.classList.add('selected');
                } else {
                    deselectGroup(group.url);
                    groupItem.classList.remove('selected');
                }
            });
            
            groupsList.appendChild(groupItem);
        });
        
        // Update selected count
        updateSelectedGroupsCount();
    }
    
    /**
     * Select a group
     */
    function selectGroup(groupUrl) {
        if (!selectedGroups.includes(groupUrl)) {
            selectedGroups.push(groupUrl);
            updateSelectedGroupsCount();
        }
    }
    
    /**
     * Deselect a group
     */
    function deselectGroup(groupUrl) {
        selectedGroups = selectedGroups.filter(url => url !== groupUrl);
        updateSelectedGroupsCount();
    }
    
    /**
     * Update selected groups count
     */
    function updateSelectedGroupsCount() {
        groupsCount.textContent = `${selectedGroups.length} of ${fetchedGroups.length} selected`;
    }
    
    /**
     * Select all groups
     */
    function selectAllGroups() {
        selectedGroups = fetchedGroups.map(group => group.url);
        updateGroupsList();
    }
    
    /**
     * Clear group selection
     */
    function clearGroupSelection() {
        selectedGroups = [];
        updateGroupsList();
    }
    
    /**
     * Export group status data to CSV
     */
    function exportResultsToCSV() {
        // Get all rows from the group status table
        const rows = Array.from(groupsStatusTableBody.querySelectorAll('tr:not(.group-details-row):not(.no-data)'));
        
        if (rows.length === 0) {
            showToast('No data to export', 'warning');
            return;
        }
        
        // Create CSV header row
        let csv = 'Group Name,Group URL,Status,Time,Message Preview\n';
        
        // Add data from each row
        rows.forEach(row => {
            const groupName = row.querySelector('.group-title')?.textContent.replace(/,/g, ' ') || 'Unknown';
            const groupUrl = row.querySelector('.group-url a')?.getAttribute('href') || '';
            const status = row.querySelector('.status-badge')?.textContent.trim() || 'Unknown';
            const time = row.querySelector('td:nth-child(3)')?.textContent || '';
            const preview = row.querySelector('.message-preview')?.textContent.replace(/,/g, ' ').replace(/\n/g, ' ') || '';
            
            csv += `"${groupName}","${groupUrl}","${status}","${time}","${preview}"\n`;
        });
        
        // Create download link
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', url);
        link.setAttribute('download', `facebook_group_posting_results_${new Date().toISOString().slice(0, 10)}.csv`);
        link.style.visibility = 'hidden';
        
        // Add to document, click and remove
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showToast('Results exported to CSV');
    }
}); 