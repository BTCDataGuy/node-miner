#!/usr/bin/env python3
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
import json
import subprocess
import os
import signal
import psutil
import re
from threading import Thread
import time

app = Flask(__name__)
CORS(app)

# Configuration file path
CONFIG_FILE = '/data/config.json' if os.path.exists('/data') else 'config.json'

# Global variables for miner process
miner_process = None
cpulimit_process = None
miner_output = []
current_hashrate = "0 H/s"
current_hashrate_value = 0.0
current_hashrate_unit = "kH"
cpu_core_hashrates = {}  # {"CPU #0": {"value": 2205.0, "timestamp": 1704545557.123}}
last_accepted_hashrate = 0.0
hashrate_history = []
# Dedizierte Variablen für Chart (getrennt von anderen Systemen)
chart_history = []  # Nur für den Chart, wird nirgendwo anders verwendet
mining_stopped_time = None  # Timestamp when mining was stopped (for smooth chart transition)
session_best_difficulty = 0.0
all_time_best_difficulty = 0.0
mining_start_time = None

def load_config():
    """Load configuration from JSON file"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        else:
            # Return default config
            default_config = {
                "pool_url": "",
                "btc_address": "",
                "worker_name": "",
                "cpu_percentage": 10,
                "mining_active": False,
                "all_time_best_difficulty": 0.0,
                "all_time_best_difficulty_date": None
            }
            save_config(default_config)
            return default_config
    except Exception as e:
        print(f"Error loading config: {e}")
        return {
            "pool_url": "",
            "btc_address": "",
            "worker_name": "",
            "cpu_percentage": 50,
            "mining_active": False,
            "all_time_best_difficulty": 0.0,
            "all_time_best_difficulty_date": None
        }

def save_config(config):
    """Save configuration to JSON file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def calculate_cpu_limit(cpu_percentage):
    """Calculate cpulimit value based on CPU percentage
    
    cpulimit uses a percentage relative to a single core.
    For multi-core systems: 100% = 1 core, 200% = 2 cores, etc.
    So for 4 cores at 50% usage: 50 * 4 = 200%
    """
    cpu_count = psutil.cpu_count()
    limit = int(cpu_percentage * cpu_count)
    return limit

def get_system_stats():
    """Get live system statistics"""
    stats = {
        'cpu_usage_live': 0.0,
        'cpu_temp': None,
        'cpu_temp_warning': None,
        'ram_used_gb': 0.0,
        'ram_total_gb': 0.0,
        'ram_percent': 0.0
    }
    
    try:
        # Non-blocking CPU usage measurement
        # Uses system average since last call (more accurate, no blocking)
        stats['cpu_usage_live'] = psutil.cpu_percent(interval=None)
        
        # RAM usage
        ram = psutil.virtual_memory()
        stats['ram_used_gb'] = round(ram.used / (1024**3), 1)
        stats['ram_total_gb'] = round(ram.total / (1024**3), 1)
        stats['ram_percent'] = ram.percent
        
        # CPU Temperature - try different sensor names
        try:
            temps = psutil.sensors_temperatures()
            
            # Try common sensor names
            if 'coretemp' in temps and temps['coretemp']:
                # Linux desktop/server (Intel/AMD)
                stats['cpu_temp'] = round(temps['coretemp'][0].current, 1)
            elif 'cpu_thermal' in temps and temps['cpu_thermal']:
                # Raspberry Pi
                stats['cpu_temp'] = round(temps['cpu_thermal'][0].current, 1)
            elif 'k10temp' in temps and temps['k10temp']:
                # AMD Ryzen
                stats['cpu_temp'] = round(temps['k10temp'][0].current, 1)
            elif 'zenpower' in temps and temps['zenpower']:
                # AMD Ryzen (alternative driver)
                stats['cpu_temp'] = round(temps['zenpower'][0].current, 1)
            else:
                # No known sensor found
                if temps:
                    # Try first available sensor
                    first_sensor = list(temps.keys())[0]
                    if temps[first_sensor]:
                        stats['cpu_temp'] = round(temps[first_sensor][0].current, 1)
                    else:
                        stats['cpu_temp_warning'] = 'Temperature sensor not available'
                else:
                    stats['cpu_temp_warning'] = 'Temperature sensor not available'
        except (AttributeError, OSError):
            # sensors_temperatures() not supported on this system
            stats['cpu_temp_warning'] = 'Temperature sensor not available'
    
    except Exception as e:
        print(f"Error getting system stats: {e}")
    
    return stats

