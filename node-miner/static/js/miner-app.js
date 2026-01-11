/**
 * Node Miner - Bitcoin CPU Mining Dashboard
 * Main Application Logic
 */

/**
 * SVG Gauge Class (based on CodePen .two style)
 */
class SVGGauge {
  constructor(element, config) {
    this.element = element;
    this.config = Object.assign({
      max: 100,
      value: 0,
      dialStartAngle: 135,
      dialEndAngle: 45,
      radius: 80,
      label: function(value) { return Math.round(value); }
    }, config);
    
    this.render();
  }
  
  render() {
    const centerX = 100;
    const centerY = 100;
    
    this.element.setAttribute('viewBox', '0 0 200 200');
    
    // Background dial
    const dialPath = this.getArcPath(centerX, centerY, this.config.radius, 
                                      this.config.dialStartAngle, this.config.dialEndAngle);
    const dial = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    dial.setAttribute('class', 'dial');
    dial.setAttribute('d', dialPath);
    this.element.appendChild(dial);
    
    // Value arc
    this.valuePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    this.valuePath.setAttribute('class', 'value');
    this.element.appendChild(this.valuePath);
    
    // Value text (positioned slightly lower for better visual balance)
    this.valueText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    this.valueText.setAttribute('x', centerX);
    this.valueText.setAttribute('y', centerY + 10); // Moved down by 10 units
    this.valueText.setAttribute('class', 'value-text');
    this.valueText.setAttribute('text-anchor', 'middle');
    this.valueText.setAttribute('alignment-baseline', 'middle');
    this.element.appendChild(this.valueText);
    
    this.update(this.config.value);
  }
  
  update(value, color) {
    const centerX = 100;
    const centerY = 100;
    const angle = this.getAngle(value, this.config.max);
    
    const valuePath = this.getArcPath(centerX, centerY, this.config.radius,
                                       this.config.dialStartAngle, angle);
    this.valuePath.setAttribute('d', valuePath);
    
    if (color) {
      this.valuePath.style.stroke = color;
    }
    
    this.valueText.textContent = this.config.label(value);
  }
  
  getAngle(value, max) {
    const minAngle = this.config.dialStartAngle;
    const maxAngle = this.config.dialEndAngle;
    
    // Calculate range (handle wrap-around for angles)
    let range = maxAngle - minAngle;
    if (range < 0) {
      range += 360;
    }
    
    return minAngle + (value / max) * range;
  }
  
  getArcPath(x, y, radius, startAngle, endAngle) {
    const start = this.polarToCartesian(x, y, radius, endAngle);
    const end = this.polarToCartesian(x, y, radius, startAngle);
    
    // Calculate angle difference (handle wrap-around)
    let diff = endAngle - startAngle;
    if (diff < 0) {
      diff += 360;
    }
    
    const largeArc = diff <= 180 ? '0' : '1';
    return 'M ' + start.x + ' ' + start.y + ' A ' + radius + ' ' + radius + ' 0 ' + largeArc + ' 0 ' + end.x + ' ' + end.y;
  }
  
  polarToCartesian(centerX, centerY, radius, angle) {
    const rad = (angle - 90) * Math.PI / 180;
    return {
      x: centerX + radius * Math.cos(rad),
      y: centerY + radius * Math.sin(rad)
    };
  }
}

// Current page tracking
let currentPage = 'dashboard';

// Hashrate chart instance
let hashrateChart = null;

// SVG Gauge instances
let cpuUsageGauge = null;
let cpuTempGauge = null;

