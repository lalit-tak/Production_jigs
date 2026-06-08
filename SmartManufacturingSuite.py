import queue
import tkinter as tk
from tkinter import ttk, messagebox
import serial
from pprint import pprint
import serial.tools.list_ports
import re
import subprocess
import time
import concurrent.futures
import threading
import pythoncom
import json
import logging
import sys
import os
import random
import psutil
import signal
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from PIL import Image, ImageTk, ImageDraw, ImageFont
import tkinter.simpledialog as simpledialog
from concurrent.futures import ThreadPoolExecutor, as_completed
import openpyxl
import win32gui
import win32con
import win32com.client
import ast
from functools import partial
import multiprocessing
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet
from os import urandom


from scripts.tests import staticDO
from scripts.tests import InstantAI

# Get current date for folder naming and filename
current_date = datetime.now().strftime("%Y-%m-%d")

# Setup directories

BASE_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))

Test_Result = os.path.join(BASE_DIR, "Test Result Excel File")
Log_folder = os.path.join(BASE_DIR, "Log files")

os.makedirs(Test_Result, exist_ok=True)
os.makedirs(Log_folder, exist_ok=True)

log_folder = os.path.join(Log_folder, f"Log_file_{current_date}")
excel_folder = os.path.join(Test_Result, f"Test_Result_{current_date}")

os.makedirs(log_folder, exist_ok=True)
os.makedirs(excel_folder, exist_ok=True)

# Enhanced file naming with timestamp
timestamp_suffix = datetime.now().strftime("%H%M%S")
file_name = os.path.join(excel_folder, f"{current_date}_IMG_TEST_RESULT.xlsx")

def log_action(action, timestamp, serial_number=None):
    log_file_path = os.path.join(log_folder, "action_log.txt")
    with open(log_file_path, "a") as log_file:
        if serial_number:
            log_file.write(f"{timestamp} - Serial Number: {serial_number} - {action}\n")
        else:
            log_file.write(f"{timestamp} - {action}\n")