def get_mining_uptime():
    """Get mining uptime in seconds"""
    global mining_start_time
    
    if mining_start_time is None:
        return 0
    
    return time.time() - mining_start_time

def format_uptime(seconds):
    """Format uptime seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def normalize_pool_url(pool_url):
    """Normalize pool URL to ensure it has the correct format"""
    if not pool_url:
        return pool_url
    
    pool_url = pool_url.strip()
    
    # If URL already has stratum+tcp://, return as is
    if pool_url.startswith('stratum+tcp://'):
        return pool_url
    
    # If URL has stratum:// (without +tcp), convert it
    if pool_url.startswith('stratum://'):
        return pool_url.replace('stratum://', 'stratum+tcp://', 1)
    
    # If URL has http:// or https://, replace with stratum+tcp://
    if pool_url.startswith('http://'):
        return pool_url.replace('http://', 'stratum+tcp://', 1)
    if pool_url.startswith('https://'):
        return pool_url.replace('https://', 'stratum+tcp://', 1)
    
    # If no protocol at all, add stratum+tcp://
    if not pool_url.startswith(('stratum', 'http')):
        return f'stratum+tcp://{pool_url}'
    
    return pool_url

def save_hashrate_to_history(value, unit):
    """Save hashrate to history for charting (always in H/s for consistency)"""
    global hashrate_history
    
    # Convert all values to H/s (base unit) for consistent charting
    value_in_hs = value
    if unit == 'kH':
        value_in_hs = value * 1000
    elif unit == 'MH':
        value_in_hs = value * 1000000
    elif unit == 'GH':
        value_in_hs = value * 1000000000
    # 'H' stays as is
    
    # Convert to milliseconds for JavaScript Date compatibility
    timestamp = time.time() * 1000
    hashrate_history.append({
        'timestamp': timestamp,
        'value': value_in_hs,  # Always in H/s
        'unit': 'H'            # Always H (base unit)
    })
    
    # Keep only last 300 datapoints (10 minutes at 2-second intervals)
    if len(hashrate_history) > 300:
        hashrate_history.pop(0)

def add_to_chart_history(value, unit):
    """Add current hashrate to chart history (synchronized with UI updates)"""
    global chart_history
    
    current_time = time.time()
    
    # No rate limiting - updates are already naturally limited by miner output frequency
    
    # Convert all values to H/s (base unit) for consistent charting
    value_in_hs = value
    if unit == 'kH':
        value_in_hs = value * 1000
    elif unit == 'MH':
        value_in_hs = value * 1000000
    elif unit == 'GH':
        value_in_hs = value * 1000000000
    # 'H' stays as is
    
    # Convert to milliseconds for JavaScript Date compatibility
    timestamp = current_time * 1000
    chart_history.append({
        'timestamp': timestamp,
        'value': value_in_hs,  # Always in H/s
        'unit': 'H'            # Always H (base unit)
    })
    
    # Cleanup: Remove entries older than 10 minutes
    ten_minutes_ago = (current_time * 1000) - (10 * 60 * 1000)
    chart_history[:] = [
        item for item in chart_history 
        if item['timestamp'] > ten_minutes_ago
    ]
    
    # Keep only last 300 datapoints
    if len(chart_history) > 300:
        chart_history.pop(0)
    
    print(f"Chart history updated: {len(chart_history)} datapoints, value: {value_in_hs:.1f} H/s")

def chart_history_writer():
    """Background thread that saves current hashrate to chart every 2 seconds when mining is active"""
    global current_hashrate_value, current_hashrate_unit, chart_history, miner_process, mining_stopped_time
    
    while True:
        time.sleep(2)  # Wait 2 seconds
        
        # Check if mining is running
        mining_active = miner_process is not None and miner_process.poll() is None
        
        if mining_active:
            # Mining is active - write current hashrate
            add_to_chart_history(current_hashrate_value, current_hashrate_unit)
            print(f"Chart history writer: {current_hashrate_value:.1f} {current_hashrate_unit}/s")
        elif mining_stopped_time is not None:
            # Mining stopped recently - continue writing for smooth transition (30 seconds)
            time_since_stop = time.time() - mining_stopped_time
            if time_since_stop < 30:
                # Still within 30 second grace period - write current value (should be declining to 0)
                add_to_chart_history(current_hashrate_value, current_hashrate_unit)
                print(f"Chart history writer (cooldown): {current_hashrate_value:.1f} {current_hashrate_unit}/s")
            # After 30 seconds: thread waits but doesn't write (chart frozen)
        # If mining never started: thread waits but doesn't write (no unnecessary 0-values)

def update_hashrate_from_cores():
    """Calculate hashrate from CPU core values with timeout cleanup"""
    global cpu_core_hashrates, current_hashrate, current_hashrate_value, current_hashrate_unit
    global last_accepted_hashrate
    
    # Cleanup: Remove cores older than 30 seconds
    current_time = time.time()
    cpu_core_hashrates = {
        k: v for k, v in cpu_core_hashrates.items()
        if current_time - v["timestamp"] < 30
    }
    
    # Calculate sum of all cores
    cores_sum = sum(v["value"] for v in cpu_core_hashrates.values())
    
    if cores_sum > 0:
        # Weighted average: 70% accepted (precise), 30% cores_sum (current)
        if last_accepted_hashrate > 0:
            current_hashrate_value = (last_accepted_hashrate * 0.7) + (cores_sum * 0.3)
        else:
            # No accepted value yet, use only cores
            current_hashrate_value = cores_sum
        
        current_hashrate = f"{current_hashrate_value:.1f} {current_hashrate_unit}/s"
        
        # Chart history is now updated by background thread every 2 seconds

def monitor_miner_output():
    """Monitor miner output for hashrate and status"""
    global miner_process, miner_output, current_hashrate
    global current_hashrate_value, current_hashrate_unit
    global cpu_core_hashrates, last_accepted_hashrate
    global hashrate_history, session_best_difficulty, all_time_best_difficulty
    
    if miner_process is None:
        return
    
    try:
        for line in iter(miner_process.stdout.readline, b''):
            if miner_process.poll() is not None:
                break
            
            line_str = line.decode('utf-8', errors='ignore').strip()
            miner_output.append(line_str)
            
            # Keep only last 500 lines (increased for full output)
            if len(miner_output) > 500:
                miner_output.pop(0)
            
            # PRIORITY 1: Track individual CPU cores (fast feedback!)
            if 'CPU #' in line_str and '/s' in line_str:
                core_match = re.search(r'CPU #(\d+):\s*([\d.]+)\s*(H|kH|MH|GH)/s', line_str, re.IGNORECASE)
                if core_match:
                    core_id = f"CPU #{core_match.group(1)}"
                    value = float(core_match.group(2))
                    unit = core_match.group(3)
                    timestamp = time.time()
                    
                    # Store core hashrate with timestamp
                    cpu_core_hashrates[core_id] = {
                        "value": value,
                        "timestamp": timestamp
                    }
                    
                    # Update unit if this is the first core
                    if not current_hashrate_unit or current_hashrate_unit == "kH":
                        current_hashrate_unit = unit
                    
                    # Calculate total hashrate from cores
                    update_hashrate_from_cores()
                    
                    print(f"Core update: {core_id} = {value} {unit}/s, Total: {current_hashrate}")
            
            # PRIORITY 2: Track "accepted:" lines (precise total hashrate)
            elif 'accepted:' in line_str:
                hashrate_match = re.search(r'accepted:.*?([\d.]+)\s*(H|kH|MH|GH)/s', line_str, re.IGNORECASE)
                if hashrate_match:
                    accepted_value = float(hashrate_match.group(1))
                    unit = hashrate_match.group(2)
                    
                    # Store as reference for weighting
                    last_accepted_hashrate = accepted_value
                    current_hashrate_unit = unit
                    
                    # Calculate cores sum
                    cores_sum = sum(v["value"] for v in cpu_core_hashrates.values())
                    
                    # Weighted average: 70% accepted, 30% cores_sum
                    if cores_sum > 0:
                        current_hashrate_value = (accepted_value * 0.7) + (cores_sum * 0.3)
                    else:
                        current_hashrate_value = accepted_value
                    
                    current_hashrate = f"{current_hashrate_value:.1f} {unit}/s"
                    
                    # Chart history is now updated by background thread every 2 seconds
                    
                    print(f"Accepted: {accepted_value} {unit}/s, Weighted: {current_hashrate}")
            
            # PRIORITY 3: Track share difficulty (ONLY "share diff" lines!)
            if 'share diff' in line_str:
                # Only parse "share diff X.XXX" - NOT "Stratum difficulty" or "block diff"
                diff_match = re.search(r'share diff ([\d.]+)', line_str, re.IGNORECASE)
                if diff_match:
                    difficulty = float(diff_match.group(1))
                    
                    # Update Session Best
                    if difficulty > session_best_difficulty:
                        session_best_difficulty = difficulty
                        print(f"🎉 New session best difficulty: {difficulty}")
                    
                    # Update All-Time Best
                    if difficulty > all_time_best_difficulty:
                        all_time_best_difficulty = difficulty
                        print(f"🏆 NEW ALL-TIME BEST DIFFICULTY: {difficulty}")
                        
                        # Save to config.json
                        try:
                            config = load_config()
                            config['all_time_best_difficulty'] = difficulty
                            config['all_time_best_difficulty_date'] = time.time()
                            save_config(config)
                        except Exception as e:
                            print(f"Error saving all-time best difficulty: {e}")
            
            print(f"Miner: {line_str}")
    except Exception as e:
        print(f"Error monitoring miner: {e}")

def test_pool_connection(pool_url, btc_address, worker_name="test"):
    """Test connection to mining pool with fast feedback"""
    try:
        # Normalize pool URL
        pool_url = normalize_pool_url(pool_url)
        
        if not pool_url or not btc_address:
            return False, "Pool URL and Bitcoin address are required"
        
        username = f"{btc_address}.{worker_name}"
        
        # Hardcoded start difficulty (optimal for CPU mining)
        start_difficulty = 0.1
        
        # Format password with difficulty
        password = f"d={start_difficulty}"
        
        # Start cpuminer test
        cmd = [
            'cpuminer',
            '-a', 'sha256d',
            '-o', pool_url,
            '-u', username,
            '-p', password,
            '-t', '1',  # Just 1 thread for testing
            '--no-color'
        ]
        
        print(f"Testing connection to: {pool_url}")
        
        # Start process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1
        )
        
        output_lines = []
        start_time = time.time()
        connection_successful = False
        error_message = None
        
        # Success indicators - any of these means connection works
        success_indicators = [
            'Stratum difficulty set to',
            'Stratum session id:',
            'asks job'
        ]
        
        # Error patterns - any of these means connection failed
        error_patterns = {
            'Empty reply from server': "Pool did not respond - check URL and port",
            'Connection refused': "Connection refused - pool may be offline",
            'Could not resolve host': "Could not resolve hostname - check pool URL",
            'Failed to connect': "Failed to connect - check URL and port",
            'Connection failed': "Connection failed - check URL and port",
            'Timeout': "Connection timeout - pool may be unreachable"
        }
        
        # Monitor output for max 10 seconds (but exit early on success/failure)
        while time.time() - start_time < 10:
            if process.poll() is not None:
                break
            
            line = process.stdout.readline()
            if line:
                line_str = line.decode('utf-8', errors='ignore').strip()
                output_lines.append(line_str)
                print(f"Test output: {line_str}")
                
                # Check for SUCCESS - exit immediately!
                for indicator in success_indicators:
                    if indicator in line_str:
                        connection_successful = True
                        elapsed = time.time() - start_time
                        print(f"✅ Connection successful after {elapsed:.1f}s")
                        break
                
                # If success found, break outer loop too
                if connection_successful:
                    break
                
                # Check for ERRORS - exit immediately!
                for pattern, message in error_patterns.items():
                    if pattern in line_str:
                        error_message = message
                        elapsed = time.time() - start_time
                        print(f"❌ Connection failed after {elapsed:.1f}s: {pattern}")
                        break
                
                # If error found, break outer loop too
                if error_message:
                    break
        
        # Kill the test process
        try:
            process.terminate()
            process.wait(timeout=2)
        except:
            process.kill()
        
        # Determine result
        elapsed_total = time.time() - start_time
        
        if connection_successful:
            return True, f"Connection successful! ({elapsed_total:.1f}s) Pool: {pool_url}"
        elif error_message:
            return False, f"{error_message} ({elapsed_total:.1f}s)"
        else:
            return False, "Could not establish connection within 10 seconds"
            
    except Exception as e:
        return False, f"Test failed: {str(e)}"

def validate_mining_connection(process, timeout=5):
    """
    Monitor miner output for timeout seconds to validate connection
    Returns: (success: bool, message: str)
    """
    start_time = time.time()
    output_buffer = []
    
    # Success patterns
    success_patterns = [
        "Stratum difficulty set",
        "new job",
        "accepted"
    ]
    
    # Failure patterns
    failure_patterns = [
        "connection failed",
        "Connection refused",
        "Failed to connect",
        "Invalid address",
        "authentication failed"
    ]
    
    while time.time() - start_time < timeout:
        # Check if process died
        if process.poll() is not None:
            return False, "Mining process terminated unexpectedly"
        
        # Read output (non-blocking)
        try:
            line = process.stdout.readline()
            if line:
                line_str = line.decode('utf-8', errors='ignore').strip()
                output_buffer.append(line_str)
                
                # Check for failure
                for pattern in failure_patterns:
                    if pattern.lower() in line_str.lower():
                        # Extract specific error
                        return False, f"Connection failed: {line_str}"
                
                # Check for success
                for pattern in success_patterns:
                    if pattern.lower() in line_str.lower():
                        return True, "Connected successfully"
        except:
            pass
        
        time.sleep(0.1)
    
    # Timeout reached - check if still running
    if process.poll() is None:
        # Still running, no errors detected
        return True, "Mining started (validating...)"
    else:
        return False, "Mining process failed to start"

def start_mining(config):
    """Start the cpuminer-multi process with cpulimit"""
    global miner_process, cpulimit_process, miner_output, current_hashrate
    global current_hashrate_value, current_hashrate_unit
    global cpu_core_hashrates, last_accepted_hashrate
    global hashrate_history, session_best_difficulty, all_time_best_difficulty
    global mining_start_time, mining_stopped_time
    
    if miner_process is not None and miner_process.poll() is None:
        return False, "Mining is already running"
    
    # Reset session stats
    session_best_difficulty = 0.0
    # Keep hashrate_history - don't reset! Background thread will manage it
    mining_start_time = time.time()
    mining_stopped_time = None  # Reset stopped time (new session starting)
    
    # Clear chart history for clean start
    global chart_history
    chart_history = []
    print("Chart history cleared for new mining session")
    
    # Reset hashrate tracking
    cpu_core_hashrates = {}
    last_accepted_hashrate = 0.0
    current_hashrate_value = 0.0
    current_hashrate_unit = "kH"
    current_hashrate = "0 H/s"
    
    # Load all-time best from config
    all_time_best_difficulty = config.get('all_time_best_difficulty', 0.0)
    print(f"All-time best difficulty: {all_time_best_difficulty}")
    
    # Validate configuration
    if not config.get('pool_url'):
        return False, "Pool URL is required"
    if not config.get('btc_address'):
        return False, "BTC address is required"
    
    # Normalize pool URL (fix for the issue!)
    pool_url = normalize_pool_url(config.get('pool_url'))
    
    # Save the normalized URL back to config
    config['pool_url'] = pool_url
    save_config(config)
    
    # Calculate CPU limit for cpulimit
    cpu_percentage = config.get('cpu_percentage', 10)
    cpu_limit = calculate_cpu_limit(cpu_percentage)
    cpu_count = psutil.cpu_count()
    
    # Hardcoded start difficulty (optimal for CPU mining)
    start_difficulty = 0.1
    
    # Build cpuminer command - use ALL available threads (0 = auto-detect)
    worker_name = config.get('worker_name', 'worker1')
    username = f"{config['btc_address']}.{worker_name}"
    
    # Format password with difficulty
    password = f"d={start_difficulty}"
    
    # Log the configuration for debugging
    print(f"Starting miner with normalized pool URL: {pool_url}")
    print(f"Username: {username}")
    print(f"Start Difficulty: {start_difficulty}")
    print(f"Password: {password}")
    print(f"CPU Cores: {cpu_count}")
    print(f"Target CPU %: {cpu_percentage}%")
    print(f"cpulimit value: {cpu_limit}%")
    print(f"Using ALL available threads (controlled by cpulimit)")
    
    cmd = [
        'cpuminer',
        '-a', 'sha256d',  # Algorithm (can be changed based on pool)
        '-o', pool_url,
        '-u', username,
        '-p', password,  # Password with difficulty: d=0.1
        '-t', '0',  # 0 = use all available threads
        '--no-color',  # Disable ANSI colors for cleaner output parsing
        '--debug'  # Enable debug output for more information
    ]
    
    try:
        # Start the miner process
        miner_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1
        )
        
        # Get the PID of the miner process
        miner_pid = miner_process.pid
        print(f"Miner process started with PID: {miner_pid}")
        
        # Wait a moment for the miner to fully start
        time.sleep(1)
        
        # Start cpulimit to control CPU usage
        cpulimit_cmd = [
            'cpulimit',
            '-p', str(miner_pid),
            '-l', str(cpu_limit),
            '-z'  # sleep when limit is reached (saves energy)
        ]
        
        cpulimit_process = subprocess.Popen(
            cpulimit_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        print(f"cpulimit started with PID: {cpulimit_process.pid}")
        print(f"CPU usage limited to {cpu_limit}% ({cpu_percentage}% of {cpu_count} cores)")
        
        # Clear previous output
        miner_output = []
        current_hashrate = "0 H/s"
        
        # Validate connection before declaring success
        print("Validating mining connection...")
        success, validation_msg = validate_mining_connection(miner_process, timeout=5)
        
        if not success:
            # Connection failed - cleanup
            print(f"Connection validation failed: {validation_msg}")
            try:
                miner_process.kill()
            except:
                pass
            try:
                cpulimit_process.kill()
            except:
                pass
            
            # Reset state
            miner_process = None
            cpulimit_process = None
            config['mining_active'] = False
            save_config(config)
            
            return False, validation_msg
        
        # Connection successful - start monitoring
        print(f"Connection validated: {validation_msg}")
        
        # Start monitoring thread
        monitor_thread = Thread(target=monitor_miner_output, daemon=True)
        monitor_thread.start()
        
        # Update config
        config['mining_active'] = True
        save_config(config)
        
        return True, "Mining started successfully"
    except Exception as e:
        # Cleanup if something went wrong
        if miner_process:
            try:
                miner_process.kill()
            except:
                pass
        if cpulimit_process:
            try:
                cpulimit_process.kill()
            except:
                pass
        return False, f"Failed to start mining: {str(e)}"

def stop_mining():
    """Stop the cpuminer-multi process and cpulimit"""
    global miner_process, cpulimit_process, current_hashrate, mining_start_time
    global cpu_core_hashrates, last_accepted_hashrate, current_hashrate_value, mining_stopped_time
    
    if miner_process is None or miner_process.poll() is not None:
        return False, "Mining is not running"
    
    try:
        # Terminate both processes
        print("Stopping mining processes...")
        
        # Stop cpulimit first
        if cpulimit_process and cpulimit_process.poll() is None:
            try:
                cpulimit_process.terminate()
                cpulimit_process.wait(timeout=2)
                print("cpulimit stopped")
            except subprocess.TimeoutExpired:
                cpulimit_process.kill()
                cpulimit_process.wait()
                print("cpulimit killed (timeout)")
            except Exception as e:
                print(f"Error stopping cpulimit: {e}")
        
        # Then stop the miner
        miner_process.terminate()
        
        # Wait for process to end (with timeout)
        try:
            miner_process.wait(timeout=5)
            print("Miner stopped")
        except subprocess.TimeoutExpired:
            # Force kill if it doesn't terminate
            miner_process.kill()
            miner_process.wait()
            print("Miner killed (timeout)")
        
        miner_process = None
        cpulimit_process = None
        
        # Mark when mining was stopped (for chart cooldown period)
        mining_stopped_time = time.time()
        
        # Reset hashrate tracking completely
        cpu_core_hashrates = {}
        last_accepted_hashrate = 0.0
        current_hashrate_value = 0.0
        current_hashrate = "0 H/s"
        mining_start_time = None
        
        # Update config
        config = load_config()
        config['mining_active'] = False
        save_config(config)
        
        return True, "Mining stopped successfully"
    except Exception as e:
        return False, f"Failed to stop mining: {str(e)}"

@app.route('/')
def index():
    """Serve the main dashboard page"""
    return send_file('index.html')

@app.route('/static/<path:path>')
def send_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    config = load_config()
    return jsonify(config)

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration"""
    try:
        new_config = request.json
        
        # Validate CPU percentage
        cpu_percentage = new_config.get('cpu_percentage', 50)
        if cpu_percentage < 1 or cpu_percentage > 100:
            return jsonify({"success": False, "message": "CPU percentage must be between 1 and 100"}), 400
        
        # Load current config and update fields
        config = load_config()
        
        # Normalize pool URL before saving
        pool_url = normalize_pool_url(new_config.get('pool_url', ''))
        
        config.update({
            'pool_url': pool_url,
            'btc_address': new_config.get('btc_address', ''),
            'worker_name': new_config.get('worker_name', ''),
            'cpu_percentage': cpu_percentage
        })
        
        if save_config(config):
            return jsonify({"success": True, "message": "Configuration saved successfully"})
        else:
            return jsonify({"success": False, "message": "Failed to save configuration"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/start', methods=['POST'])
def start():
    """Start mining"""
    config = load_config()
    success, message = start_mining(config)
    
    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "message": message}), 400