/**
 * Initialize the application on page load
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Node Miner Dashboard initialized');
    
    // Load configuration
    loadConfig();
    
    // Initialize hashrate chart
    initHashrateChart();
    
    // Initialize gauges
    initGauges();
    
    // Start status updates
    updateStatus();
    setInterval(updateStatus, 2000); // Update every 2 seconds
    
    // Start chart updates (synced with UI)
    fetchHashrateHistory();
    setInterval(fetchHashrateHistory, 2000); // Update every 2 seconds (synced with UI)
    
    // Show dashboard by default
    showPage('dashboard');
    
    // Setup form handlers
    setupFormHandlers();
    
    // Setup button handlers
    setupButtonHandlers();
    
    // Close sidebar when clicking on main content (mobile)
    const mainPanel = document.querySelector('.main-panel');
    
    if (mainPanel) {
        mainPanel.addEventListener('click', function(e) {
            const html = document.documentElement;
            
            // Only on mobile when sidebar is open
            if (window.innerWidth < 991 && html.classList.contains('nav-open')) {
                // Don't close if clicking on navbar, sidebar, or toggle button
                if (!e.target.closest('.navbar') && 
                    !e.target.closest('.sidebar') && 
                    !e.target.closest('.navbar-toggle')) {
                    
                    // Remove nav-open class from html
                    html.classList.remove('nav-open');
                    
                    // Remove toggled class from toggle button
                    const toggleButton = document.querySelector('.navbar-toggle');
                    if (toggleButton) {
                        toggleButton.classList.remove('toggled');
                    }
                    
                    // Remove bodyClick overlay if exists
                    const bodyClick = document.querySelector('.bodyClick');
                    if (bodyClick) {
                        bodyClick.remove();
                    }
                    
                    // Update Black Dashboard state
                    if (typeof blackDashboard !== 'undefined') {
                        blackDashboard.misc.navbar_menu_visible = 0;
                    }
                }
            }
        });
    }
});

/**
 * Setup form event handlers
 */
function setupFormHandlers() {
    const configForm = document.getElementById('configForm');
    if (configForm) {
        configForm.addEventListener('submit', function(e) {
            e.preventDefault();
            saveConfig();
        });
    }
}

/**
 * Setup button event handlers
 */
function setupButtonHandlers() {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const testBtn = document.getElementById('testBtn');
    
    if (startBtn) {
        startBtn.addEventListener('click', startMining);
    }
    
    if (stopBtn) {
        stopBtn.addEventListener('click', stopMining);
    }
    
    if (testBtn) {
        testBtn.addEventListener('click', testConnection);
    }
}

/**
 * Show a specific page and hide others
 */
function showPage(pageId) {
    console.log('Switching to page:', pageId);
    currentPage = pageId;
    
    // Hide all pages
    const pages = document.querySelectorAll('.page-content');
    pages.forEach(page => {
        page.style.display = 'none';
    });
    
    // Show selected page
    const selectedPage = document.getElementById('page-' + pageId);
    if (selectedPage) {
        selectedPage.style.display = 'block';
    }
    
    // Update navigation active state
    document.querySelectorAll('.sidebar .nav li').forEach(li => {
        li.classList.remove('active');
    });
    
    const navItem = document.getElementById('nav-' + pageId);
    if (navItem) {
        navItem.classList.add('active');
    }
    
    // Update page title
    const titles = {
        'dashboard': 'Dashboard',
        'pool-settings': 'Pool Settings',
        'terminal': 'Terminal'
    };
    
    const pageTitle = document.getElementById('page-title');
    if (pageTitle) {
        pageTitle.textContent = titles[pageId] || 'Dashboard';
    }
}

/**
 * Load configuration from backend
 */
function loadConfig() {
    fetch('/api/config')
        .then(response => response.json())
        .then(data => {
            console.log('Configuration loaded:', data);
            
            // Update form fields
            const poolUrl = document.getElementById('poolUrl');
            const btcAddress = document.getElementById('btcAddress');
            const workerName = document.getElementById('workerName');
            const cpuPercentage = document.getElementById('cpuPercentage');
            
            if (poolUrl) poolUrl.value = data.pool_url || '';
            if (btcAddress) btcAddress.value = data.btc_address || '';
            if (workerName) workerName.value = data.worker_name || '';
            if (cpuPercentage) cpuPercentage.value = data.cpu_percentage || 50;
        })
        .catch(error => {
            console.error('Error loading configuration:', error);
            showNotification('Error loading configuration: ' + error, 'danger');
        });
}

/**
 * Save configuration to backend
 */