logging.basicConfig(
    filename=os.path.join(log_folder, f"{current_date}_program_log.txt"),
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

def _function_wrapper(func, queue, args, kwargs):
    try:
        output = func(*args, **kwargs)
        queue.put(("success", output))
    except Exception as e:
        queue.put(("error", str(e)))

class ProcessManager:
    """Enhanced process management with forced termination capabilities"""
    
    def __init__(self):
        self.active_processes = {}
        self.process_lock = threading.Lock()
    
    def run_process_with_timeout(self, cmd, timeout, station_num, test_name):
        """Run a process with robust timeout and forced termination"""
        process = None
        start_time = time.time()
        
        try:
            logging.info(f"Station {station_num}: Starting process for {test_name} with {timeout}s timeout")
            
            # Start the process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            
            # Register the process
            with self.process_lock:
                self.active_processes[station_num] = {
                    'process': process,
                    'start_time': start_time,
                    'test_name': test_name,
                    'timeout': timeout
                }
            
            # Wait for completion with timeout
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                return_code = process.returncode
                
                # Unregister the process
                with self.process_lock:
                    if station_num in self.active_processes:
                        del self.active_processes[station_num]
                
                logging.info(f"Station {station_num}: Process completed normally in {time.time() - start_time:.2f}s")
                return stdout, stderr, return_code, False  # False = not timed out
                
            except subprocess.TimeoutExpired:
                logging.error(f"Station {station_num}: Process timed out after {timeout}s, attempting forced termination")
                
                # Force kill the process and all its children
                self._force_kill_process_tree(process, station_num, test_name)
                
                # Unregister the process
                with self.process_lock:
                    if station_num in self.active_processes:
                        del self.active_processes[station_num]
                
                return "", f"Process timed out after {timeout} seconds", -1, True  # True = timed out
                
        except Exception as e:
            logging.error(f"Station {station_num}: Exception starting process: {e}")
            
            if process:
                self._force_kill_process_tree(process, station_num, test_name)
                
            # Unregister the process
            with self.process_lock:
                if station_num in self.active_processes:
                    del self.active_processes[station_num]
            
            return "", f"Exception: {str(e)}", -1, False
    
    def _force_kill_process_tree(self, process, station_num, test_name):
        """Forcefully kill a process and all its children"""
        try:
            # Get the process PID
            pid = process.pid
            logging.warning(f"Station {station_num}: Force killing process tree for {test_name} (PID: {pid})")
            
            # Try to get the process and its children using psutil
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                
                # Kill all children first
                for child in children:
                    try:
                        logging.warning(f"Station {station_num}: Killing child process PID: {child.pid}")
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                
                # Kill the parent process
                try:
                    parent.kill()
                    logging.warning(f"Station {station_num}: Killed parent process PID: {pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                
                # Wait for processes to die
                gone, alive = psutil.wait_procs(children + [parent], timeout=3)
                
                # Force kill any remaining processes
                for p in alive:
                    try:
                        p.kill()
                        logging.warning(f"Station {station_num}: Force killed remaining process PID: {p.pid}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                        
            except psutil.NoSuchProcess:
                logging.info(f"Station {station_num}: Process {pid} already terminated")
            
            # Fallback: use subprocess methods
            try:
                process.kill()
                process.wait(timeout=2)
            except:
                pass
            
            # Platform-specific force kill as last resort
            if sys.platform == "win32":
                try:
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], 
                                 capture_output=True, timeout=5)
                    logging.warning(f"Station {station_num}: Used taskkill for PID: {pid}")
                except:
                    pass
            else:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                    logging.warning(f"Station {station_num}: Used killpg for PID: {pid}")
                except:
                    pass
                    
        except Exception as e:
            logging.error(f"Station {station_num}: Error in force kill: {e}")
    
    def kill_station_processes(self, station_num):
        """Kill all processes for a specific station"""
        with self.process_lock:
            if station_num in self.active_processes:
                process_info = self.active_processes[station_num]
                process = process_info['process']
                test_name = process_info['test_name']
                
                logging.warning(f"Station {station_num}: Killing process for {test_name}")
                self._force_kill_process_tree(process, station_num, test_name)
                del self.active_processes[station_num]
    
    def get_active_processes(self):
        """Get information about active processes"""
        with self.process_lock:
            return dict(self.active_processes)
    
    def cleanup_all_processes(self):
        """Clean up all active processes"""
        with self.process_lock:
            for station_num, process_info in list(self.active_processes.items()):
                process = process_info['process']
                test_name = process_info['test_name']
                logging.warning(f"Station {station_num}: Cleaning up process for {test_name}")
                self._force_kill_process_tree(process, station_num, test_name)
            self.active_processes.clear()



    def run_function_with_timeout(self, func, timeout, station_num, test_name, *args, **kwargs):

        queue = multiprocessing.Queue()

        process = multiprocessing.Process(
            target=_function_wrapper,
            args=(func, queue, args, kwargs)
        )

        start_time = time.time()
        process.start()

        with self.process_lock:
            self.active_processes[station_num] = {
                "process": process,
                "start_time": start_time,
                "test_name": test_name,
                "timeout": timeout
            }

        process.join(timeout)

        if process.is_alive():
            logging.error(f"Station {station_num}: {test_name} timed out")
            process.terminate()
            process.join()

            with self.process_lock:
                self.active_processes.pop(station_num, None)

            return "", f"Function timed out after {timeout} seconds", -1, True
        
        status, value = queue.get() if not queue.empty() else ("error", "No result")
        queue.close()
        queue.join_thread()

        with self.process_lock:
            self.active_processes.pop(station_num, None)

        if status == "success":
            return value if value else "", "", 0, False
        else:
            return "", value, -1, False

class ExcelLogger:
    """Enhanced Excel logging with detailed test data and formatting"""
    
    def __init__(self, main_file):
        self.main_file = main_file
        self.lock = threading.Lock()
        
        # Color schemes for Excel formatting
        self.colors = {
            'pass': PatternFill(start_color='C8E6C9', end_color='C8E6C9', fill_type='solid'),
            'fail': PatternFill(start_color='FFCDD2', end_color='FFCDD2', fill_type='solid'),
            'header': PatternFill(start_color='E3F2FD', end_color='E3F2FD', fill_type='solid'),
            'warning': PatternFill(start_color='FFF3E0', end_color='FFF3E0', fill_type='solid')
        }
        
        self.fonts = {
            'header': Font(bold=True, size=11),
            'normal': Font(size=10),
            'bold': Font(bold=True, size=10)
        }
        
        self.initialize_excel_files()
    
    def initialize_excel_files(self):
        """Initialize both main and detailed Excel files with headers"""
        with self.lock:
            # Initialize main results file
            if not os.path.exists(self.main_file):
                wb = Workbook()
                ws = wb.active
                ws.title = "Test Results Summary"
                
                headers = [
                    "Test Session", "Station", "PCBA Serial Number", "Test Start Time", "Test End Time",
                    "Mapped with COM Port", "BOOT Mode Initialization", "BOOT MODE ON", "Boost Output", "Boost Output Status", "Super Cap Voltage",  "Super Cap Voltage Status", "BOOT MODE OFF", "SUPERCAP DISCHARGE", "Discharge Output",  "Discharge Output Status", "Discharge Super Cap Voltage", "Discharge Super Cap Voltage Status", "MODULE SUPPLY OFF","Overall Status", "Total Test Time (s)", "Timestamp"
                ]
                
                ws.append(headers)
                self._format_header_row(ws, len(headers))
                wb.save(self.main_file)
    
    def _format_header_row(self, worksheet, num_columns):
        """Format the header row with styling"""
        for col in range(1, num_columns + 1):
            cell = worksheet.cell(row=1, column=col)
            cell.fill = self.colors['header']
            cell.font = self.fonts['header']
            cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # def log_final_results(self, session_id, station, serial_number, test_results, 
    #                      start_time, end_time):
    def log_final_results(self, overall_result):
        """Log final test results to main file with proper value extraction"""
        with self.lock:
            try:
                wb = load_workbook(self.main_file)
                ws = wb.active
                for result in overall_result:
                    session_id, station, serial_number, test_results, start_time, end_time = result
                    overall_status = test_results.get('overall_result').get('status', 'FAIL')
                    total_time = (end_time - start_time).total_seconds() if end_time and start_time else 0
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Extract individual test results with proper value handling
                    COM_PORT_MAPPING = test_results.get('COM_PORT_MAPPING', {})
                    STATIC_DO0_ON = test_results.get('BOOT Mode Initialization', {})
                    BOOT_Mode = test_results.get('BOOT MODE ON', {})
                    Instant_AI_Boost_Output = test_results.get("Boost Output", {})
                    Instant_AI_Super_Cap_Voltage = test_results.get("Super Cap Voltage", {})
                    BOOT_MODE_OFF = test_results.get('BOOT MODE OFF', {})
                    SUPERCAP_DISCHARGE = test_results.get('SUPERCAP DISCHARGE', {})
                    DISCHARGE_OUTPUT = test_results.get('DISCHARGE OUTPUT', {})
                    Discharge_Super_Cap_Voltage = test_results.get('Discharge Super Cap Voltage', {})
                    MODULE_SUPPLY_OFF = test_results.get('MODULE SUPPLY OFF', {})
                    overall_station_status = test_results.get('overall_result', {})
                    

                    row_data = [
                        session_id, station, serial_number,
                        start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else "",
                        end_time.strftime("%Y-%m-%d %H:%M:%S") if end_time else "",
                        COM_PORT_MAPPING.get('status', 'FAIL'),
                        STATIC_DO0_ON.get('status','FAIL'),
                        BOOT_Mode.get('status','FAIL'),
                        Instant_AI_Boost_Output.get("value", 0),
                        Instant_AI_Boost_Output.get("status", "FAIL"),
                        Instant_AI_Super_Cap_Voltage.get("value", 0),
                        Instant_AI_Super_Cap_Voltage.get("status", "FAIL"),
                        BOOT_MODE_OFF.get('status','FAIL'),
                        SUPERCAP_DISCHARGE.get('status','FAIL'),
                        DISCHARGE_OUTPUT.get('value',0),
                        DISCHARGE_OUTPUT.get('status','FAIL'),
                        Discharge_Super_Cap_Voltage.get('value',0),
                        Discharge_Super_Cap_Voltage.get('status', 'FAIL'),
                        MODULE_SUPPLY_OFF.get('status','FAIL'),
                        overall_station_status.get('status', 'FAIL')
                    ]
                    # row_data.append(overall_status)
                    row_data.append(f"{total_time:.2f}")
                    row_data.append(timestamp)


                    
                    ws.append(row_data)
                    
                    # Apply formatting to the entire row based on overall status
                    row_num = ws.max_row
                    fill_color = self.colors['pass'] if overall_status == 'PASS' else self.colors['fail']
                    
                    for col in range(1, len(row_data) + 1):
                        cell = ws.cell(row=row_num, column=col)
                        if col == len(row_data) - 1:  # Overall status column
                            cell.fill = fill_color
                            cell.font = self.fonts['bold']
                    
                    logging.info(f"Logged final results for Station {station}, Serial: {serial_number}, Status: {overall_status}")
                wb.save(self.main_file)
            except Exception as e:
                logging.error(f"Error logging final results: {e}")

class SerialScanner:
    """Enhanced serial scanning functionality with retry mechanism and station isolation"""
    
    def __init__(self, port_config, baud_rate=9600, trigger_command=b'*T', timeout=3, max_retries=1, retry_delay=2):
        self.port_config = port_config
        self.baud_rate = baud_rate
        self.trigger_command = trigger_command
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.scan_results = {}
        self.scan_lock = threading.Lock()
        self.retry_stations = set()
    
    def scan_single_port(self, station_num, port, is_retry=False):
        """Scan a single COM port for serial number with improved error handling"""
        retry_text = " (RETRY)" if is_retry else ""

        try:
            
            with serial.Serial(port, self.baud_rate, timeout=self.timeout) as ser:
                ser.write(self.trigger_command)
                logging.debug(f"[Station {station_num}] Sent trigger command to {port}{retry_text}")
                
                time.sleep(1)
                scanned_data = ser.readline().decode('utf-8', errors='ignore').strip()
                # scanned_data = ser.read_all()

                # scanned_data = "ABC-123E2"

                with self.scan_lock:
                    if scanned_data:
                        self.scan_results[station_num] = {
                            'serial': scanned_data,
                            'port': port,
                            'status': 'success',
                            'retry_attempt': is_retry
                        }
                        self.retry_stations.discard(station_num)
                        logging.info(f"[Station {station_num}] Successfully scanned{retry_text}: {scanned_data}")
                    else:
                        self.scan_results[station_num] = {
                            'serial': None,
                            'port': port,
                            'status': 'no_data',
                            'retry_attempt': is_retry
                        }
                        if not is_retry:
                            self.retry_stations.add(station_num)
                        logging.warning(f"[Station {station_num}] No data received from {port}{retry_text}")
                        
        except serial.SerialException as e:
            with self.scan_lock:
                self.scan_results[station_num] = {
                    'serial': None,
                    'port': port,
                    'status': 'error',
                    'error': str(e),
                    'retry_attempt': is_retry
                }
                if not is_retry:
                    self.retry_stations.add(station_num)
            logging.error(f"[Station {station_num}] Serial error on {port}{retry_text}: {e}")
        except Exception as e:
            with self.scan_lock:
                self.scan_results[station_num] = {
                    'serial': None,
                    'port': port,
                    'status': 'error',
                    'error': str(e),
                    'retry_attempt': is_retry
                }
                if not is_retry:
                    self.retry_stations.add(station_num)
            logging.error(f"[Station {station_num}] Unexpected error on {port}{retry_text}: {e}")
    
    def scan_all_configured_ports(self):
        """Scan all configured COM ports in parallel with retry mechanism and station isolation"""
        self.scan_results.clear()
        self.retry_stations.clear()
        
        logging.info("Starting initial scan of all configured ports")
        self._perform_scan_batch(is_retry=False)
        if self.retry_stations and self.max_retries > 0:
            logging.info(f"Retrying failed stations: {list(self.retry_stations)}")
            time.sleep(self.retry_delay)
            self._perform_scan_batch(is_retry=True, stations_to_scan=self.retry_stations.copy())
        
        return self.scan_results.copy()
    
    def _perform_scan_batch(self, is_retry=False, stations_to_scan=None):
        """Perform a batch of scans (either initial or retry) with station isolation"""
        threads = []
        
        if stations_to_scan is None:
            stations_to_scan = self.port_config.keys()
        
        for station_num in stations_to_scan:
            port = self.port_config.get(station_num)
            if port:
                thread = threading.Thread(
                    target=self.scan_single_port, 
                    args=(station_num, port, is_retry),
                    daemon=True
                )
                threads.append(thread)
                thread.start()
        
        for thread in threads:
            thread.join()
        
        return self.scan_results.copy()

class ModernUI:
    """Helper class for modern UI elements"""
    
    @staticmethod
    def create_rounded_rectangle(canvas, x1, y1, x2, y2, radius=25, **kwargs):
        """Draw a rounded rectangle on a canvas"""
        points = [
            x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius,
            x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2,
            x1, y2, x1, y2-radius, x1, y1+radius, x1, y1
        ]
        return canvas.create_polygon(points, **kwargs, smooth=True)
    
    @staticmethod
    def create_status_indicator(parent, size=60, initial_state="pending"):
        """Create a modern status indicator"""
        canvas = tk.Canvas(parent, width=size, height=size, bg=parent["bg"], highlightthickness=0)
        
        states = {
            "pending": {"fill": "#E0E0E0", "outline": "#BDBDBD", "symbol": "⏱", "symbol_color": "#757575"},
            "scanning": {"fill": "#FFE082", "outline": "#FFC107", "symbol": "📡", "symbol_color": "#F57F17"},
            "retrying": {"fill": "#FFCC80", "outline": "#FF9800", "symbol": "🔄", "symbol_color": "#E65100"},
            "running": {"fill": "#90CAF9", "outline": "#2196F3", "symbol": "⏳", "symbol_color": "#0D47A1"},
            "success": {"fill": "#A5D6A7", "outline": "#4CAF50", "symbol": "✓", "symbol_color": "#1B5E20"},
            "failure": {"fill": "#EF9A9A", "outline": "#F44336", "symbol": "✕", "symbol_color": "#B71C1C"}
        }
        
        canvas.create_oval(3, 3, size-1, size-1, fill="#F5F5F5", outline="#E0E0E0", width=2)
        
        state_config = states.get(initial_state, states["pending"])
        inner_size = 4
        canvas.create_oval(inner_size, inner_size, size-inner_size, size-inner_size, 
                          fill=state_config["fill"], outline=state_config["outline"], width=2)
        
        canvas.create_text(size/2, size/2, text=state_config["symbol"], 
                          fill=state_config["symbol_color"], font=("Arial", int(size/2), "bold"))
        
        return canvas

    @staticmethod
    def update_status_indicator(canvas, state):
        """Update the status indicator to a new state"""
        size = canvas.winfo_width()
        if size < 10:
            size = 60
        
        canvas.delete("all")
        
        states = {
            "pending": {"fill": "#E0E0E0", "outline": "#BDBDBD", "symbol": "⏱", "symbol_color": "#757575"},
            "scanning": {"fill": "#FFE082", "outline": "#FFC107", "symbol": "📡", "symbol_color": "#F57F17"},
            "retrying": {"fill": "#FFCC80", "outline": "#FF9800", "symbol": "🔄", "symbol_color": "#E65100"},
            "running": {"fill": "#90CAF9", "outline": "#2196F3", "symbol": "⏳", "symbol_color": "#0D47A1"},
            "success": {"fill": "#4CAF50", "outline": "#2E7D32", "symbol": "✓", "symbol_color": "#FFFFFF"},
            "failure": {"fill": "#F44336", "outline": "#B71C1C", "symbol": "✕", "symbol_color": "#FFFFFF"}
        }
        
        state_config = states.get(state, states["pending"])
        
        gradient_colors = ["#D0D0D0", "#A0A0A0"]
        steps = 10
        step_size = (size - 4) / (2 * steps)
        
        for i in range(steps):
            color = gradient_colors[i % 2]
            canvas.create_oval(2 + i * step_size, 2 + i * step_size, size - 2 - i * step_size, size - 2 - i * step_size,
                              outline=color, width=1)
        
        gradient_offset = 4
        canvas.create_oval(gradient_offset, gradient_offset, size - gradient_offset, size - gradient_offset,
                          fill=state_config["fill"], outline=state_config["outline"], width=2)
        
        highlight_offset = 8
        canvas.create_arc(highlight_offset, highlight_offset, size - highlight_offset, size - highlight_offset,
                          start=30, extent=120, style="arc", outline="#FFFFFF", width=2)
        
        shadow_offset = 1
        canvas.create_oval(gradient_offset + shadow_offset, gradient_offset + shadow_offset,
                          size - gradient_offset - shadow_offset, size - gradient_offset - shadow_offset,
                          outline="#808080", width=1)
        
        canvas.create_text(size / 2, size / 2, text=state_config["symbol"],
                          fill=state_config["symbol_color"], font=("Arial", int(size / 2.5), "bold"))

    @staticmethod
    def create_modern_button(parent, text, command, width=120, height=40, bg="#4CAF50", hover_bg="#388E3C"):
        def on_enter(e):
            if button._enabled:
                button["bg"] = hover_bg
                button["relief"] = "raised"
        
        def on_leave(e):
            if button._enabled:
                button["bg"] = bg
                button["relief"] = "ridge"
        
        def on_press(e):
            if button._enabled:
                button["relief"] = "sunken"
        
        def on_release(e):
            if button._enabled:
                button["relief"] = "raised"
                command()   # only fire if enabled ✅

        button = tk.Label(
            parent,
            text=text,
            width=width, height=height,
            bg=bg, fg="white",
            font=("Arial", 12, "bold"),
            bd=3, relief="ridge",
            padx=5, pady=5,
            cursor="hand2"
        )

        # Enable/disable state flag
        button._enabled = True
        button._bg = bg
        button._hover_bg = hover_bg

        # Bind events
        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
        button.bind("<ButtonPress-1>", on_press)
        button.bind("<ButtonRelease-1>", on_release)

        # Custom methods
        def enable():
            button._enabled = True
            button.config(fg="white", bg=button._bg, cursor="hand2")

        def disable():
            button._enabled = False
            button.config(fg="gray", bg="#B0BEC5", cursor="arrow")

        button.enable = enable
        button.disable = disable

        button.pack_propagate(False)
        return button

    @staticmethod
    def create_task_indicator(parent, text, initial_state="pending"):
        """Create a task indicator with icon and text"""
        frame = tk.Frame(parent, bg=parent["bg"])
        
        states = {
            "pending": {"symbol": "⏱", "color": "#757575"},
            "running": {"symbol": "⏳", "color": "#2196F3"},
            "success": {"symbol": "✓", "color": "#4CAF50"},
            "failure": {"symbol": "✕", "color": "#F44336"}
        }
        
        state_config = states.get(initial_state, states["pending"])
        
        icon_label = tk.Label(frame, text=state_config["symbol"], fg=state_config["color"], 
                             bg=parent["bg"], font=("Arial", 12, "bold"))
        icon_label.pack(side=tk.LEFT, padx=(0, 5))
        
        text_label = tk.Label(frame, text=text, anchor="w", bg=parent["bg"], font=("Arial", 9))
        text_label.pack(side=tk.LEFT, fill=tk.X)
        
        return frame, icon_label

class ManufacturingSuite:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Manufacturing Suite : IMG- [SMS] [Version 1.0.0.4, 01-MAY-26]")
        self.root.geometry("1350x700")
        self.root.configure(bg="#F5F5F5")
        
        # Initialize process manager
        self.process_manager = ProcessManager()

        self.test_thread = None
        
        self.root.attributes('-fullscreen', True)
        self.root.bind("<Escape>", self.exit_fullscreen)
        
        # Initialize Excel logger
        self.excel_logger = None
        self.excel_logger = ExcelLogger(file_name)
        
        # Generate unique session ID for this test run
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Load configuration for COM ports mapping
        self.scanner_ports = {}
        self.optical_ports = {}
        self.dec_port_id = "USB-4716,BID#0"
        self.firmware = "0.0.0.0"
        self.voltage = {}
        self.max_retries = 1
        self.test_timeout = 60
        self.retry_delay = 2
        self.PASSWORD = b"Polaris@1234"
        self.ITERATIONS = 390000
        self.CONFIG_FILE_NAME_ENC = "serial_config.enc"

        self.load_serial_config(self.CONFIG_FILE_NAME_ENC)
  
        # Initialize serial scanner with retry capability (uses MAX_RETRIE, RETRY_DELA from config)
        self.serial_scanner = SerialScanner(self.scanner_ports, max_retries=self.max_retries, retry_delay=self.retry_delay)
        
        self.active_ports_serials = []
        self.task_labels = {}
        self.station_numbers = {}
        self.entries = {}
        self.scanned_serials = set()
        self.eng_var = tk.BooleanVar()
        self.status_indicators = {}
        self.task_indicators = {}
        
        # Track failed stations
        self.failed_stations = set()

        # Connectivity alarm: stations awaiting user confirmation before boost retry
        self.connectivity_alarm_stations = set()   # set of (station_num, serial_number, voltage) — Boost + Super Cap
        self.discharge_alarm_stations = set()      # set of (station_num, serial_number, voltage) — Discharge Output + Dis Super Cap
        
        # Enhanced test tracking with timing - per station tracking
        self.test_completion_lock = threading.Lock()
        self.station_completed_tests = {}  # Track completion per station
        self.completed_tests = {
            "Mapped with COM Port": False,
            "BOOT Mode Initialization": False,
            "BOOT MODE ON": False,
            "Boost Output": False,
            "BOOT MODE OFF": False,
            "SUPERCAP DISCHARGE": False,
            "DISCHARGE OUTPUT": False,
            "MODULE SUPPLY OFF": False
        }
        self.station_test_results = {}
        self.station_test_times = {}  # Track start/end times per station
        
        # Create the UI components
        self.create_header()
        self.create_main_content()
        self.create_status_bar()
        

        # Timer variables
        self.start_time = None
        self.timer_running = False
        self.timer_id = None

        # Cycle and pass counters
        self.total_cycles = 0
        self.total_passed_stations = 0
        self.is_break = False
        
        # Station-specific test threads and control flags
        self.station_threads = {}
        self.station_stop_flags = {}
        
        # Flag to track if any test has failed in the programming phase
        self.programming_phase_failed = False
        
        # Start process monitoring thread
        self.monitor_running = True
        self.start_process_monitor()

    def derive_key(self, password, salt):
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(password))

    def decrypt_json(self, encrypted_json):  
        try:
            config = {}
            with open(encrypted_json, "rb") as f:
                salt = f.read(16)
                encrypted_data = f.read()
            
            key = self.derive_key(self.PASSWORD, salt)
            cipher = Fernet(key)

            decrypted_data = cipher.decrypt(encrypted_data)

            config = json.loads(decrypted_data.decode("utf-8"))
        except Exception as e:
            print("Error while decrypting serial_config.enc",e)
        return config

    def start_process_monitor(self):
        """Start a background thread to monitor processes"""
        def monitor_processes():
            while self.monitor_running:
                try:
                    active_processes = self.process_manager.get_active_processes()
                    current_time = time.time()
                    
                    for station_num, process_info in active_processes.items():
                        start_time = process_info['start_time']
                        timeout = process_info['timeout']
                        test_name = process_info['test_name']
                        
                        # Check if process has been running too long (timeout + 10 seconds grace period)
                        if current_time - start_time > timeout + 10:
                            logging.warning(f"Station {station_num}: Process {test_name} exceeded timeout by 10s, force killing")
                            self.process_manager.kill_station_processes(station_num)
                            
                            # Mark station as failed
                            self.failed_stations.add(station_num)
                            self.station_stop_flags[station_num] = True
                    
                    time.sleep(2)  # Check every 2 seconds
                except Exception as e:
                    logging.error(f"Error in process monitor: {e}")
                    time.sleep(2)
        
        self.monitor_thread = threading.Thread(target=monitor_processes, daemon=True)
        self.monitor_thread.start()

    def load_serial_config(self, path):
        """Load COM port configuration from config.txt"""
        if os.path.exists(path):
            try:
                config = self.decrypt_json(path)

                # Load Scanner Ports
                self.scanner_ports[1] = config.get('SCANNER_COM1', '')
                self.scanner_ports[2] = config.get('SCANNER_COM2', '')
                self.scanner_ports[3] = config.get('SCANNER_COM3', '')
                self.scanner_ports[4] = config.get('SCANNER_COM4', '')

                # Load Optical Ports
                self.optical_ports[1] = config.get('OPTICAL_COM1', '')
                self.optical_ports[2] = config.get('OPTICAL_COM2', '')
                self.optical_ports[3] = config.get('OPTICAL_COM3', '')
                self.optical_ports[4] = config.get('OPTICAL_COM4', '')

                # Load Dec Card Ports
                self.dec_port_id = config.get('DAC_COM', '')

                # Load Firmware Version
                self.firmware = config.get("Firmware_version", '0.0.0.0')

                # Load Test Control Parameters
                self.max_retries = config.get("MAX_RETRIE", 1)
                self.test_timeout = config.get("TEST_TIMEOUT", 60)
                self.retry_delay = config.get("RETRY_DELA", 2)

                # Load Voltages
                self.voltage["min_Boost_voltage"] = config.get("min_Boost_voltage", 0.0)
                self.voltage["max_Boost_voltage"] = config.get("max_Boost_voltage", 0.0)
                self.voltage["min_Dis_super_cap_voltage"] = config.get("min_Dis_super_cap_voltage", 0.0)
                self.voltage["max_Dis_super_cap_voltage"] = config.get("max_Dis_super_cap_voltage", 0.0)
                self.voltage["min_super_cap_voltage"] = config.get("min_super_cap_voltage", 0.0)
                self.voltage["max_super_cap_voltage"] = config.get("max_super_cap_voltage", 0.0)
                self.voltage["min_Discharge_voltage"] = config.get("min_Discharge_voltage", 0.0)
                self.voltage["max_Discharge_voltage"] = config.get("max_Discharge_voltage", 0.0)
            
                logging.info(f"Loaded scanner ports: {self.scanner_ports}")
                logging.info(f"Loaded optical ports: {self.optical_ports}")
                logging.info(f"Loaded Dack Card ports: {self.dec_port_id}")
                logging.info(f"Loaded Firmware version: {self.firmware}")
                logging.info(f"Loaded Voltages: {self.voltage}")
                logging.info(f"Loaded Test Control: max_retries={self.max_retries}, test_timeout={self.test_timeout}s, retry_delay={self.retry_delay}s")

            except Exception as e:
                logging.error(f"Error loading serial configuration: {e}")
                messagebox.showerror("Config Error", f"Failed to load serial configuration: {e}")
        else:
            logging.warning(f"serial config file not found at: {path}")
            messagebox.showwarning("serial config Missing", 
                                 f"serial configuration file not found: {path}\n"
                                 "Please create serial_config.enc")

    def auto_scan_all_serials(self):
        """Auto scan serial numbers from all configured COM ports with enhanced logging"""
        self.status_label.config(text="Auto-scanning serial numbers...")
        
        # Update status indicators to show scanning
        for station_num in self.station_numbers.keys():
            if station_num in self.scanner_ports:
                ModernUI.update_status_indicator(self.status_indicators[station_num], "scanning")
        
        self.root.update()
        
        # Perform the scan
        scan_results = self.serial_scanner.scan_all_configured_ports()
        
        # Process scan results with enhanced logging
        successful_scans = 0
        failed_scans = 0
        retried_scans = 0
        for station_num, result in scan_results.items():
            if result['status'] == 'success' and result['serial']:
                self.station_numbers[station_num].set(result['serial'])
                self.finalize_serial_entry(station_num)
                successful_scans += 1
                
                if result.get('retry_attempt', False):
                    retried_scans += 1
                    logging.info(f"Station {station_num}: Retry successful - Scanned {result['serial']} from {result['port']}")
                else:
                    logging.info(f"Station {station_num}: Scanned {result['serial']} from {result['port']}")
            else:
                failed_scans += 1
                self.failed_stations.add(station_num)
                error_msg = result.get('error', 'No data received')
                retry_text = " (after retry)" if result.get('retry_attempt', False) else ""

                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_action(f"Station {station_num} scan failed{retry_text}: {error_msg}", timestamp)
                
                logging.warning(f"Station {station_num}: Scan failed{retry_text} - {error_msg}")
                ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")
                
                for task_name in self.task_indicators[station_num]:
                    self.task_indicators[station_num][task_name].config(text="✕", fg="#F44336")
        
        # Update status with detailed information
        status_parts = []
        if successful_scans > 0:
            status_parts.append(f"{successful_scans} successful")
        if retried_scans > 0:
            status_parts.append(f"{retried_scans} recovered on retry")
        if failed_scans > 0:
            status_parts.append(f"{failed_scans} failed")
        
        if status_parts:
            status_msg = f"Auto-scan completed: {', '.join(status_parts)}"
        else:
            status_msg = "Auto-scan completed: No serial numbers found"
        
        self.status_label.config(text=status_msg)
            
        logging.info(f"Scan summary: {successful_scans} successful ({retried_scans} after retry), {failed_scans} failed")
        if failed_scans > 0:
            logging.warning(f"Failed stations (after retry): {list(self.failed_stations)}")
        if retried_scans > 0:
            logging.info(f"Stations recovered on retry: {retried_scans}")

    def finalize_serial_entry(self, station_num):
        """Finalize a serial entry (lock the field and update status)"""
        entry_widget = self.entries[station_num]
        serial_value = self.station_numbers[station_num].get().strip()
        
        if serial_value:
            entry_widget.config(state="disabled", disabledbackground="#F5F5F5", disabledforeground="#333")
            self.scanned_serials.add(serial_value)
            ModernUI.update_status_indicator(self.status_indicators[station_num], "pending")

    def handle_manual_entry(self, event, station_num):
        """Handle manual serial number entry"""
        serial_value = self.station_numbers[station_num].get().strip()
        if serial_value:
            self.failed_stations.discard(station_num)
            self.finalize_serial_entry(station_num)

    def exit_fullscreen(self, event=None):
        self.root.attributes('-fullscreen', False)
        
    def create_header(self):
        # Create a frame for the header
        header_frame = tk.Frame(self.root, bg="#1976D2", height=72)
        header_frame.pack(fill=tk.X)
        
        # Logo frame on the left
        logo_frame = tk.Frame(header_frame, bg="#1976D2", width=200)
        logo_frame.pack(side=tk.LEFT, padx=20, pady=10)
        
        # Try to load and display the logo
        if os.path.exists("logo.png"):
            try:
                original_image = Image.open("logo.png")
                resized_image = original_image.resize((125, 40))
                logo_image = ImageTk.PhotoImage(resized_image)
                logo_label = tk.Label(logo_frame, image=logo_image, bg="#1976D2")
                logo_label.image = logo_image
            except:
                logo_label = tk.Label(logo_frame, text="POLARIS", font=("Arial", 20, "bold"), 
                                    bg="#1976D2", fg="white")
        else:
            logo_label = tk.Label(logo_frame, text="POLARIS", font=("Arial", 20, "bold"), 
                                bg="#1976D2", fg="white")

        logo_label.pack(side=tk.LEFT)
        
        # Add title
        title_label = tk.Label(header_frame, text="Smart Manufacturing Suite", 
                              font=("Arial", 18, "bold"), bg="#1976D2", fg="white")
        title_label.pack(side=tk.LEFT, padx=5, pady=15)

        
        # Add version info
        version_label = tk.Label(header_frame, text="V1.0.0.4 | 01-May-26", 
                                font=("Arial", 10), bg="#1976D2", fg="#E1F5FE")
        version_label.pack(side=tk.LEFT, padx=5, pady=15)
        
        # Add Jig info
        jig_label = tk.Label(header_frame, text="IMG Stage - 2", 
                                font=("Arial", 15, "bold"), bg="#1976D2", fg="#E1F5FE")
        jig_label.pack(side=tk.RIGHT, padx=15, pady=15)

        # Add toolbar
        toolbar_frame = tk.Frame(self.root, bg="#2196F3", height=55)
        toolbar_frame.pack(fill=tk.X)
        
        # Add buttons to toolbar
        run_btn_frame = ModernUI.create_modern_button(toolbar_frame, "▶ Run Test", self.run_test, 
                                                width=10, height=1, bg="#4CAF50", hover_bg="#388E3C")
        run_btn_frame.pack(side=tk.LEFT, padx=15, pady=7)

        
        # Bind Enter key to run_test function
        self.root.bind('<Return>', lambda event: self.run_test())

        stop_btn_frame = ModernUI.create_modern_button(toolbar_frame, "■ Stop", self.stop_test, 
                                                width=10, height=1, bg="#F44336", hover_bg="#D32F2F")
        stop_btn_frame.pack(side=tk.LEFT, padx=15, pady=7)

        new_batch_btn_frame = ModernUI.create_modern_button(toolbar_frame, "New Batch", self.show_start_batch_dialog, 
                                                        width=10, height=1, bg="#555259", hover_bg="#3b393d")
        new_batch_btn_frame.pack(side=tk.LEFT, padx=15, pady=7)
        
    def create_main_content(self):
        # Create a frame for the main content with some padding
        main_frame = tk.Frame(self.root, bg="#F5F5F5")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create a frame for the test stations
        content_frame = tk.Frame(main_frame, bg="#F5F5F5")
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Dictionary to store serial numbers for each test station
        self.station_numbers = {}
        self.task_indicators = {}

        for i in range(4):
            station_num = i + 1

            # Create a frame for each test station
            station_frame = tk.Frame(content_frame, bg="white", bd=0)
            # station_frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            station_frame.grid(row=0, column=i, padx=10, pady=10, sticky="nsew")
            
            # Add a canvas for rounded corners and shadow effect
            station_canvas = tk.Canvas(station_frame, bg="white", highlightthickness=0)
            station_canvas.pack(fill="both", expand=True)
            
            # Draw rounded rectangle for the station
            ModernUI.create_rounded_rectangle(station_canvas, 2, 2, 720, 1600, radius=10,
                                            fill="white", outline="#E0E0E0", width=2)
            
            # Create inner frame for content
            inner_frame = tk.Frame(station_canvas, bg="white")
            station_canvas.create_window(320, 400, window=inner_frame, width=620, height=800)
            
            # Station header
            header_frame = tk.Frame(inner_frame, bg="#2196F3", height=30)
            header_frame.pack(fill=tk.X)
            
            station_label = tk.Label(header_frame, text=f"Test Station {station_num}", 
                                    font=("Arial", 12, "bold"), bg="#2196F3", fg="white")
            station_label.pack(side=tk.LEFT, padx=15, pady=8)
            
            # Show configured COM port (optical port for testing)
            if station_num in self.optical_ports:
                port_label = tk.Label(header_frame, text=f"({self.optical_ports[station_num]})", 
                                    font=("Arial", 10), bg="#2196F3", fg="#E1F5FE")
                port_label.pack(side=tk.RIGHT, padx=15, pady=8)
            
            # Create status indicator
            status_indicator = ModernUI.create_status_indicator(station_canvas, size=50, initial_state="pending")
            status_indicator.place(x=250, y=150)
            self.status_indicators[station_num] = status_indicator
            
            # Serial number frame
            serial_frame = tk.Frame(inner_frame, bg="white", height=50)
            serial_frame.pack(fill=tk.X, padx=10, pady=(15, 5))
            
            serial_label = tk.Label(serial_frame, text="Serial Number:", bg="white", font=("Arial", 11))
            serial_label.pack(side=tk.LEFT, padx=(5, 5))
            
            # Entry field for serial number
            self.station_numbers[station_num] = tk.StringVar()
            entry = tk.Entry(serial_frame, textvariable=self.station_numbers[station_num], 
                           width=28, font=("Arial", 11), bd=2, relief=tk.GROOVE)
            entry.pack(side=tk.LEFT, padx=2)
            entry.bind("<Return>", lambda event, s=station_num: self.handle_manual_entry(event, s))
            self.entries[station_num] = entry
            
            # Task status frame
            task_frame = tk.Frame(inner_frame, bg="white")
            task_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
            
            # List of tasks
            tasks = [
                "Mapped with COM Port",
                "BOOT Mode Initialization",
                "BOOT MODE ON",
                "Boost Output",
                "Super Cap Voltage",
                "BOOT MODE OFF",
                "SUPERCAP DISCHARGE",
                "DISCHARGE OUTPUT",
                "Discharge Super Cap Voltage",
                'MODULE SUPPLY OFF'
            ]
            
            # Store task indicators for this station
            self.task_indicators[station_num] = {}
            
            # Display tasks with status indicators
            for task in tasks:
                task_indicator, icon_label = ModernUI.create_task_indicator(task_frame, task, initial_state="pending")
                task_indicator.pack(fill=tk.X, pady=1)
                self.task_indicators[station_num][task] = icon_label
        
        for col in range(4):
            content_frame.columnconfigure(col, weight=1)
        content_frame.rowconfigure(0, weight=1)
    
    def create_status_bar(self):
        status_frame = tk.Frame(self.root, bg="#E0E0E0", height=30)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_label = tk.Label(status_frame, text="Ready", anchor="w", bg="#E0E0E0", font=("Arial", 10))
        self.status_label.pack(side=tk.LEFT, padx=15, pady=5)

        self.batch_time = tk.Label(status_frame, text="BATCH TIME: 00:00", bg="#4CAF50", fg="white", 
                                padx=10, pady=5, font=("Arial", 10, "bold"))
        self.batch_time.pack(side=tk.RIGHT, padx=15)

        self.status = tk.Label(status_frame, text="OFFLINE", bg="#FFD700", fg="#333", 
                            padx=10, pady=5, font=("Arial", 10, "bold"))
        self.status.pack(side=tk.RIGHT, padx=15)

        self.firmware_version_label = tk.Label(status_frame, text=f"Current Firmware version: {self.firmware}", 
                                            bg="#E0E0E0", fg="#333", font=("Arial", 10 , "bold"))
        self.firmware_version_label.pack(side=tk.RIGHT, padx=10)

        self.deck_card_count = tk.Label(status_frame, text=f"Deck Card Count: 1 - 8 CH", 
                                            bg="#E0E0E0", fg="#333", font=("Arial", 10 , "bold"))
        self.deck_card_count.pack(side=tk.RIGHT, padx=10)

    def gather_com_ports_serial_numbers(self):
        """Map serial numbers to COM ports with enhanced logging"""
        self.status_label.config(text="Mapping COM ports to serial numbers...")
        self.root.update()

        self.active_ports_serials = []

        for station_num in range(1, 5):
            if station_num in self.failed_stations:
                continue

            serial_number = self.station_numbers[station_num].get().strip()
            if not serial_number:
                self.task_indicators[station_num]["Mapped with COM Port"].config(
                    text="⛔ Skipped", fg="#9E9E9E")
                self.failed_stations.add(station_num)
                continue

            optical_com_port = self.optical_ports.get(station_num)



            if optical_com_port:
                self.active_ports_serials.append((optical_com_port, serial_number, station_num))

                if self.eng_var.get():
                    self.station_numbers[station_num].set(f"{optical_com_port} - {serial_number}")
                    self.entries[station_num].config(
                        state="disabled", disabledbackground="#F5F5F5", disabledforeground="#333")

                self.task_indicators[station_num]["Mapped with COM Port"].config(
                    text="✓", fg="#4CAF50")
                self.station_test_results[serial_number] = {}
                self.station_test_results[serial_number]["COM_PORT_MAPPING"] = {"status": "PASS", "value": ""}
            else:          
                self.task_indicators[station_num]["Mapped with COM Port"].config(
                    text="✕", fg="#F44336")
                self.failed_stations.add(station_num)

                self.station_test_results[serial_number]["COM_PORT_MAPPING"] = {"status": "FAIL", "value": ""}

        logging.warning(f"Failed stations: {list(self.failed_stations)}")
        logging.info(f"Mapped COM Ports and Serial Numbers for optical tests: {self.active_ports_serials}")
        logging.info(f"Skipped failed stations: {list(self.failed_stations)}")
        self.status_label.config(text="COM port mapping complete")

    def _run_test_script_parallel(self, script_name, task_name, result_key, com_port = None, serial_number = None, station_num = None, value_key=None):
        """Enhanced test script runner with improved value parsing and station isolation"""
        args_var = [] 
        kwargs_var = {} 

        if "BOOT Mode Initialization" in task_name:
            my_test_function = staticDO.run_staticDO
            args_var.append("01")
            args_var.append(self.dec_port_id)
        elif "BOOT MODE ON" in task_name:
            my_test_function = staticDO.run_staticDO
            args_var.append("05")
            args_var.append(self.dec_port_id)
        elif "BOOT MODE OFF" in task_name:
            my_test_function = staticDO.run_staticDO
            args_var.append("00")
            args_var.append(self.dec_port_id)
        elif "SUPERCAP DISCHARGE" in task_name:
            my_test_function = staticDO.run_staticDO
            args_var.append("02")
            args_var.append(self.dec_port_id)
        elif "MODULE SUPPLY OFF" in task_name:
            my_test_function = staticDO.run_staticDO
            args_var.append("00")
            args_var.append(self.dec_port_id)
        elif "Boost Output" in task_name:
            my_test_function = InstantAI.run_instantAi
            args_var.append(self.dec_port_id)
        elif "DISCHARGE OUTPUT" in task_name:
            my_test_function = InstantAI.run_instantAi
            args_var.append(self.dec_port_id)


        start_time = datetime.now()
        logging.info(f"Station {station_num} ({serial_number}): Executing {task_name} command: {my_test_function}")
        
        test_status = "FAIL"
        test_value = "N/A"
        error_message = ""
        Boost_voltage = 0
        Dis_super_cap_voltage = 0
        super_cap_voltage = 0
        Discharge_voltage = 0
        data_dict = {}

        
        logging.info(f"[RUN] Station {station_num} | Task: {task_name} | Port: {com_port} | Serial: {serial_number}")

        try:
            logging.debug(f"[SPAWNED] Started {task_name} for Station {station_num} on {com_port}")
            # Timeout from config (TEST_TIMEOUT key in serial_config.enc)
            timeout_duration = self.test_timeout

            stdout, stderr, return_code, timed_out = self.process_manager.run_function_with_timeout(
                my_test_function,
                timeout_duration,
                station_num,
                task_name,
                *args_var,
                **kwargs_var
            )

            logging.debug(f"{task_name} raw output for Station {station_num}:\n{stdout}, Error: {stderr}")

            if timed_out:
                error_message = f"Test {task_name} timed out and was forcefully terminated after {timeout_duration} seconds"
                logging.error(f"⏰ Station {station_num}: {error_message}")
                test_status = "FAIL"
                test_value = "Timeout - Process Killed"
                
                # Mark this station as failed for timeout
                self.failed_stations.add(station_num)
                self.station_stop_flags[station_num] = True
                
                return serial_number, test_status, station_num, task_name
        

            # Enhanced parsing based on your log data
            if ("BOOT Mode Initialization" in task_name) or ("BOOT MODE" in task_name) or ("SUPERCAP DISCHARGE" in task_name) or ("MODULE SUPPLY ON" in task_name) or ("MODULE SUPPLY OFF" in task_name):
                if stdout == "DO output completed!":
                    test_status = "PASS"
                else:
                    test_status = "FAIL"
                        
            elif ("Boost Output" in task_name) or ("DISCHARGE OUTPUT" in task_name):  
                data_dict = stdout
                if len(data_dict.keys()) >= 8:
                    test_status = "PASS"
                else:
                    test_status = "FAIL"
            
            else:
                test_status = "PASS"
                
        except Exception as e:
            error_message = f"Test {task_name} failed with exception: {str(e)}"
            logging.error(f"Station {station_num}: {error_message}")
            test_status = "FAIL"
            test_value = "N/A"
            
            # Mark this station as failed for exceptions
            self.failed_stations.add(station_num)
            self.station_stop_flags[station_num] = True
            
            return serial_number, "FAIL", station_num, task_name
        
        end_time = datetime.now()

        with self.test_completion_lock:
            if serial_number is not None:
                if serial_number not in self.station_test_results:
                    self.station_test_results[serial_number] = {}
                if serial_number not in self.station_test_times:
                    self.station_test_times[serial_number] = {'start': start_time, 'end': end_time}
                else:
                    self.station_test_times[serial_number]['end'] = end_time
                self.station_test_results[serial_number][task_name] = {"status": test_status, "value": test_value}

            else:
                for com_port, serial_number, station_num in self.active_ports_serials:
                    if serial_number.strip():
                        if serial_number not in self.station_test_results:
                            self.station_test_results[serial_number] = {}
                        if serial_number not in self.station_test_times:
                            self.station_test_times[serial_number] = {'start': start_time, 'end': end_time}
                        else:
                            self.station_test_times[serial_number]['end'] = end_time
                        self.station_test_results[serial_number][task_name] = {"status": test_status, "value": test_value}

                        if task_name == "Boost Output":
                            super_cap_voltage = float(data_dict["Channel " + str((station_num - 1)*2 + 0 ) + " data"])
                            Boost_voltage = float(data_dict["Channel " + str((station_num - 1)*2 + 1 ) + " data"])
                            if (super_cap_voltage >= self.voltage["min_super_cap_voltage"]) and (super_cap_voltage <= self.voltage["max_super_cap_voltage"]):
                                self.station_test_results[serial_number]["Super Cap Voltage"] = {"status": "PASS", "value": data_dict["Channel " + str((station_num - 1)*2 + 0 ) + " data"]}
                                self.root.after(0, lambda s=station_num, t="Super Cap Voltage", stat="PASS": self._update_task_ui(s, "Super Cap Voltage", "PASS"))
                            else:
                                self.station_test_results[serial_number]["Super Cap Voltage"] = {"status": "FAIL", "value": data_dict["Channel " + str((station_num - 1)*2 + 0 ) + " data"]}
                                self.root.after(0, lambda s=station_num, t="Super Cap Voltage", stat="FAIL": self._update_task_ui(s, "Super Cap Voltage", "FAIL"))
                                # Connectivity alarm: super cap below minimum — same retry group as Boost Output
                                if super_cap_voltage < self.voltage["min_super_cap_voltage"]:
                                    self.connectivity_alarm_stations.add((station_num, serial_number, super_cap_voltage))
                                    logging.warning(
                                        f"Station {station_num} ({serial_number}): Connectivity issue — "
                                        f"Super Cap {super_cap_voltage:.3f} V < min {self.voltage['min_super_cap_voltage']} V"
                                    )

                            if (float(Boost_voltage) >= self.voltage["min_Boost_voltage"]) and (float(Boost_voltage) <= self.voltage["max_Boost_voltage"]):
                                self.station_test_results[serial_number]["Boost Output"] = {"status": "PASS", "value": data_dict["Channel " + str((station_num - 1)*2 + 1 )  + " data"]}
                                self.root.after(0, lambda s=station_num, t="Boost Output", stat="PASS": self._update_task_ui(s, "Boost Output", "PASS"))
                            else:
                                self.station_test_results[serial_number]["Boost Output"] = {"status": "FAIL", "value": data_dict["Channel " + str((station_num - 1)*2 + 1 )  + " data"]}
                                self.root.after(0, lambda s=station_num, t="Boost Output", stat="FAIL": self._update_task_ui(s, "Boost Output", "FAIL"))
                                # Connectivity alarm: record station for batch pause after all readings
                                if float(Boost_voltage) < self.voltage["min_Boost_voltage"]:
                                    self.connectivity_alarm_stations.add((station_num, serial_number, float(Boost_voltage)))
                                    logging.warning(
                                        f"Station {station_num} ({serial_number}): Connectivity issue — "
                                        f"Boost {float(Boost_voltage):.3f} V < min {self.voltage['min_Boost_voltage']} V"
                                    )
                        
                        elif task_name == "DISCHARGE OUTPUT":
                            Dis_super_cap_voltage = float(data_dict["Channel " + str((station_num - 1)*2 + 0 ) + " data"])
                            Discharge_voltage = float(data_dict["Channel " + str((station_num - 1)*2 + 1 ) + " data"])

                            if (Dis_super_cap_voltage >= self.voltage["min_Dis_super_cap_voltage"]) and (Dis_super_cap_voltage <= self.voltage["max_Dis_super_cap_voltage"]):
                                self.station_test_results[serial_number]["Discharge Super Cap Voltage"] = {"status": "PASS", "value": data_dict["Channel " + str((station_num - 1)*2 + 0 ) + " data"]}
                                self.root.after(0, lambda s=station_num, t="Discharge Super Cap Voltage", stat="PASS": self._update_task_ui(s, "Discharge Super Cap Voltage", "PASS"))
                            else:
                                self.station_test_results[serial_number]["Discharge Super Cap Voltage"] = {"status": "FAIL", "value": data_dict["Channel " + str((station_num - 1)*2 + 0 ) + " data"]}
                                self.root.after(0, lambda s=station_num, t="Discharge Super Cap Voltage", stat="FAIL": self._update_task_ui(s, "Discharge Super Cap Voltage", "FAIL"))
                                # Connectivity alarm: dis super cap above maximum — same retry group as Discharge Output
                                if Dis_super_cap_voltage > self.voltage["max_Dis_super_cap_voltage"]:
                                    self.discharge_alarm_stations.add((station_num, serial_number, Dis_super_cap_voltage))
                                    logging.warning(
                                        f"Station {station_num} ({serial_number}): Connectivity issue — "
                                        f"Dis Super Cap {Dis_super_cap_voltage:.3f} V > max {self.voltage['max_Dis_super_cap_voltage']} V"
                                    )

                            if (float(Discharge_voltage) >= self.voltage["min_Discharge_voltage"]) and (float(Discharge_voltage) <= self.voltage["max_Discharge_voltage"]):
                                self.station_test_results[serial_number]["DISCHARGE OUTPUT"] = {"status": "PASS", "value": data_dict["Channel " + str((station_num - 1)*2 + 1 ) + " data"]}
                                self.root.after(0, lambda s=station_num, t="DISCHARGE OUTPUT", stat="PASS": self._update_task_ui(s, "DISCHARGE OUTPUT", "PASS"))
                            else:
                                self.station_test_results[serial_number]["DISCHARGE OUTPUT"] = {"status": "FAIL", "value": data_dict["Channel " + str((station_num - 1)*2 + 1 ) + " data"]}
                                self.root.after(0, lambda s=station_num, t="DISCHARGE OUTPUT", stat="FAIL": self._update_task_ui(s, "DISCHARGE OUTPUT", "FAIL"))
                                # Connectivity alarm: discharge output above maximum — record for batch retry
                                if float(Discharge_voltage) > self.voltage["max_Discharge_voltage"]:
                                    self.discharge_alarm_stations.add((station_num, serial_number, float(Discharge_voltage)))
                                    logging.warning(
                                        f"Station {station_num} ({serial_number}): Connectivity issue — "
                                        f"Discharge {float(Discharge_voltage):.3f} V > max {self.voltage['max_Discharge_voltage']} V"
                                    )
                            
        return serial_number, test_status, station_num, task_name

    def _handle_boost_connectivity_alarm(self):
        """Block the test thread, show ONE combined alarm for all affected stations.
        Returns True if user wants to retry Boost Output, False to mark as FAIL and continue."""
        alarm_event = threading.Event()
        retry_holder = [False]

        station_lines = "\n".join(
            f"  Station {sn}  |  Serial: {sr}  |  Read: {bv:.3f} V"
            for sn, sr, bv in sorted(self.connectivity_alarm_stations)
        )

        def show_dialog():
            result = messagebox.askretrycancel(
                "⚠ Connectivity Issue — ALL Stations Paused",
                f"Boost voltage below minimum on the following station(s):\n\n"
                f"{station_lines}\n\n"
                f"Expected: {self.voltage['min_Boost_voltage']} – {self.voltage['max_Boost_voltage']} V\n\n"
                f"ALL stations are paused.\n"
                f"Please reseat the module(s), then click:\n"
                f"  • Retry  — re-run Boost Output for affected station(s)\n"
                f"  • Cancel — mark affected station(s) as FAIL and continue"
            )
            retry_holder[0] = result
            alarm_event.set()

        self.root.after(0, show_dialog)
        alarm_event.wait()  # Block test thread until user responds
        logging.warning(
            f"Boost connectivity alarm resolved — user chose {'RETRY' if retry_holder[0] else 'CANCEL'}. "
            f"Affected: {[(sn, sr) for sn, sr, _ in self.connectivity_alarm_stations]}"
        )
        return retry_holder[0]

    def _handle_discharge_connectivity_alarm(self):
        """Block the test thread, show ONE combined alarm for all discharge-affected stations.
        Returns True if user wants to retry Discharge Output, False to mark as FAIL and continue."""
        alarm_event = threading.Event()
        retry_holder = [False]

        station_lines = "\n".join(
            f"  Station {sn}  |  Serial: {sr}  |  Read: {bv:.3f} V"
            for sn, sr, bv in sorted(self.discharge_alarm_stations)
        )

        def show_dialog():
            result = messagebox.askretrycancel(
                "⚠ Discharge Connectivity Issue — ALL Stations Paused",
                f"Discharge voltage above maximum on the following station(s):\n\n"
                f"{station_lines}\n\n"
                f"Expected: {self.voltage['min_Discharge_voltage']} – {self.voltage['max_Discharge_voltage']} V\n\n"
                f"ALL stations are paused.\n"
                f"Please reseat the module(s), then click:\n"
                f"  • Retry  — re-run Discharge Output for affected station(s)\n"
                f"  • Cancel — mark affected station(s) as FAIL and continue"
            )
            retry_holder[0] = result
            alarm_event.set()

        self.root.after(0, show_dialog)
        alarm_event.wait()  # Block test thread until user responds
        logging.warning(
            f"Discharge connectivity alarm resolved — user chose {'RETRY' if retry_holder[0] else 'CANCEL'}. "
            f"Affected: {[(sn, sr) for sn, sr, _ in self.discharge_alarm_stations]}"
        )
        return retry_holder[0]

    def _execute_shared_test(self, test_name, script_name, result_key, value_key=None):
        """Run one test globally (no station context), apply result to all active stations."""
        self.status_label.config(text=f"Running {test_name} (shared test)...")

        start_time = datetime.now()

        # Collect active stations
        active_stations_for_test = []
        for _, _, station_num in self.active_ports_serials:
            if station_num not in self.failed_stations and not self.station_stop_flags.get(station_num, False):

                active_stations_for_test.append(station_num)
                # Mark as running
                self.task_indicators[station_num][test_name].config(text="⏳", fg="#2196F3")
                ModernUI.update_status_indicator(self.status_indicators[station_num], "running")
            
            else:
                # Skip failed stations
                self.task_indicators[station_num][test_name].config(text="⛔", fg="#9E9E9E")
                with self.test_completion_lock:
                    self.station_completed_tests.setdefault(test_name, {})[station_num] = True

        self.root.update()
        end_time = datetime.now()
        # If no active stations -> nothing to do
        if not active_stations_for_test:
            with self.test_completion_lock:
                self.completed_tests[test_name] = True
            self.root.after(0, lambda: self.status_label.config(text=f"No active stations for {test_name}"))

            with self.test_completion_lock:
                for com_port, serial_number, station_num in self.active_ports_serials:
                    if serial_number.strip():
                        if serial_number not in self.station_test_results:
                            self.station_test_results[serial_number] = {}
                        if serial_number not in self.station_test_times:
                            self.station_test_times[serial_number] = {'start': start_time, 'end': end_time}
                        else:
                            self.station_test_times[serial_number]['end'] = end_time
                        self.station_test_results[serial_number][test_name] = {"status": "FAIL", "value": "FAIL"}
            return

        try:
            # ✅ Run test ONCE, without station context
            result = self._run_test_script_parallel(
                script_name,
                task_name=test_name,
                result_key=result_key,
                value_key=value_key,
                com_port=None,
                serial_number=None,
                station_num=None
            )
            

            # Default status is FAIL unless explicitly PASS/OK
            status = "FAIL"
            if result and len(result) >= 2:
                _, status, _, _ = result  # Ignore station-specific parts

            # ✅ Apply the SAME result to all stations
            for station_num in active_stations_for_test:
                # self.root.after(0, lambda s=station_num, stat=status: self._update_task_ui(s, test_name, stat))

                if (test_name == "Boost Output") or (test_name == "DISCHARGE OUTPUT"):
                    pass
                else:
                    self.root.after(0, lambda s=station_num, stat=status: self._update_task_ui(s, test_name, stat))
                    
                if status in ["PASS", "OK", "SUCCESS"]:
                    ModernUI.update_status_indicator(self.status_indicators[station_num], "running")
                else:
                    # self.failed_stations.add(station_num)
                    self.station_stop_flags[station_num] = True
                    ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")
                with self.test_completion_lock:
                    self.station_completed_tests.setdefault(test_name, {})[station_num] = True

        except Exception as e:
            logging.error(f"Shared test {test_name} failed with exception: {e}")
            for station_num in active_stations_for_test:
                self.root.after(0, lambda s=station_num: self._update_task_ui(s, test_name, "FAIL"))
                ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")
                # self.failed_stations.add(station_num)
                self.station_stop_flags[station_num] = True
                with self.test_completion_lock:
                    self.station_completed_tests.setdefault(test_name, {})[station_num] = True

        # ✅ Mark global test as completed
        with self.test_completion_lock:
            if (test_name == "Boost Output"):
                self.completed_tests[test_name] = True
            elif test_name == "DISCHARGE OUTPUT":
                self.completed_tests[test_name] = True
            else:
                self.completed_tests[test_name] = True

        self.root.after(0, lambda: self.status_label.config(text=f"{test_name} completed (shared)"))

    def _execute_tests_in_parallel(self, test_name, script_name, result_key, value_key=None):
        """Enhanced parallel test execution with ProcessManager and complete station isolation"""

        self.status_label.config(text=f"Running {test_name} tests...")
        
        # Initialize per-station completion tracking for this test
        with self.test_completion_lock:
            if test_name not in self.station_completed_tests:
                self.station_completed_tests[test_name] = {}
            
            # Mark all active stations as not completed for this test
            for _, _, station_num in self.active_ports_serials:
                if station_num not in self.failed_stations:
                    self.station_completed_tests[test_name][station_num] = False


        # Update UI to show tests are running for active stations only
        active_stations_for_test = []
        for optical_com_port, serial_number, station_num in self.active_ports_serials:
            if station_num not in self.failed_stations and not self.station_stop_flags.get(station_num, False):
                active_stations_for_test.append((optical_com_port, serial_number, station_num))
                if test_name == "SIM1 Cellular Test":
                    self.task_indicators[station_num][test_name].config(text="⏳", fg="#2196F3")
                    self.task_indicators[station_num]["SIM2 Cellular Test"].config(text="⏳", fg="#2196F3")
                    self.task_indicators[station_num]["GPIO Test"].config(text="⏳", fg="#2196F3")
                    self.task_indicators[station_num]["External Flash Test"].config(text="⏳", fg="#2196F3")
                    self.task_indicators[station_num]["RF RSSI Test"].config(text="⏳", fg="#2196F3")
                else:    
                    self.task_indicators[station_num][test_name].config(text="⏳", fg="#2196F3")
                ModernUI.update_status_indicator(self.status_indicators[station_num], "running")
            else:
                # Mark failed stations' tests as skipped
                
                if test_name == "SIM1 Cellular Test":
                    self.task_indicators[station_num][test_name].config(text="⛔", fg="#9E9E9E")
                    self.task_indicators[station_num]["SIM2 Cellular Test"].config(text="⛔", fg="#9E9E9E")
                    self.task_indicators[station_num]["GPIO Test"].config(text="⛔", fg="#9E9E9E")
                    self.task_indicators[station_num]["External Flash Test"].config(text="⛔", fg="#9E9E9E")
                    self.task_indicators[station_num]["RF RSSI Test"].config(text="⛔", fg="#9E9E9E")
                else:    
                    self.task_indicators[station_num][test_name].config(text="⛔", fg="#9E9E9E")
                # Mark as completed for failed stations
                with self.test_completion_lock:
                    if test_name in self.station_completed_tests:
                        self.station_completed_tests[test_name][station_num] = True
    
        self.root.update()

        def run_and_update_with_retry(com_port, serial_number, station_num, test_name, max_retries=0):
            """Run test with retry logic and proper error handling - completely isolated per station"""

            
            for attempt in range(max_retries + 1):
                # Skip if station is marked as failed during retry attempts
                if station_num in self.failed_stations or self.station_stop_flags.get(station_num, False):
                    logging.info(f"Station {station_num} marked as failed during retry, skipping {test_name}")
                    # Mark this station's test as completed
                    with self.test_completion_lock:
                        if test_name in self.station_completed_tests:
                            self.station_completed_tests[test_name][station_num] = True
                    return serial_number, "FAIL", station_num, test_name
                
                is_retry = attempt > 0
                if is_retry:
                    logging.info(f"Station {station_num}: Retrying {test_name} (attempt {attempt + 1}/{max_retries + 1})")
                    # Update UI to show retry status
                    self.root.after(0, lambda s=station_num, tn=test_name: self.task_indicators[s][tn].config(text="🔄", fg="#FF9800"))
                    self.root.after(0, lambda s=station_num: ModernUI.update_status_indicator(self.status_indicators[s], "retrying"))
                    time.sleep(1)  # Longer delay before retry for stability
                
                try:
                    # Use the enhanced test script runner
                    # result = self._run_test_script_parallel(script_name, com_port, serial_number, station_num, test_name, result_key, value_key)
                    result = self._run_test_script_parallel(
                        script_name,
                        task_name=test_name,
                        result_key=result_key,
                        value_key=value_key,
                        com_port=com_port,
                        serial_number=serial_number,
                        station_num=station_num
                        )
                
                    if result and len(result) >= 2:
                        sn, status, st_num, task = result
                        
                        if status in ["PASS", "OK"]:
                            # Test passed, update UI and return
                            if test_name == "SIM1 Cellular Test":
                                pass
                            else:
                                self.root.after(0, lambda s=st_num, t=task, stat=status: self._update_task_ui(s, t, stat))
                            if is_retry:
                                logging.info(f"Station {station_num}: {test_name} succeeded on retry attempt {attempt + 1}")
                            
                            # Mark this station's test as completed
                            with self.test_completion_lock:
                                if test_name in self.station_completed_tests:
                                    self.station_completed_tests[test_name][station_num] = True
                            return result
                        elif status == "FAIL":
                            if attempt < max_retries and test_name != "Memory Test":  # Don't retry Memory Test due to timeout sensitivity
                                # Test failed but we have retries left
                                logging.warning(f"Station {station_num}: {test_name} failed on attempt {attempt + 1}, will retry")
                                continue
                            else:
                                # All retries exhausted or Memory Test failed
                                logging.error(f"Station {station_num}: {test_name} failed after all retry attempts")
                                if test_name == "SIM1 Cellular Test":
                                    pass
                                else:
                                    self.root.after(0, lambda s=st_num, t=task, stat=status: self._update_task_ui(s, t, stat))
                                
                                # For critical tests, mark station as failed
                                if test_name in ["Test Firmware Download", "NIC Status Test", "Memory Test", "Live Version Test"]:
                                    self.failed_stations.add(station_num)
                                    self.station_stop_flags[station_num] = True
                                
                                # Mark this station's test as completed
                                with self.test_completion_lock:
                                    if test_name in self.station_completed_tests:
                                        self.station_completed_tests[test_name][station_num] = True
                                return result
                            
                except Exception as e:
                    error_msg = f"Exception in {test_name} attempt {attempt + 1}: {str(e)}"
                    logging.error(f"Station {station_num}: {error_msg}")
                    
                    # Kill any hanging processes for this station
                    self.process_manager.kill_station_processes(station_num)
                    
                    if attempt < max_retries and test_name != "Memory Test":
                        continue
                    else:
                        # All retries exhausted due to exceptions
                        self.failed_stations.add(station_num)
                        self.station_stop_flags[station_num] = True
                        
                        # Mark this station's test as completed
                        with self.test_completion_lock:
                            if test_name in self.station_completed_tests:
                                self.station_completed_tests[test_name][station_num] = True
                        return serial_number, "FAIL", station_num, test_name
        
            # Should not reach here, but just in case
            with self.test_completion_lock:
                if test_name in self.station_completed_tests:
                    self.station_completed_tests[test_name][station_num] = True
            return serial_number, "FAIL", station_num, test_name

        # If no active stations, mark test as completed and return
        if not active_stations_for_test:
            with self.test_completion_lock:
                self.completed_tests[test_name] = True
            self.root.after(0, lambda: self.status_label.config(text=f"No active stations for {test_name}"))
            return

        # Execute tests in parallel for active stations only - each station completely independent
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(active_stations_for_test)) as executor:
            future_to_test = {
                executor.submit(run_and_update_with_retry, com_port, serial_number, station_num, test_name): (serial_number, station_num)
                for com_port, serial_number, station_num in active_stations_for_test
                if serial_number.strip()
            }
            
            for future in concurrent.futures.as_completed(future_to_test):
                try:
                    result = future.result()
                    if result:
                        _, status, station_num, _ = result
                        # Update station status indicator based on result
                        if status in ["PASS", "OK"]:
                            self.root.after(0, lambda s=station_num: ModernUI.update_status_indicator(self.status_indicators[s], "running"))
                        elif status == "FAIL":
                            # Only update to failure if this station isn't continuing with other tests
                            if station_num in self.failed_stations:
                                self.root.after(0, lambda s=station_num: ModernUI.update_status_indicator(self.status_indicators[s], "failure"))
                        
                except Exception as e:
                    serial_number, station_num = future_to_test[future]
                    logging.error(f"Exception in {test_name} execution for Station {station_num}: {e}")
                    self.failed_stations.add(station_num)
                    self.station_stop_flags[station_num] = True
                    
                    # Kill any hanging processes for this station
                    self.process_manager.kill_station_processes(station_num)
                    
                    # Mark this station's test as completed
                    with self.test_completion_lock:
                        if test_name in self.station_completed_tests:
                            self.station_completed_tests[test_name][station_num] = True
    
        # Mark the overall test as completed
        with self.test_completion_lock: 
            self.completed_tests[test_name] = True
        self.root.after(0, lambda: self.status_label.config(text=f"{test_name} tests completed"))

    def _update_task_ui(self, station_num, task_name, status):
        """Enhanced UI update with real-time feedback"""
        if station_num in self.failed_stations:
            return
            
        # Update task indicator with animation effect
        icon = self.task_indicators[station_num][task_name]
        
        if status == "PASS" or status == "OK":
            icon.config(text="✓", fg="#4CAF50")
            # Brief highlight effect
            self.root.after(100, lambda: icon.config(bg="#E8F5E8"))
            self.root.after(500, lambda: icon.config(bg=icon.master["bg"]))
        else:
            icon.config(text="✕", fg="#F44336")
            # Brief highlight effect for failures
            self.root.after(100, lambda: icon.config(bg="#FFEBEE"))
            self.root.after(500, lambda: icon.config(bg=icon.master["bg"]))
        
        # Update status label with current progress
        self.status_label.config(text=f"Station {station_num}: {task_name} - {status}")
        self.root.update()

    def show_start_batch_dialog(self):
        # Dialog to confirm starting a new batch
        dialog = tk.Toplevel(self.root)
        dialog.title("Start New Batch")
        dialog.geometry("400x220")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="white")
        
        # Center the dialog
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (self.root.winfo_width() // 2) - (width // 2) + self.root.winfo_x()
        y = (self.root.winfo_height() // 2) - (height // 2) + self.root.winfo_y()
        dialog.geometry(f"+{x}+{y}")
        
        # Add a header
        header_frame = tk.Frame(dialog, bg="#2196F3", height=50)
        header_frame.pack(fill=tk.X)
        
        header_label = tk.Label(header_frame, text="Start New Batch", 
                               font=("Arial", 14, "bold"), bg="#2196F3", fg="white")
        header_label.pack(pady=10)
        
        # Dialog content
        content_frame = tk.Frame(dialog, bg="white")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Create info icon
        icon_canvas = tk.Canvas(content_frame, width=40, height=40, bg="white", highlightthickness=0)
        icon_canvas.pack(pady=5)
        
        # Draw info icon
        icon_canvas.create_oval(5, 5, 35, 35, fill="#E3F2FD", outline="#2196F3", width=2)
        icon_canvas.create_text(20, 20, text="i", font=("Arial", 18, "bold"), fill="#2196F3")
        
        message = tk.Label(content_frame, text="Are you sure you want to start a new batch?", 
                          bg="white", font=("Arial", 11))
        message.pack(pady=10)
        
        # Button frame
        button_frame = tk.Frame(content_frame, bg="white")
        button_frame.pack(pady=10)
        
        # Create buttons
        yes_btn_frame = ModernUI.create_modern_button(button_frame, "Yes", 
                                                    lambda: self.start_new_batch(dialog), 
                                                    width=100, height=30, bg="#4CAF50", hover_bg="#388E3C")
        yes_btn_frame.pack(side=tk.LEFT, padx=10)
        
        no_btn_frame = ModernUI.create_modern_button(button_frame, "No", 
                                                   dialog.destroy, 
                                                   width=100, height=30, bg="#F44336", hover_bg="#D32F2F")
        no_btn_frame.pack(side=tk.LEFT, padx=10)

    def start_new_batch(self, dialog):
        if self.test_thread and self.test_thread.is_alive():
            logging.info("Waiting for test thread to finish before starting new batch...")
            self.test_thread.join(timeout=5)
        # Close dialog and start a new batch
        dialog.destroy()
        
        # Clean up all processes before restarting
        self.process_manager.cleanup_all_processes()
        
        # Destroy the current root window
        self.monitor_running = False
        # self.root.destroy()
        
        # Create a new root window and initialize the GUI again
        new_root = tk.Tk()
        app = ManufacturingSuite(new_root)
        new_root.mainloop()
    
    def stop_test(self):
        """Enhanced stop test with proper cleanup and logging"""
        self.monitor_running = False

        if hasattr(self, "monitor_thread") and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=3)
        if self.test_thread and self.test_thread.is_alive():
            logging.info("Waiting for test thread to finish...")
            self.test_thread.join(timeout=5)
        
        self.process_manager.cleanup_all_processes()

        if self.timer_running:
            if self.timer_id:
                self.root.after_cancel(self.timer_id)
            self.timer_running = False
        
        # Kill all active processes
        
        # Set all station stop flags
        for station_num in range(1, 5):
            self.station_stop_flags[station_num] = True
        
        self.status_label.config(text="Test stopped by user.")
        self.status.config(text="OFFLINE")
        self.batch_time.config(text="BATCH TIME: 00:00")

        for station_num in range(1, 5):
            self.station_numbers[station_num].set("")
        
        # Reset status indicators
        for station_num in self.status_indicators:
            ModernUI.update_status_indicator(self.status_indicators[station_num], "pending")

        # Reset task indicators to default state
        for station_num, task_dict in self.task_indicators.items():
            for task, label in task_dict.items():
                label.config(text="⏱", fg="#757575")

        # Clear serial mappings and failed stations
        self.active_ports_serials.clear()
        self.failed_stations.clear()
        
        # Clear test completion tracking
        with self.test_completion_lock:
            for key in self.completed_tests:
                self.completed_tests[key] = False
            self.station_test_results.clear()
            self.station_test_times.clear()
            self.station_completed_tests.clear()

        # Unlock serial entries for re-entry
        for entry in self.entries.values():
            entry.config(state="normal")
            
        # Reset programming phase failed flag
        self.programming_phase_failed = False
        
        # Reset station stop flags
        self.station_stop_flags.clear()
        # self.root.destroy()

    def _run_all_tests_sequence(self, active_ports_serials):
        """Enhanced test sequence with complete station isolation"""

        logging.info("===== Starting full test sequence =====")
        pythoncom.CoInitialize()
        # self.launch_minimized()

        def safe_call(func, *args):
            """Wrapper to ensure one test failure doesn’t stop others"""
            try:
                func(*args)
            except Exception as e:
                logging.error(f"⚠️ Test failed: {args[0]} — {e}", exc_info=True)

        # 1. BOOT Mode Initialization Test
        safe_call(self._execute_shared_test,
                "BOOT Mode Initialization", "staticDO.py", "BOOT_MODE_INITIALIZATION_RESULT", "BOOT_MODE_INITIALIZATION_VALUE")

        # 2. BOOT Mode Test
        safe_call(self._execute_shared_test,
                "BOOT MODE ON", "staticDO.py", "BOOT_Mode_ON_RESULT", "BOOT_Mode_ON_VALUE")
        
        self.root.after(0, lambda: self.status_label.config(text="Waiting 110 seconds to charge module..."))


        time.sleep(110)  # Wait for 2 minutes to ensure BOOT mode is stable

        # 3. Instant AI Test — with connectivity retry loop
        # If any station reads boost voltage below minimum, ALL stations pause and
        # user is asked to reseat the module before re-running Boost Output.
        while True:
            self.connectivity_alarm_stations.clear()

            safe_call(self._execute_shared_test,
                    "Boost Output", "InstantAI.py", "INSTANT_AI_RESULT", "INSTANT_AI_VALUE")

            if not self.connectivity_alarm_stations:
                break  # All stations OK, proceed

            # At least one station has a connectivity issue — block and ask user
            retry = self._handle_boost_connectivity_alarm()

            if retry:
                logging.info("User chose RETRY — resetting affected stations and re-running Boost Output")
                for sn, sr, _ in self.connectivity_alarm_stations:
                    # Un-stop the station so _execute_shared_test includes it again
                    self.station_stop_flags.pop(sn, None)
                    self.failed_stations.discard(sn)
                    # Clear previous boost/super cap results so fresh values are written
                    if sr in self.station_test_results:
                        self.station_test_results[sr].pop("Boost Output", None)
                        self.station_test_results[sr].pop("Super Cap Voltage", None)
                    # Reset UI indicators for these tasks
                    self.root.after(0, lambda s=sn: self.task_indicators[s]["Boost Output"].config(text="⏱", fg="#757575"))
                    self.root.after(0, lambda s=sn: self.task_indicators[s]["Super Cap Voltage"].config(text="⏱", fg="#757575"))
                    self.root.after(0, lambda s=sn: ModernUI.update_status_indicator(self.status_indicators[s], "running"))
                # loop back and re-run Boost Output
            else:
                logging.info("User chose CANCEL — affected stations marked FAIL, continuing sequence")
                break  # Continue with remaining tests; affected stations stay FAIL

        safe_call(self._execute_shared_test,
                "BOOT MODE OFF", "staticDO.py", "BOOT_MODE_OFF_RESULT", "BOOT_MODE_OFF_VALUE")
        
        
        safe_call(self._execute_shared_test,
                "SUPERCAP DISCHARGE", "staticDO.py",
                "SUPERCAP_DISCHARGE_RESULT", "SUPERCAP_DISCHARGE_VALUE")
        
        self.root.after(0, lambda: self.status_label.config(text="Waiting 50 seconds to discharge module..."))

        time.sleep(50)  # Wait for 50 seconds to ensure discharge is complete

        # Discharge Output + Dis Super Cap — with connectivity retry loop
        # If any station reads discharge/dis-super-cap below minimum, ALL stations pause and
        # user is asked to reseat the module before re-running Discharge Output.
        while True:
            self.discharge_alarm_stations.clear()

            safe_call(self._execute_shared_test,
                    "DISCHARGE OUTPUT", "InstantAI.py", "DIS_OUTPUT_RESULT", "DIS_OUTPUT_VALUE")

            if not self.discharge_alarm_stations:
                break  # All stations OK, proceed

            # At least one station has a connectivity issue — block and ask user
            retry = self._handle_discharge_connectivity_alarm()

            if retry:
                logging.info("User chose RETRY — resetting affected stations and re-running Discharge Output")
                for sn, sr, _ in self.discharge_alarm_stations:
                    self.station_stop_flags.pop(sn, None)
                    self.failed_stations.discard(sn)
                    # Clear previous discharge results so fresh values are written
                    if sr in self.station_test_results:
                        self.station_test_results[sr].pop("DISCHARGE OUTPUT", None)
                        self.station_test_results[sr].pop("Discharge Super Cap Voltage", None)
                    # Reset UI indicators for these tasks
                    self.root.after(0, lambda s=sn: self.task_indicators[s]["DISCHARGE OUTPUT"].config(text="⏱", fg="#757575"))
                    self.root.after(0, lambda s=sn: self.task_indicators[s]["Discharge Super Cap Voltage"].config(text="⏱", fg="#757575"))
                    self.root.after(0, lambda s=sn: ModernUI.update_status_indicator(self.status_indicators[s], "running"))
                # loop back and re-run Discharge Output
            else:
                logging.info("User chose CANCEL — affected stations marked FAIL, continuing sequence")
                break  # Continue; affected stations stay FAIL

        # safe_call(self._execute_shared_test,
        #         "MODULE SUPPLY ON", "staticDO.py", "MODULE_SUPPLY_ON_RESULT", "MODULE_SUPPLY_ON_VALUE")
        # time.sleep(60)  # Wait for 1 minute to ensure module supply is stable

        # safe_call(self._execute_shared_test,
        # "Boost Output", "InstantAI.py", "INSTANT_AI_RESULT", "INSTANT_AI_VALUE")

        # safe_call(self._execute_tests_in_parallel,
        #         "SIM1 Cellular Test", "test_script.py", "TEST_SCRIPT_RESULT", "TEST_SCRIPT_VALUE")

        safe_call(self._execute_shared_test,
                "MODULE SUPPLY OFF", "staticDO.py", "MODULE_SUPPLY_OFF_RESULT", "MODULE_SUPPLY_OFF_VALUE")


        logging.info("===== Test sequence completed =====")
        self.root.after(0, self.update_status_after_tests)

    def update_timer(self):
        """Update the batch time display"""
        if self.start_time and self.timer_running:
            elapsed_time = time.time() - self.start_time
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            self.batch_time.config(text=f"BATCH TIME: {minutes:02d}:{seconds:02d}")
            self.timer_id = self.root.after(1000, self.update_timer)

    def make_default_dec_card_status(self):
        self.status_label.config(text=f"Running default DEC Card configuration...")
        self.root.update()
        try:
            args_var = ['00', self.dec_port_id]
            kwargs_var = {}
            stdout, stderr, return_code, timed_out = self.process_manager.run_function_with_timeout(
                staticDO.run_staticDO,
                60,  # timeout_duration in seconds
                1,
                "make DEC Card status",
                *args_var,
                **kwargs_var
                )
            if stdout == "DO output completed!":
                logging.info(f"DEC Card high DO: DO0, DO1, DO2")
            else:
                self.failed_stations.add(1)
                self.failed_stations.add(2)
                self.failed_stations.add(3)
                self.failed_stations.add(4)
            

        except Exception as e:
            logging.error(f"Failed to Configure DEC Card: {e}")
            messagebox.showerror("Error", f"Failed to Configure DEC Card: {e}")
            self.failed_stations.add(1)
            self.failed_stations.add(2)
            self.failed_stations.add(3)
            self.failed_stations.add(4)

    def run_test(self):
        """Enhanced run test with comprehensive logging, progress tracking, and complete station isolation"""
        if self.test_thread and self.test_thread.is_alive():
            logging.warning("Previous test still running. Waiting...")
            self.test_thread.join(timeout=5)

        # Reset UI and internal states
        for station_num in range(1, 5):
            self.station_numbers[station_num].set("")
        
        for station_num in self.status_indicators:
            ModernUI.update_status_indicator(self.status_indicators[station_num], "pending")

        for station_num, task_dict in self.task_indicators.items():
            for task, label in task_dict.items():
                label.config(text="⏱", fg="#757575")

        self.active_ports_serials.clear()
        self.failed_stations.clear()
        
        with self.test_completion_lock:
            for key in self.completed_tests:
                self.completed_tests[key] = False
            self.station_test_results.clear()
            self.station_test_times.clear()
            self.station_completed_tests.clear()

        for entry in self.entries.values():
            entry.config(state="normal")

        # Reset station stop flags and programming phase flag
        self.station_stop_flags.clear()
        self.programming_phase_failed = False

        self.status.config(text="ONLINE")

        # Start timer
        self.start_time = time.time()
        self.timer_running = True
        self.update_timer()
        
        self.status_label.config(text="Test is running...")

        # Step 0: Auto-scan serial numbers
        self.status_label.config(text="Starting auto-scan for serial numbers...")
        self.auto_scan_all_serials()
        self.root.update()
        time.sleep(1)

        # Count active stations and update status indicators
        valid_stations_to_test = []
        for station_num in range(1, 5):
            if station_num not in self.failed_stations:
                serial_number = self.station_numbers[station_num].get().strip()
                if serial_number:
                    valid_stations_to_test.append(station_num)
                    ModernUI.update_status_indicator(self.status_indicators[station_num], "running")
        
        if not valid_stations_to_test:
            self.status_label.config(text="No valid stations to test - all stations failed serial scan or config.")
            logging.warning("No valid stations to test - all stations failed serial scan or config.")
            self.stop_test()
            return
        
        self.root.update()

        # Step 1: Map Serial Number with COM Ports
        self.gather_com_ports_serial_numbers()
        self.root.update()
        time.sleep(0.5)

        self.make_default_dec_card_status()

        # Filter active_ports_serials to only include valid stations
        self.active_ports_serials = [
            (com, sn, st_num) for com, sn, st_num in self.active_ports_serials
            if st_num not in self.failed_stations
        ]
        
        if not self.active_ports_serials:
            self.status_label.config(text="No stations with valid COM port mapping to proceed with tests.")
            logging.warning("No stations with valid COM port mapping to proceed with tests.")
            self.stop_test()
            return
        
        # Now run the sequence of subsequent tests in a separate thread



        
        self.test_thread = threading.Thread(target=self._run_all_tests_sequence,args=(self.active_ports_serials,), daemon=True)
        self.test_thread.start()
        
        logging.info(f"Test sequence initiated for session {self.session_id}. Final status will update upon completion of all tests.")

    def check_all_pass(self, data):
        if not data:
            return False
        if all(test.get("status") == "PASS" for test in data.values()):
            return True
        else:
            return False

    def update_status_after_tests(self):
        """Enhanced status update with proper handling of failed stations and complete isolation"""
        logging.debug(f"Entering update_status_after_tests. Current completed_tests state: {self.completed_tests}")

        overall_result = []

        with self.test_completion_lock:
            # Check if all tests are completed
            
            self.completed_tests['Mapped with COM Port'] = True
            all_tests_completed = all(self.completed_tests.values())
            
            if not all_tests_completed:
                logging.debug("Not all tests completed yet. Rescheduling update_status_after_tests.")
                self.root.after(200, self.update_status_after_tests)
                return

        logging.info("All tests completed. Finalizing...")
        overall_pass_count = 0
        overall_fail_count = 0

        for station_num in range(1, 5):  # Assuming 4 stations
            serial_number = self.station_numbers[station_num].get().strip()
            if self.eng_var.get() and " - " in serial_number:
                serial_number = serial_number.split(" - ")[-1]

            if not serial_number or station_num in self.failed_stations:
                if station_num in self.failed_stations:
                    overall_fail_count += 1
                    ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")

            station_results = self.station_test_results.get(serial_number, {})
            critical_tests_passed = 0
            total_tests_run = 0
            all_tests_passed = True  # Flag to track if all tests passed

            # Check all test results for this station

            for test_name, test_result in station_results.items():
                if test_name == 'IMG SINK Programming':
                    continue
                total_tests_run += 1
                if test_result.get('status', 'FAIL') in ['PASS', 'OK']:
                    critical_tests_passed += 1
                else:
                    all_tests_passed = False  # If any test fails, mark as not all passed

            pass_percentage = (critical_tests_passed / total_tests_run) if total_tests_run > 0 else 0
            firmware_passed = station_results.get('IMG SINK Programming', {}).get('status', 'FAIL') in ['OK', 'PASS']

            # Determine overall station status
            if station_num in self.station_stop_flags:
                overall_station_status = "FAIL"
                ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")
                overall_fail_count += 1
            else:
                overall_station_status = self.check_all_pass(self.station_test_results.get(serial_number))
                if overall_station_status:
                    overall_station_status = "PASS"
                    ModernUI.update_status_indicator(self.status_indicators[station_num], "success")
                    overall_pass_count += 1
                
                else:
                    overall_station_status = "FAIL"
                    ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")
                    overall_fail_count += 1
            # elif firmware_passed and pass_percentage >= 0.7 and all_tests_passed:
            #     overall_station_status = "PASS"
            #     ModernUI.update_status_indicator(self.status_indicators[station_num], "success")  # Set to success
            #     overall_pass_count += 1
            # else:
            #     overall_station_status = "FAIL"
            #     ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")
            #     overall_fail_count += 1

            station_results['overall_result'] = {'status': overall_station_status}
            logging.info(f"Station {station_num} ({serial_number}) final result: {overall_station_status}")
            overall_result.append([self.session_id, station_num, serial_number, station_results,
                self.station_test_times.get(serial_number, {}).get('start', datetime.now()),
                self.station_test_times.get(serial_number, {}).get('end', datetime.now())])

       
        self.excel_logger.log_final_results(overall_result)
        self.total_cycles += 1
        self.total_passed_stations += overall_pass_count
        logging.debug(f"Updated total_cycles = {self.total_cycles}")
        logging.debug(f"Updated total_passed_stations = {self.total_passed_stations}")

        # Update cycle and pass labels
        try:
            # if self.cycle_count_label:
            #     self.cycle_count_label.config(text=f"Total Cycles: {self.total_cycles}")
            #     self.cycle_count_label.update_idletasks()
            # else:
            #     logging.warning("cycle_count_label is None")

            # if self.passed_stations_label:
            #     self.passed_stations_label.config(text=f"Passed PCBA: {self.total_passed_stations}")
            #     self.passed_stations_label.update_idletasks()
            # else:
            #     logging.warning("passed_stations_label is None")

            if self.status:
                self.status.config(text="OFFLINE")
                self.status.update_idletasks()

            summary_msg = f"Test completed: {overall_pass_count} PASS, {overall_fail_count} FAIL"
            skipped_count = len(self.station_numbers) - (overall_pass_count + overall_fail_count)
            if skipped_count > 0:
                summary_msg += f", {skipped_count} SKIPPED."

            if self.status_label:
                self.status_label.config(text=summary_msg)
                self.status_label.update_idletasks()
            else:
                logging.warning("status_label is None")
        except Exception as e:
            logging.error(f"Label update failed: {e}")

        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
            logging.info("Batch timer stopped after test completion.")

        with self.test_completion_lock:
            self.station_test_results.clear()
            self.station_test_times.clear()
            self.station_completed_tests.clear()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = ManufacturingSuite(root)
    root.mainloop()