@app.route('/api/stop', methods=['POST'])
def stop():
    """Stop mining"""
    success, message = stop_mining()
    
    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "message": message}), 400

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """Test connection to mining pool"""
    try:
        data = request.json
        pool_url = data.get('pool_url', '')
        btc_address = data.get('btc_address', '')
        worker_name = data.get('worker_name', 'test')
        
        success, message = test_pool_connection(pool_url, btc_address, worker_name)
        
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "message": message}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"Test error: {str(e)}"}), 500

@app.route('/api/status', methods=['GET'])
def status():
    """Get mining status"""
    global miner_process, cpulimit_process, current_hashrate, miner_output
    global session_best_difficulty, all_time_best_difficulty
    
    is_running = miner_process is not None and miner_process.poll() is None
    cpulimit_running = cpulimit_process is not None and cpulimit_process.poll() is None
    
    # Get CPU info
    cpu_count = psutil.cpu_count()
    config = load_config()
    cpu_percentage = config.get('cpu_percentage', 50)
    cpu_limit = calculate_cpu_limit(cpu_percentage)
    
    # Get live system stats
    system_stats = get_system_stats()
    
    # Get mining uptime
    uptime_seconds = get_mining_uptime()
    uptime_formatted = format_uptime(uptime_seconds) if is_running else "00:00:00"
    
    return jsonify({
        "running": is_running,
        "hashrate": current_hashrate if is_running else "0 H/s",
        "cpu_count": cpu_count,
        "cpu_percentage": cpu_percentage if is_running else 0,
        "cpu_limit": cpu_limit if is_running else 0,
        "cpulimit_active": cpulimit_running,
        "cpu_usage_live": system_stats['cpu_usage_live'],
        "cpu_temp": system_stats['cpu_temp'],
        "cpu_temp_warning": system_stats['cpu_temp_warning'],
        "ram_used_gb": system_stats['ram_used_gb'],
        "ram_total_gb": system_stats['ram_total_gb'],
        "ram_percent": system_stats['ram_percent'],
        "mining_uptime": uptime_formatted,
        "mining_uptime_seconds": uptime_seconds,
        "session_best_difficulty": session_best_difficulty,
        "all_time_best_difficulty": config.get('all_time_best_difficulty', 0.0),
        "all_time_best_difficulty_date": config.get('all_time_best_difficulty_date'),
        "recent_output": miner_output[-50:] if miner_output else [],  # Show last 50 lines
        "full_output": miner_output if miner_output else []  # Full output available
    })

@app.route('/api/hashrate-history', methods=['GET'])
def get_hashrate_history():
    """Get hashrate history for charting"""
    global chart_history
    
    # Optional limit parameter
    limit = request.args.get('limit', 100, type=int)
    limit = min(limit, 300)  # Max 300 datapoints (10 minutes at 2-second intervals)
    
    # Return chart_history (already sorted by timestamp, no sorting needed)
    history_slice = chart_history[-limit:] if chart_history else []
    
    return jsonify({
        "history": history_slice,
        "count": len(chart_history)
    })

if __name__ == '__main__':
    # Initialize CPU monitoring (establish baseline)
    print("Initializing CPU monitoring...")
    psutil.cpu_percent(interval=1)  # Wait 1 second for baseline
    print("CPU monitoring initialized")
    
    # Start chart history writer thread for smooth, regular updates
    chart_thread = Thread(target=chart_history_writer, daemon=True)
    chart_thread.start()
    print("Chart history writer started (2 second interval for smooth chart)")
    
    # Check if mining was active on last run
    config = load_config()
    if config.get('mining_active'):
        # Don't auto-start, just reset the flag
        config['mining_active'] = False
        save_config(config)
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