function saveConfig() {
    const config = {
        pool_url: document.getElementById('poolUrl').value,
        btc_address: document.getElementById('btcAddress').value,
        worker_name: document.getElementById('workerName').value,
        cpu_percentage: parseInt(document.getElementById('cpuPercentage').value)
    };
    
    console.log('Saving configuration:', config);
    
    fetch('/api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Configuration saved successfully!', 'success');
            loadConfig(); // Reload to show normalized URL
        } else {
            showNotification('Error: ' + data.message, 'danger');
        }
    })
    .catch(error => {
        console.error('Error saving configuration:', error);
        showNotification('Error saving configuration: ' + error, 'danger');
    });
}

/**
 * Test connection to mining pool
 */
function testConnection() {
    const testBtn = document.getElementById('testBtn');
    
    // Get current form values
    const config = {
        pool_url: document.getElementById('poolUrl').value,
        btc_address: document.getElementById('btcAddress').value,
        worker_name: document.getElementById('workerName').value || 'test'
    };
    
    // Validate
    if (!config.pool_url) {
        showNotification('❌ Please enter a Pool URL', 'danger');
        return;
    }
    if (!config.btc_address) {
        showNotification('❌ Please enter a Bitcoin Address', 'danger');
        return;
    }
    
    // Disable button and show testing message
    testBtn.disabled = true;
    testBtn.innerHTML = '<i class="tim-icons icon-settings"></i> Testing...';
    showNotification('Testing connection to pool...', 'info');
    
    fetch('/api/test-connection', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
    })
    .then(response => response.json())
    .then(data => {
        testBtn.disabled = false;
        testBtn.innerHTML = '<i class="tim-icons icon-wifi"></i> Test Connection';
        
        if (data.success) {
            showNotification('✅ Connection successful: ' + data.message, 'success');
        } else {
            showNotification('❌ Connection failed: ' + data.message, 'danger');
        }
    })
    .catch(error => {
        testBtn.disabled = false;
        testBtn.innerHTML = '<i class="tim-icons icon-wifi"></i> Test Connection';
        showNotification('❌ Connection test error: ' + error.message, 'danger');
    });
}

/**
 * Start mining
 */
function startMining() {
    console.log('Starting mining...');
    
    fetch('/api/start', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Mining started successfully!', 'success');
            updateStatus();
        } else {
            // Show detailed error message
            showNotification('Failed to start mining: ' + data.message, 'danger');
            // Update status to reflect failure
            setTimeout(updateStatus, 500);
        }
    })
    .catch(error => {
        console.error('Error starting mining:', error);
        showNotification('Error starting mining: ' + error, 'danger');
        // Update status to reflect failure
        setTimeout(updateStatus, 500);
    });
}

/**
 * Stop mining
 */
function stopMining() {
    console.log('Stopping mining...');
    
    fetch('/api/stop', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Mining stopped successfully!', 'info');
            updateStatus();
        } else {
            showNotification('Error: ' + data.message, 'danger');
        }
    })
    .catch(error => {
        console.error('Error stopping mining:', error);
        showNotification('Error stopping mining: ' + error, 'danger');
    });
}

/**
 * Update mining status and statistics
 */
function updateStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            // Update mining status
            const miningStatus = document.getElementById('miningStatus');
            if (miningStatus) {
                miningStatus.textContent = data.running ? 'Running' : 'Stopped';
                miningStatus.className = data.running ? 'text-success' : 'text-info';
            }
            
            // Update status icon
            const statusIcon = document.getElementById('statusIcon');
            if (statusIcon) {
                if (data.running) {
                    statusIcon.className = 'tim-icons icon-check-2 text-success';
                } else {
                    statusIcon.className = 'tim-icons icon-simple-remove text-muted';
                }
            }
            
            // Update hashrate
            const hashrate = document.getElementById('hashrate');
            if (hashrate) {
                hashrate.textContent = data.hashrate;
            }
            
            // Update mining uptime
            const miningUptime = document.getElementById('miningUptime');
            if (miningUptime) {
                miningUptime.textContent = data.mining_uptime;
            }
            
            // Update system stats
            const cpuCores = document.getElementById('cpuCores');
            if (cpuCores) {
                cpuCores.textContent = data.cpu_count;
            }
            
            // Update CPU Usage Gauge
            if (cpuUsageGauge) {
                const cpuValue = data.cpu_usage_live;
                let color = '#00f2c3'; // Green
                if (cpuValue >= 80) color = '#fd5d93'; // Red
                else if (cpuValue >= 60) color = '#ffc107'; // Yellow
                cpuUsageGauge.update(cpuValue, color);
            }
            
            // Update CPU Temperature Gauge
            if (cpuTempGauge && data.cpu_temp !== null) {
                const tempValue = data.cpu_temp;
                let color = '#00f2c3'; // Green
                if (tempValue >= 90) color = '#fd5d93'; // Red
                else if (tempValue >= 75) color = '#ffc107'; // Yellow
                cpuTempGauge.update(tempValue, color);
            } else if (cpuTempGauge) {
                // No temperature data available
                cpuTempGauge.update(0, '#334455');
            }
            
            // cpulimit status
            const cpulimitStatus = document.getElementById('cpulimitStatus');
            if (cpulimitStatus) {
                if (data.running && data.cpulimit_active) {
                    cpulimitStatus.textContent = '(target: ' + data.cpu_percentage + '%)';
                } else {
                    cpulimitStatus.textContent = '';
                }
            }
            
            // Update difficulty records
            const sessionBest = document.getElementById('sessionBest');
            if (sessionBest) {
                sessionBest.textContent = data.session_best_difficulty.toFixed(5);
            }
            
            const allTimeBest = document.getElementById('allTimeBest');
            if (allTimeBest) {
                allTimeBest.textContent = data.all_time_best_difficulty.toFixed(5);
            }
            
            // Format all-time best date
            const allTimeBestDate = document.getElementById('allTimeBestDate');
            if (allTimeBestDate) {
                if (data.all_time_best_difficulty_date) {
                    const date = new Date(data.all_time_best_difficulty_date * 1000);
                    allTimeBestDate.textContent = '(' + date.toLocaleDateString() + ' ' + date.toLocaleTimeString() + ')';
                } else {
                    allTimeBestDate.textContent = '';
                }
            }
            
            // Update buttons
            const startBtn = document.getElementById('startBtn');
            const stopBtn = document.getElementById('stopBtn');
            
            if (startBtn) {
                startBtn.disabled = data.running;
            }
            if (stopBtn) {
                stopBtn.disabled = !data.running;
            }
            
            // Update terminal output
            const outputElement = document.getElementById('minerOutput');
            if (outputElement && data.full_output) {
                if (data.full_output.length > 0) {
                    // Store current scroll position
                    const isScrolledToBottom = outputElement.scrollHeight - outputElement.clientHeight <= outputElement.scrollTop + 1;
                    
                    // Update content
                    outputElement.textContent = data.full_output.join('\n');
                    
                    // Auto-scroll to bottom if was already at bottom
                    if (isScrolledToBottom) {
                        outputElement.scrollTop = outputElement.scrollHeight;
                    }
                } else if (!data.running) {
                    outputElement.textContent = 'No output yet';
                }
            }
        })
        .catch(error => {
            console.error('Error updating status:', error);
        });
}

/**
 * Scroll terminal output to bottom
 */
function scrollToBottom() {
    const outputElement = document.getElementById('minerOutput');
    if (outputElement) {
        outputElement.scrollTop = outputElement.scrollHeight;
    }
}

/**
 * Clear terminal output display
 */

/**
 * Show notification using Bootstrap Notify
 */
function showNotification(message, type) {
    // Map types to Bootstrap colors
    const typeMap = {
        'success': 'success',
        'info': 'info',
        'warning': 'warning',
        'danger': 'danger'
    };
    
    const notifyType = typeMap[type] || 'info';
    
    // Use Bootstrap Notify if available
    if (typeof $.notify !== 'undefined') {
        $.notify({
            icon: "tim-icons icon-bell-55",
            message: message
        }, {
            type: notifyType,
            timer: 3,
            placement: {
                from: 'top',
                align: 'right'
            }
        });
    } else {
        // Fallback to console
        console.log('[' + type.toUpperCase() + '] ' + message);
    }
}

/**
 * Initialize the CPU usage and temperature gauges
 */
function initGauges() {
    const cpuUsageSvg = document.getElementById('cpuUsageGauge');
    if (cpuUsageSvg) {
        cpuUsageGauge = new SVGGauge(cpuUsageSvg, {
            max: 100,
            label: function(value) { return Math.round(value) + '%'; }
        });
    }
    
    const cpuTempSvg = document.getElementById('cpuTempGauge');
    if (cpuTempSvg) {
        cpuTempGauge = new SVGGauge(cpuTempSvg, {
            max: 100,
            label: function(value) { return Math.round(value) + '°C'; }
        });
    }
    
    console.log('SVG Gauges initialized');
}

/**
 * Initialize the hashrate chart
 */
function initHashrateChart() {
    const ctx = document.getElementById('hashrateChart');
    if (!ctx) return;
    
    console.log('Initializing hashrate chart...');
    
    // Simple chart config (working version)
    hashrateChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Hashrate',
                data: [],
                borderColor: '#1d8cf8',  // Blue color (Black Dashboard primary blue)
                backgroundColor: 'rgba(29, 140, 248, 0.1)',
                borderWidth: 2,
                fill: false,  // No gradient, just line
                pointRadius: 0,  // No dots on the line
                pointHoverRadius: 4  // Show dot only on hover
            }]
        },
        options: {
            animation: {
                duration: 0  // No animation
            },
            responsive: true,
            maintainAspectRatio: false,
            legend: {
                display: false  // No legend needed for single line
            },
            scales: {
                xAxes: [{
                    display: true
                }],
                yAxes: [{
                    display: true,
                    ticks: {
                        beginAtZero: false
                    }
                }]
            }
        }
    });
    
    console.log('Hashrate chart initialized');
}

/**
 * Update the hashrate chart with new data
 */
function updateHashrateChart(historyData) {
    if (!hashrateChart || !historyData || historyData.length === 0) {
        return;
    }
    
    console.log('Updating hashrate chart with', historyData.length, 'datapoints');
    
    const labels = [];
    const data = [];
    
    historyData.forEach(item => {
        const date = new Date(item.timestamp);
        const timeStr = date.getHours().toString().padStart(2, '0') + ':' +
                       date.getMinutes().toString().padStart(2, '0') + ':' +
                       date.getSeconds().toString().padStart(2, '0');
        labels.push(timeStr);
        data.push(item.value);
    });
    
    // Update chart
    hashrateChart.data.labels = labels;
    hashrateChart.data.datasets[0].data = data;
    hashrateChart.update(0);
    
    console.log('Hashrate chart updated');
}

/**
 * Update the hashrate chart with new data
 */
function updateHashrateChart(historyData) {
    if (!hashrateChart || !historyData || historyData.length === 0) {
        return;
    }
    
    // Prepare labels (timestamps) and data (values)
    // No deduplication needed - backend saves every 2 seconds consistently
    const labels = [];
    const data = [];
    
    historyData.forEach(item => {
        // Format timestamp as HH:MM:SS
        const date = new Date(item.timestamp);
        const timeStr = date.getHours().toString().padStart(2, '0') + ':' +
                       date.getMinutes().toString().padStart(2, '0') + ':' +
                       date.getSeconds().toString().padStart(2, '0');
        labels.push(timeStr);
        data.push(item.value);
    });
    
    // Update chart data
    hashrateChart.data.labels = labels;
    hashrateChart.data.datasets[0].data = data;
    hashrateChart.update(0); // v2 syntax: 0 = no animation
}

/**
 * Fetch hashrate history from the API
 */
function fetchHashrateHistory() {
    fetch('/api/hashrate-history?limit=300')  // 10 minutes at 2-second intervals
        .then(response => response.json())
        .then(data => {
            if (data.history && data.history.length > 0) {
                updateHashrateChart(data.history);
            }
        })
        .catch(error => {
            console.error('Error fetching hashrate history:', error);
        });
}
