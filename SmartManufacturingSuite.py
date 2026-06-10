import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import re
import subprocess
import time
import concurrent.futures
import threading
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

# Get current date for folder naming and filename
current_date = datetime.now().strftime("%Y-%m-%d")

# Setup directories

Test_Result = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Test Result Excel File")
Log_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Log files")

os.makedirs(Test_Result, exist_ok=True)
os.makedirs(Log_folder, exist_ok=True)

log_folder = os.path.join(Log_folder, f"Log_file_{current_date}")
excel_folder = os.path.join(Test_Result, f"Test_Result_{current_date}")

os.makedirs(log_folder, exist_ok=True)
os.makedirs(excel_folder, exist_ok=True)

# Enhanced file naming with timestamp
timestamp_suffix = datetime.now().strftime("%H%M%S")
file_name = os.path.join(excel_folder, f"{current_date}_3_Phase_TEST_RESULT.xlsx")
detailed_log_file = os.path.join(excel_folder, f"{current_date}_DETAILED_TEST_LOG.xlsx")

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
    format="%(asctime)s - %(levelname)s - %(message)s"
)

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

class ExcelLogger:
    """Enhanced Excel logging with detailed test data and formatting"""
    
    def __init__(self, main_file, detailed_file):
        self.main_file = main_file
        self.detailed_file = detailed_file
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
                    "FW Flash Result", "Live Version Result", "Live Version Value",
                    "NIC Status Result", "NIC Status Value", "Memory EEPROM Result", "Memory Flash Result",
                    "3P Current R (A)", "3P Current Y (A)", "3P Current B (A)", "3P Current N (A)",
                    "3P Voltage R (V)", "3P Voltage Y (V)", "3P Voltage B (V)",
                    "Digital Input Result", "Digital Input Value", "MD Reset Button Result", "MD Reset Button Value",
                    "Magnet Status Result", "Magnet Status Value", 
                    "Push Button 1 Result", "Push Button 1 Value", "Push Button 2 Result", "Push Button 2 Value",
                    "RX/TX Status Result", "RX/TX Status Value", "eFuse Mode Result", "eFuse Mode Value", "Cover Open Result", "Cover Open Value",
                    "Overall Status", "Total Test Time (s)", "Timestamp"
                ]
                
                ws.append(headers)
                self._format_header_row(ws, len(headers))
                wb.save(self.main_file)
            
            # Initialize detailed log file
            if not os.path.exists(self.detailed_file):
                wb = Workbook()
                ws = wb.active
                ws.title = "Detailed Test Logs"
                
                headers = [
                    "Test Session", "Station", "Serial Number", "Test Name", "Test Start Time",
                    "Test End Time", "Test Duration (s)", "Command Sent", "Raw Response", 
                    "Parsed Result", "Status", "Error Message", "Retry Count", "Timestamp"
                ]
                
                ws.append(headers)
                self._format_header_row(ws, len(headers))
                wb.save(self.detailed_file)
    
    def _format_header_row(self, worksheet, num_columns):
        """Format the header row with styling"""
        for col in range(1, num_columns + 1):
            cell = worksheet.cell(row=1, column=col)
            cell.fill = self.colors['header']
            cell.font = self.fonts['header']
            cell.alignment = Alignment(horizontal='center', vertical='center')
    
    def log_test_start(self, session_id, station, serial_number):
        """Log when a test session starts"""
        with self.lock:
            try:
                wb = load_workbook(self.detailed_file)
                ws = wb.active
                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ws.append([
                    session_id, station, serial_number, "TEST_SESSION_START", timestamp,
                    "", "", "", "", "", "STARTED", "", "", timestamp
                ])
                
                wb.save(self.detailed_file)
                logging.info(f"Logged test start for Station {station}, Serial: {serial_number}")
            except Exception as e:
                logging.error(f"Error logging test start: {e}")
    
    def log_individual_test(self, session_id, station, serial_number, test_name, 
                          start_time, end_time, command, response, result, status, error_msg="", retry_count=0):
        """Log individual test details"""
        with self.lock:
            try:
                wb = load_workbook(self.detailed_file)
                ws = wb.active
                
                duration = (end_time - start_time).total_seconds() if end_time and start_time else 0
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                row_data = [
                    session_id, station, serial_number, test_name,
                    start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else "",
                    end_time.strftime("%Y-%m-%d %H:%M:%S") if end_time else "",
                    f"{duration:.2f}", str(command)[:100], str(response)[:200],
                    str(result)[:100], status, error_msg, retry_count, timestamp
                ]
                
                ws.append(row_data)
                
                # Apply color formatting based on status
                row_num = ws.max_row
                status_cell = ws.cell(row=row_num, column=11)  # Status column
                if status == "PASS":
                    status_cell.fill = self.colors['pass']
                elif status == "FAIL":
                    status_cell.fill = self.colors['fail']
                elif status == "ERROR":
                    status_cell.fill = self.colors['warning']
                
                wb.save(self.detailed_file)
                logging.debug(f"Logged individual test: {test_name} for {serial_number}")
            except Exception as e:
                logging.error(f"Error logging individual test: {e}")
    
    def log_final_results(self, session_id, station, serial_number, test_results, 
                         start_time, end_time, overall_status):
        """Log final test results to main file with proper value extraction"""
        with self.lock:
            try:
                wb = load_workbook(self.main_file)
                ws = wb.active
                
                total_time = (end_time - start_time).total_seconds() if end_time and start_time else 0
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Extract individual test results with proper value handling
                fw_flash = test_results.get('Test Firmware Download', {})
                memory = test_results.get('Memory Test', {})
                live_version = test_results.get('Live Version Test', {})
                nic_status = test_results.get('NIC Status Test', {})
                current_3p = test_results.get('3P Current Test', {})
                voltage_3p = test_results.get('3P Voltage Test', {})
                digital_input = test_results.get('Digital Input Test', {})
                md_reset = test_results.get('MD Reset Button Test', {})
                magnet_status = test_results.get('Magnet Status Test', {})
                push_button1 = test_results.get('Push Button 1 Test', {})
                push_button2 = test_results.get('Push Button 2 Test', {})
                rxtx_status = test_results.get('RX/TX Status Test', {})
                efuse_mode = test_results.get('eFuse Mode Test', {})
                cover_open = test_results.get('Cover Open Test', {})
                
                # Prepare row data with proper value extraction
                row_data = [
                    session_id, station, serial_number,
                    start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else "",
                    end_time.strftime("%Y-%m-%d %H:%M:%S") if end_time else "",
                    fw_flash.get('status', 'FAIL'),
                    live_version.get('status', 'FAIL'),
                    str(live_version.get('value', 'N/A')),
                    nic_status.get('status', 'FAIL'),
                    str(nic_status.get('value', 'N/A')),
                    self._extract_memory_value(memory, 'EEPROM'),
                    self._extract_memory_value(memory, 'FLASH'),
                    self._extract_current_value(current_3p, 'R'),
                    self._extract_current_value(current_3p, 'Y'),
                    self._extract_current_value(current_3p, 'B'),
                    self._extract_current_value(current_3p, 'N'),
                    self._extract_voltage_value(voltage_3p, 'R'),
                    self._extract_voltage_value(voltage_3p, 'Y'),
                    self._extract_voltage_value(voltage_3p, 'B'),
                    digital_input.get('status', 'FAIL'),
                    str(digital_input.get('value', 'N/A')),
                    md_reset.get('status', 'FAIL'),
                    str(md_reset.get('value', 'N/A')),
                    magnet_status.get('status', 'FAIL'),
                    str(magnet_status.get('value', 'N/A')),
                    push_button1.get('status', 'FAIL'),
                    str(push_button1.get('value', 'N/A')),
                    push_button2.get('status', 'FAIL'),
                    str(push_button2.get('value', 'N/A')),
                    rxtx_status.get('status', 'FAIL'),
                    str(rxtx_status.get('value', 'N/A')),
                    efuse_mode.get('status', 'FAIL'),
                    str(efuse_mode.get('value', 'N/A')),
                    cover_open.get('status', 'FAIL'),
                    str(cover_open.get('value', 'N/A')),
                    overall_status,
                    f"{total_time:.2f}",
                    timestamp
                ]
                
                ws.append(row_data)
                
                # Apply formatting to the entire row based on overall status
                row_num = ws.max_row
                fill_color = self.colors['pass'] if overall_status == 'PASS' else self.colors['fail']
                
                for col in range(1, len(row_data) + 1):
                    cell = ws.cell(row=row_num, column=col)
                    if col == len(row_data) - 1:  # Overall status column
                        cell.fill = fill_color
                        cell.font = self.fonts['bold']
                
                wb.save(self.main_file)
                logging.info(f"Logged final results for Station {station}, Serial: {serial_number}, Status: {overall_status}")
            except Exception as e:
                logging.error(f"Error logging final results: {e}")
    
    def _extract_memory_value(self, memory_result, mem_type):
        """Extract memory test values (EEPROM/FLASH)"""
        if not memory_result:
            return "N/A"
        
        value = memory_result.get('value', {})
        if isinstance(value, dict):
            return value.get(mem_type, 'N/A')
        return "N/A"
    
    def _extract_current_value(self, current_result, phase):
        """Extract current values for specific phase"""
        if not current_result:
            return "N/A"
        
        value = current_result.get('value', {})
        if isinstance(value, dict) and phase in value:
            curr_val = value[phase]
            if isinstance(curr_val, (int, float)):
                return f"{curr_val:.3f}"
        return "N/A"
    
    def _extract_voltage_value(self, voltage_result, phase):
        """Extract voltage values for specific phase"""
        if not voltage_result:
            return "N/A"
        
        value = voltage_result.get('value', {})
        if isinstance(value, dict) and phase in value:
            volt_val = value[phase]
            if isinstance(volt_val, (int, float)):
                return f"{volt_val:.3f}"
        return "N/A"

class SerialScanner:
    """Enhanced serial scanning functionality with retry mechanism and station isolation"""
    
    def __init__(self, port_config, baud_rate=9600, trigger_command=b'*T', timeout=3, max_retries=1):
        self.port_config = port_config
        self.baud_rate = baud_rate
        self.trigger_command = trigger_command
        self.timeout = timeout
        self.max_retries = max_retries
        self.scan_results = {}
        self.scan_lock = threading.Lock()
        self.retry_stations = set()
    
    def scan_single_port(self, station_num, port, is_retry=False):
        """Scan a single COM port for serial number with improved error handling"""
        retry_text = " (RETRY)" if is_retry else ""
        try:
            logging.info(f"[Station {station_num}] Scanning port {port}{retry_text}")
            with serial.Serial(port, self.baud_rate, timeout=self.timeout) as ser:
                ser.write(self.trigger_command)
                logging.debug(f"[Station {station_num}] Sent trigger command to {port}{retry_text}")
                
                time.sleep(1)
                scanned_data = ser.readline().decode('utf-8', errors='ignore').strip()
                
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
            time.sleep(2)
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
            button["bg"] = hover_bg
            button["relief"] = "raised"
        
        def on_leave(e):
            button["bg"] = bg
            button["relief"] = "ridge"
        
        def on_press(e):
            button["relief"] = "sunken"
        
        def on_release(e):
            button["relief"] = "raised"

        button = tk.Label(parent, text=text, width=width, height=height,
                          bg=bg, fg="white", font=("Arial", 12, "bold"),
                          bd=3, relief="ridge", padx=5, pady=5, cursor="hand2")

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
        button.bind("<ButtonPress-1>", on_press)
        button.bind("<ButtonRelease-1>", lambda e: (on_release(e), command()))

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
        
        text_label = tk.Label(frame, text=text, anchor="w", bg=parent["bg"], font=("Arial", 11))
        text_label.pack(side=tk.LEFT, fill=tk.X)
        
        return frame, icon_label

class ManufacturingSuite:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Manufacturing Suite : 3P- [SMS] [Version 1.0.0.0, 18-JULY-25]")
        self.root.geometry("1350x700")
        self.root.configure(bg="#F5F5F5")
        
        # Initialize process manager
        self.process_manager = ProcessManager()
        
        self.root.attributes('-fullscreen', True)
        self.root.bind("<Escape>", self.exit_fullscreen)
        
        # Initialize Excel logger
        self.excel_logger = ExcelLogger(file_name, detailed_log_file)
        
        # Generate unique session ID for this test run
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Load configuration for COM ports mapping
        self.scanner_ports = {}
        self.optical_ports = {}
        self.load_com_port_config("config.txt")

        # Load firmware config
        self.code_file = ""
        self.station_1 = "#1"
        self.station_2 = "#2"
        self.load_firmwareflash_config("firmwareflash_config.json")
        
        # Initialize serial scanner with retry capability
        self.serial_scanner = SerialScanner(self.scanner_ports, max_retries=1)
        
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
        
        # Enhanced test tracking with timing - per station tracking
        self.test_completion_lock = threading.Lock()
        self.station_completed_tests = {}  # Track completion per station
        self.completed_tests = {
            "Test Firmware Download": False,
            "Memory Test": False,
            "Live Version Test": False,
            "NIC Status Test": False,
            "3P Current Test": False,
            "3P Voltage Test": False,
            "Digital Input Test": False,
            "MD Reset Button Test": False,
            "Magnet Status Test": False,
            "Push Button 1 Test": False,
            "Push Button 2 Test": False,
            "RX/TX Status Test": False,
            "eFuse Mode Test": False,
            "Cover Open Test": False,
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
        
        # Station-specific test threads and control flags
        self.station_threads = {}
        self.station_stop_flags = {}
        
        # Flag to track if any test has failed in the programming phase
        self.programming_phase_failed = False
        
        # Start process monitoring thread
        self.start_process_monitor()

    def load_firmwareflash_config(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.code_file = data.get('codefile', '')
        self.station_1 = data.get("station_1_gang_pro_map", "#1")
        self.station_2 = data.get("station_2_gang_pro_map", "#2")

    def start_process_monitor(self):
        """Start a background thread to monitor processes"""
        def monitor_processes():
            while True:
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
                    
                    time.sleep(5)  # Check every 5 seconds
                except Exception as e:
                    logging.error(f"Error in process monitor: {e}")
                    time.sleep(5)
        
        monitor_thread = threading.Thread(target=monitor_processes, daemon=True)
        monitor_thread.start()

    def load_com_port_config(self, path):
        """Load COM port configuration from config.txt"""
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            key, value = line.split("=", 1)
                            key = key.strip()
                            value = value.strip()
                            if key == "SCANNER_COM1":
                                self.scanner_ports[1] = value
                            elif key == "SCANNER_COM2":
                                self.scanner_ports[2] = value
                            elif key == "OPTICAL_COM1":
                                self.optical_ports[1] = value
                            elif key == "OPTICAL_COM2":
                                self.optical_ports[2] = value
                logging.info(f"Loaded scanner ports: {self.scanner_ports}")
                logging.info(f"Loaded optical ports: {self.optical_ports}")
            except Exception as e:
                logging.error(f"Error loading COM port configuration: {e}")
                messagebox.showerror("Config Error", f"Failed to load COM port configuration: {e}")
        else:
            logging.warning(f"COM port config file not found at: {path}")
            messagebox.showwarning("Config Missing", 
                                 f"Configuration file not found: {path}\n"
                                 "Please create config.txt with SCANNER_COMx and OPTICAL_COMx mappings")

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
                
                # Log to Excel
                self.excel_logger.log_individual_test(
                    self.session_id, station_num, result['serial'], "SERIAL_SCAN",
                    datetime.now(), datetime.now(), f"Scan {result['port']}", 
                    result['serial'], result['serial'], "PASS"
                )
                
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
                
                # Log failure to Excel
                self.excel_logger.log_individual_test(
                    self.session_id, station_num, "UNKNOWN", "SERIAL_SCAN",
                    datetime.now(), datetime.now(), f"Scan {result['port']}", 
                    "", "", "FAIL", error_msg
                )
                
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
        title_label = tk.Label(header_frame, text="Smart Manufacturing Suite [LTCT]", 
                              font=("Arial", 18, "bold"), bg="#1976D2", fg="white")
        title_label.pack(side=tk.LEFT, padx=5, pady=15)
        
        # Add version info
        version_label = tk.Label(header_frame, text="v1.0.0.2 | 04-DEC-25", 
                                font=("Arial", 10), bg="#1976D2", fg="#E1F5FE")
        version_label.pack(side=tk.LEFT, padx=5, pady=15)
        
        # Add engineering mode checkbox
        eng_frame = tk.Frame(header_frame, bg="#1976D2")
        eng_frame.pack(side=tk.RIGHT, padx=20)
        
        eng_check = tk.Checkbutton(eng_frame, text="Engineering Mode", variable=self.eng_var, 
                                  bg="#1976D2", fg="white", selectcolor="#0D47A1", 
                                  activebackground="#1976D2", activeforeground="white")
        eng_check.pack(pady=15)
        
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
        
    def export_excel_data(self):
        """Open the Excel files for viewing"""
        try:
            import subprocess
            import platform
            
            if platform.system() == 'Windows':
                subprocess.Popen(['start', 'excel', file_name], shell=True)
                subprocess.Popen(['start', 'excel', detailed_log_file], shell=True)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.Popen(['open', file_name])
                subprocess.Popen(['open', detailed_log_file])
            else:  # Linux
                subprocess.Popen(['xdg-open', file_name])
                subprocess.Popen(['xdg-open', detailed_log_file])
                
            messagebox.showinfo("Excel Export", f"Excel files opened:\n\n1. Main Results: {file_name}\n2. Detailed Logs: {detailed_log_file}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to open Excel files: {e}")

    def get_firmware_version_from_file(self):
        """Reads the current firmware version from the config file"""
        try:
            firmware_config = os.path.join("ConfigFiles", "firmware_config.txt")
            if os.path.exists(firmware_config):
                with open(firmware_config, 'r') as f:
                    version = f.read().strip()
                    return version
        except Exception as e:
            logging.error(f"Failed to read firmware version: {e}")
        return "Unknown"
        
    def create_main_content(self):
        # Create a frame for the main content with some padding
        main_frame = tk.Frame(self.root, bg="#F5F5F5")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        # Create a frame for the test stations
        content_frame = tk.Frame(main_frame, bg="#F5F5F5")
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Dictionary to store serial numbers for each test station
        self.station_numbers = {}
        self.task_indicators = {}

        # Create test station frames for 2 stations
        for i in range(2):
            station_num = i + 1
            
            # Create a frame for each test station
            station_frame = tk.Frame(content_frame, bg="white", bd=0)
            station_frame.grid(row=0, column=i, padx=10, pady=10, sticky="nsew")
            
            # Add a canvas for rounded corners and shadow effect
            station_canvas = tk.Canvas(station_frame, bg="white", highlightthickness=0)
            station_canvas.pack(fill="both", expand=True)
            
            # Draw rounded rectangle for the station
            ModernUI.create_rounded_rectangle(station_canvas, 2, 2, 650, 600, radius=10,
                                            fill="white", outline="#E0E0E0", width=2)
            
            # Create inner frame for content
            inner_frame = tk.Frame(station_canvas, bg="white")
            station_canvas.create_window(325, 300, window=inner_frame, width=620, height=580)
            
            # Station header
            header_frame = tk.Frame(inner_frame, bg="#2196F3", height=40)
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
            status_indicator = ModernUI.create_status_indicator(station_canvas, size=85, initial_state="pending")
            status_indicator.place(x=550, y=120)
            self.status_indicators[station_num] = status_indicator
            
            # Serial number frame
            serial_frame = tk.Frame(inner_frame, bg="white", height=50)
            serial_frame.pack(fill=tk.X, padx=10, pady=(15, 5))
            
            serial_label = tk.Label(serial_frame, text="Serial Number:", bg="white", font=("Arial", 11))
            serial_label.pack(side=tk.LEFT, padx=(5, 10))
            
            # Entry field for serial number
            self.station_numbers[station_num] = tk.StringVar()
            entry = tk.Entry(serial_frame, textvariable=self.station_numbers[station_num], 
                           width=30, font=("Arial", 11), bd=2, relief=tk.GROOVE)
            entry.pack(side=tk.LEFT, padx=5)
            entry.bind("<Return>", lambda event, s=station_num: self.handle_manual_entry(event, s))
            self.entries[station_num] = entry
            
            # Task status frame
            task_frame = tk.Frame(inner_frame, bg="white")
            task_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
            
            # List of tasks
            tasks = [
                "Mapped with COM Port",
                "Test Firmware Download",
                "Memory Test",
                "Live Version Test",
                "NIC Status Test",
                "3P Current Test",
                "3P Voltage Test",
                "Digital Input Test",
                "MD Reset Button Test",
                "Magnet Status Test",
                "Push Button 1 Test",
                "Push Button 2 Test",
                "RX/TX Status Test",
                "eFuse Mode Test",
                "Cover Open Test",
            ]
            
            # Store task indicators for this station
            self.task_indicators[station_num] = {}
            
            # Display tasks with status indicators
            for task in tasks:
                task_indicator, icon_label = ModernUI.create_task_indicator(task_frame, task, initial_state="pending")
                task_indicator.pack(fill=tk.X, pady=3)
                self.task_indicators[station_num][task] = icon_label
        
        # Configure grid weights
        content_frame.rowconfigure(0, weight=1)
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
    
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

        # Create labels to display counters in the UI
        self.cycle_count_label = tk.Label(status_frame, text="Total Cycles: 0", bg="#E0E0E0", 
                                        fg="#333", font=("Arial", 10, "bold"))
        self.cycle_count_label.pack(side=tk.RIGHT, padx=15)

        self.passed_stations_label = tk.Label(status_frame, text="Passed PCBA: 0", bg="#E0E0E0", 
                                            fg="#333", font=("Arial", 10, "bold"))
        self.passed_stations_label.pack(side=tk.RIGHT, padx=15)

        
        # Firmware version display
        firmware_version = self.get_firmware_version_from_file()
        self.firmware_version_label = tk.Label(status_frame, text=f"Current Firmware version: {firmware_version}", 
                                            bg="#E0E0E0", fg="#333", font=("Arial", 10 , "bold"))
        self.firmware_version_label.pack(side=tk.RIGHT, padx=10)

    def gather_com_ports_serial_numbers(self):
        """Map serial numbers to COM ports with enhanced logging"""
        self.status_label.config(text="Mapping COM ports to serial numbers...")
        self.root.update()

        self.active_ports_serials = []

        for station_num in range(1, 3):
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

                # Log COM port mapping to Excel
                self.excel_logger.log_individual_test(
                    self.session_id, station_num, serial_number, "COM_PORT_MAPPING",
                    datetime.now(), datetime.now(), f"Map to {optical_com_port}", 
                    optical_com_port, f"Station {station_num} -> {optical_com_port}", "PASS"
                )

                if self.eng_var.get():
                    self.station_numbers[station_num].set(f"{optical_com_port} - {serial_number}")
                    self.entries[station_num].config(
                        state="disabled", disabledbackground="#F5F5F5", disabledforeground="#333")

                self.task_indicators[station_num]["Mapped with COM Port"].config(
                    text="✓", fg="#4CAF50")
            else:
                # Log mapping failure
                self.excel_logger.log_individual_test(
                    self.session_id, station_num, serial_number, "COM_PORT_MAPPING",
                    datetime.now(), datetime.now(), "No optical port configured", 
                    "", "", "FAIL", f"No optical port configured for station {station_num}"
                )
                
                self.task_indicators[station_num]["Mapped with COM Port"].config(
                    text="✕", fg="#F44336")
                self.failed_stations.add(station_num)

        logging.warning(f"Failed stations: {list(self.failed_stations)}")
        logging.info(f"Mapped COM Ports and Serial Numbers for optical tests: {self.active_ports_serials}")
        logging.info(f"Skipped failed stations: {list(self.failed_stations)}")
        self.status_label.config(text="COM port mapping complete")

    def _run_efuse_mode_test(self, com_port, serial_number, station_num, task_name):
        """Enhanced eFuse Mode Test with set-and-verify functionality and station isolation"""
        # Check if this station has been marked as failed
        if station_num in self.failed_stations:
            logging.info(f"Station {station_num} already failed, skipping {task_name}")
            return serial_number, "FAIL", station_num, task_name
            
        # Check if we should stop testing for this station
        if self.station_stop_flags.get(station_num, False):
            logging.info(f"Stop flag set for Station {station_num}, skipping {task_name}")
            return serial_number, "FAIL", station_num, task_name
            
        start_time = datetime.now()
        logging.info(f"Station {station_num} ({serial_number}): Executing {task_name}")
        
        test_status = "FAIL"
        test_value = "N/A"
        error_message = ""
        combined_output = ""
        
        try:
            # Step 1: Generate random eFuse mode value (0 or 1)
            random_efuse_value = random.randint(0, 1)
            efuse_mode_text = "Enable" if random_efuse_value == 1 else "Disable"
            
            logging.info(f"Station {station_num}: Setting eFuse mode to {efuse_mode_text} (value={random_efuse_value})")
            
            # Step 2: Set eFuse mode
            set_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "tests", "set_efuse_mode.py")
            set_cmd = [sys.executable, set_script_path, "--serial_port", com_port, "--enable", str(random_efuse_value)]
            
            set_result = subprocess.run(
                set_cmd, capture_output=True, text=True, check=False,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            set_output = set_result.stdout + set_result.stderr

            logging.debug(f"[{task_name}] Return code: {set_result.returncode}")
            if set_result.stderr:
                logging.debug(f"[{task_name}] STDERR:\n{set_result.stderr}")

            combined_output += f"=== SET EFUSE MODE ===\n{set_output}\n"
            
            # Check if set operation was successful
            set_success = False
            if "Efuse mode enabled successfully" in set_output or "Efuse mode disabled successfully" in set_output:
                set_success = True
                logging.info(f"Station {station_num}: eFuse mode set operation successful")
            else:
                logging.error(f"Station {station_num}: eFuse mode set operation failed")
                error_message = "Set eFuse mode operation failed"
            
            if set_success:
                # Step 3: Wait a moment for the setting to take effect
                time.sleep(2)
                
                # Step 4: Get eFuse mode to verify
                get_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "tests", "get_efuse_mode.py")
                get_cmd = [sys.executable, get_script_path, "--serial_port", com_port]
                
                get_result = subprocess.run(
                    get_cmd, capture_output=True, text=True, check=False,
                    encoding='utf-8',
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                get_output = get_result.stdout + get_result.stderr
                combined_output += f"=== GET EFUSE MODE ===\n{get_output}\n"
                
                # Parse the get result
                # efuse_match = re.search(r"Efuse Mode\s*:\s*(\w+)\s*$$value=(\d+)$$", get_output)
                efuse_match = re.search(r"Efuse Mode\s*:\s*([\w\s]+)\s*\(value=(\d+)\)", get_output)

                if efuse_match:
                    get_efuse_state = efuse_match.group(1)
                    get_efuse_value = int(efuse_match.group(2))
                    
                    logging.info(f"Station {station_num}: Get eFuse mode result: {get_efuse_state} (value={get_efuse_value})")
                    
                    # Step 5: Compare set and get values
                    if get_efuse_value == random_efuse_value:
                        test_status = "PASS"
                        set_emoji = "✅" if random_efuse_value == 1 else "🚫"
                        get_emoji = "✅" if get_efuse_value == 1 else "🚫"
                        test_value = f"Set: {set_emoji} {efuse_mode_text} ({random_efuse_value}) | Get: {get_emoji} {get_efuse_state} ({get_efuse_value}) | Match: ✅"
                        logging.info(f"Station {station_num}: eFuse mode test PASSED - Set and Get values match")
                    else:
                        test_status = "FAIL"
                        set_emoji = "✅" if random_efuse_value == 1 else "🚫"
                        get_emoji = "✅" if get_efuse_value == 1 else "🚫"
                        test_value = f"Set: {set_emoji} {efuse_mode_text} ({random_efuse_value}) | Get: {get_emoji} {get_efuse_state} ({get_efuse_value}) | Match: ❌"
                        error_message = f"eFuse mode mismatch: Set={random_efuse_value}, Get={get_efuse_value}"
                        logging.error(f"Station {station_num}: eFuse mode test FAILED - {error_message}")
                        
                        # Mark this station as failed
                        self.failed_stations.add(station_num)
                        self.station_stop_flags[station_num] = True
                else:
                    test_status = "FAIL"
                    test_value = f"Set: {efuse_mode_text} ({random_efuse_value}) | Get: Parse Error"
                    error_message = "Failed to parse get eFuse mode result"
                    logging.error(f"Station {station_num}: Failed to parse get eFuse mode result")
                    
                    # Mark this station as failed
                    self.failed_stations.add(station_num)
                    self.station_stop_flags[station_num] = True
            else:
                test_status = "FAIL"
                test_value = f"Set: {efuse_mode_text} ({random_efuse_value}) | Get: Not Attempted"
                # error_message already set above
                
                # Mark this station as failed
                self.failed_stations.add(station_num)
                self.station_stop_flags[station_num] = True
                
        except Exception as e:
            error_message = str(e)
            logging.error(f"Error running {task_name} on {com_port} with serial {serial_number}: {e}")
            test_status = "FAIL"
            test_value = "N/A"
            
            # Mark this station as failed
            self.failed_stations.add(station_num)
            self.station_stop_flags[station_num] = True
        
        end_time = datetime.now()
        
        # Log detailed test information to Excel
        self.excel_logger.log_individual_test(
            self.session_id, station_num, serial_number, task_name,
            start_time, end_time, f"Set+Get eFuse Mode", combined_output[:200], 
            str(test_value)[:100], test_status, error_message
        )
        
        with self.test_completion_lock:
            if serial_number not in self.station_test_results:
                self.station_test_results[serial_number] = {}
            if serial_number not in self.station_test_times:
                self.station_test_times[serial_number] = {'start': start_time, 'end': end_time}
            else:
                self.station_test_times[serial_number]['end'] = end_time
                
            self.station_test_results[serial_number][task_name] = {"status": test_status, "value": test_value}
        
        return serial_number, test_status, station_num, task_name

    def _run_test_script(self, script_name, com_port, serial_number, station_num, task_name, result_key, value_key=None):
        """Enhanced test script runner with improved value parsing and station isolation"""
        # Check if this station has been marked as failed
        if station_num in self.failed_stations:
            logging.info(f"Station {station_num} already failed, skipping {task_name}")
            return serial_number, "FAIL", station_num, task_name
            
        # Check if we should stop testing for this station
        if self.station_stop_flags.get(station_num, False):
            logging.info(f"Stop flag set for Station {station_num}, skipping {task_name}")
            return serial_number, "FAIL", station_num, task_name
            
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "tests", script_name)
        cmd = [sys.executable, script_path, "--serial_port", com_port]
        
        start_time = datetime.now()
        logging.info(f"Station {station_num} ({serial_number}): Executing {task_name} command: {' '.join(cmd)}")
        
        test_status = "FAIL"
        test_value = "N/A"
        raw_output = ""
        error_message = ""
        
        logging.info(f"[RUN] Station {station_num} | Task: {task_name} | Port: {com_port} | Serial: {serial_number}")

        try:
            logging.debug(f"[SPAWNED] Started {task_name} for Station {station_num} on {com_port}")
            
            # Enhanced timeout handling - increased timeout for Memory Test
            timeout_duration = 25 if task_name == "Memory Test" else 20
            
            if task_name == "Digital Input Test":
                time.sleep(2)  # Allow time for process to finalize
            # Use ProcessManager for robust process handling
            stdout, stderr, return_code, timed_out = self.process_manager.run_process_with_timeout(
                cmd, timeout_duration, station_num, task_name
            )

            
            raw_output = stdout + stderr
            logging.debug(f"{task_name} raw output for Station {station_num}:\n{raw_output}")

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
            if task_name == "Memory Test":
                # Look for "EEPROM Test     : PASS" and "Flash Test      : PASS"
                eeprom_match = re.search(r"EEPROM Test\s*:\s*(PASS|FAIL)", raw_output)
                flash_match = re.search(r"Flash Test\s*:\s*(PASS|FAIL)", raw_output)
                
                if eeprom_match and flash_match:
                    eeprom_status = eeprom_match.group(1)
                    flash_status = flash_match.group(1)
                    test_value = {"EEPROM": eeprom_status, "FLASH": flash_status}
                    test_status = "PASS" if eeprom_status == "PASS" and flash_status == "PASS" else "FAIL"
                    
                    if test_status == "FAIL":
                        error_message = f"Memory test failed - EEPROM: {eeprom_status}, Flash: {flash_status}"
                        logging.error(f"Station {station_num}: {error_message}")
                        self.failed_stations.add(station_num)
                        self.station_stop_flags[station_num] = True
                else:
                    # Check for timeout or other failure indicators
                    if "timed out" in raw_output.lower() or "timeout" in raw_output.lower():
                        error_message = "Memory test timed out"
                        test_status = "FAIL"
                        test_value = "Timeout"
                    elif "failed" in raw_output.lower() or "error" in raw_output.lower():
                        error_message = "Memory test failed - no valid response"
                        test_status = "FAIL"
                        test_value = "Error"
                    else:
                        error_message = "Memory test - unable to parse results"
                        test_status = "FAIL"
                        test_value = "Parse Error"
                    
                    logging.error(f"Station {station_num}: {error_message}")
                    self.failed_stations.add(station_num)
                    self.station_stop_flags[station_num] = True
                
            elif task_name == "Live Version Test":
                # Look for "Live version retrieved: 1700" and "LIVE_VERSION_RESULT:PASS"
                version_match = re.search(r"Live version retrieved:\s*(\d+)", raw_output)
                status_match = re.search(r"LIVE_VERSION_RESULT:(PASS|FAIL)", raw_output)
                
                if version_match and status_match:
                    test_value = int(version_match.group(1))
                    test_status = status_match.group(1)
                else:
                    # Fallback to parsed version from logs
                    parsed_match = re.search(r"Parsed Live Version:\s*(\d+)", raw_output)
                    if parsed_match:
                        test_value = int(parsed_match.group(1))
                        test_status = "PASS"
                        
            elif task_name == "NIC Status Test":
                # Look for "NIC Status      : 1" or "NIC Status      : 0"
                status_match = re.search(r"NIC Status\s*:\s*(\d+)", raw_output)
                if status_match:
                    status_value = int(status_match.group(1))
                    test_value = status_value
                    # Both 0 and 1 are valid - PASS for both
                    test_status = "PASS"
                    
                    # Store descriptive text based on value
                    if status_value == 1:
                        test_value = "NIC is not present (value=1)"
                    else:
                        test_value = "NIC is present (value=0)"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"
            
            elif task_name == "3P Current Test":
                # Look for "✅ Final Current Values:" - if present, it's PASS
                if "✅ Final Current Values:" in raw_output or "Final Current Values:" in raw_output:
                    # Extract current values
                    r_match = re.search(r"R_Current\s*:\s*([\d.]+)\s*A", raw_output)
                    y_match = re.search(r"Y_Current\s*:\s*([\d.]+)\s*A", raw_output)
                    b_match = re.search(r"B_Current\s*:\s*([\d.]+)\s*A", raw_output)
                    n_match = re.search(r"Neutral Current:\s*([\d.]+)\s*A", raw_output)
                    
                    if r_match and y_match and b_match and n_match:
                        test_value = {
                            "R": float(r_match.group(1)),
                            "Y": float(y_match.group(1)),
                            "B": float(b_match.group(1)),
                            "N": float(n_match.group(1))
                        }
                        test_status = "PASS"  # If we get Final Current Values, it's PASS
                    else:
                        test_status = "FAIL"
                        test_value = "N/A"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"
                
            elif task_name == "3P Voltage Test":
                # Look for "✅ Final Voltage Values:" - if present, it's PASS
                if "✅ Final Voltage Values:" in raw_output or "Final Voltage Values:" in raw_output:
                    # Extract voltage values
                    r_match = re.search(r"R_Voltage\s*:\s*([\d.]+)\s*V", raw_output)
                    y_match = re.search(r"Y_Voltage\s*:\s*([\d.]+)\s*V", raw_output)
                    b_match = re.search(r"B_Voltage\s*:\s*([\d.]+)\s*V", raw_output)
                    
                    if r_match and y_match and b_match:
                        test_value = {
                            "R": float(r_match.group(1)),
                            "Y": float(y_match.group(1)),
                            "B": float(b_match.group(1))
                        }
                        test_status = "PASS"  # If we get Final Voltage Values, it's PASS
                    else:
                        test_status = "FAIL"
                        test_value = "N/A"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"
                
            elif task_name == "Digital Input Test":
                # Look for "🧾 Digital Input Status: 0 (Binary: 0b0)" - if present, it's PASS
                if "Digital Input Status:" in raw_output:
                    # Extract digital input value
                    input_match = re.search(r"Digital Input\s*:\s*(\d+)", raw_output)
                    if input_match:
                        input_value = int(input_match.group(1))
                        if input_value == 0:
                            test_value = f"Digital Input Status: {input_value} (Binary: 0b{input_value})"
                            test_status = "FAIL"  # Any digital input status reading is PASS
                        elif input_value == 15:
                            test_value = f"Digital Input Status: {input_value} (Binary: 0b{input_value})"
                            test_status = "PASS"
                        else:
                            test_value = f"Digital Input Status: {input_value} (Binary: 0b{input_value})"
                            test_status = "FAIL"  # Any digital input status reading is PASS
                    else:
                        test_status = "FAIL"
                        test_value = "N/A"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"
                
            elif task_name == "MD Reset Button Test":
                # Look for "🔘 Button Status   : Released (value=0)" or any button status
                if "Button Status" in raw_output:
                    # Extract button status
                    button_match = re.search(r"Button Status\s*:\s*(\w+)\s*$$value=(\d+)$$", raw_output)
                    if button_match:
                        button_state = button_match.group(1)
                        button_value = int(button_match.group(2))
                        test_value = f"MD Reset Button Status: {button_state} (value={button_value})"
                        test_status = "PASS"  # Any button status reading is PASS
                    else:
                        # Fallback - look for any button value
                        value_match = re.search(r"value=(\d+)", raw_output)
                        if value_match:
                            button_value = int(value_match.group(1))
                            button_state = "Pressed" if button_value == 0 else "Released"
                            test_value = f"MD Reset Button Status: {button_state} (value={button_value})"
                            test_status = "PASS"
                        else:
                            test_status = "FAIL"
                            test_value = "N/A"
                            error_message = "No button status received"
                elif "No response received within timeout" in raw_output:
                    test_value = "N/A"
                    test_status = "FAIL"
                    error_message = "Timeout - No response received"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"
                
            elif task_name == "Magnet Status Test":
                # Look for "✅ Magnet Status Received: 1" or "✅ Magnet Status Received: 0"
                status_match = re.search(r"Magnet Status Received:\s*(\d+)", raw_output)
                if status_match:
                    magnet_value = int(status_match.group(1))
                    test_value = magnet_value
                    test_status = "PASS"  # Both 0 and 1 are valid - PASS for both
                    
                    # Store descriptive text based on value
                    if magnet_value == 1:
                        test_value = "Magnet Status: Not Present (value=1)"
                    else:
                        test_value = "Magnet Status: Present (value=0)"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"

            elif task_name == "Push Button 1 Test":
                # Look for "Push Button 1   : Not Pressed (value=1)" or "Push Button 1   : Pressed (value=0)"
                if "Push Button 1" in raw_output:
                    # Extract button status - fix the regex pattern
                    # button_match = re.search(r"Push Button 1\s*:\s*(\w+\s*\w*)\s*$$value=(\d+)$$", raw_output)
                    button_match = re.search(r"Push Button 1\s*:\s*([\w\s]+)\s*\(value=(\d+)\)", raw_output)

                    if button_match:
                        button_state = button_match.group(1).strip()
                        button_value = int(button_match.group(2))
                        
                        # Look for the final status with emoji
                        if "Push Button 1: ✅ Pressed" in raw_output:
                            test_value = "Push Button 1: ✅ Pressed"
                        elif "Push Button 1: ✅ Not Pressed" in raw_output:
                            test_value = "Push Button 1: ✅ Not Pressed"
                        else:
                            test_value = f"Push Button 1: {button_state} (value={button_value})"
                        
                        test_status = "PASS"  # Both pressed and not pressed are valid states
                    else:
                        test_status = "FAIL"
                        test_value = "N/A"
                        error_message = "No button status received"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"
                    error_message = "No Push Button 1 data in response"

            elif task_name == "Push Button 2 Test":
                # Look for "Push Button 2   : Not Pressed (value=1)" or "Push Button 2   : Pressed (value=0)"
                if "Push Button 2" in raw_output:
                    # Extract button status - fix the regex pattern
                    button_match = re.search(r"Push Button 2\s*:\s*([\w\s]+)\s*\(value=(\d+)\)", raw_output)
                    if button_match:
                        button_state = button_match.group(1).strip()
                    
                        button_value = int(button_match.group(2))
                        
                        # Look for the final status with emoji
                        if "Push Button 2: ✅ Pressed" in raw_output:
                            test_value = "Push Button 2: ✅ Pressed"
                        elif "Push Button 2: ✅ Not Pressed" in raw_output:
                            test_value = "Push Button 2: ✅ Not Pressed"
                        else:
                            test_value = f"Push Button 2: {button_state} (value={button_value})"
                        
                        test_status = "PASS"  # Both pressed and not pressed are valid states
                    else:
                        test_status = "FAIL"
                        test_value = "N/A"
                        error_message = "No button status received"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"
                    error_message = "No Push Button 2 data in response"

            elif task_name == "Cover Open Test":
                # Check for known output keys
                if "COVER_STATUS_RESULT" in raw_output:
                    status_match = re.search(r"COVER_STATUS_RESULT:(PASS|FAIL)", raw_output)
                    value_match = re.search(r"COVER_STATUS_VALUE:(\d+|N/A)", raw_output)

                    if status_match:
                        test_status = status_match.group(1)
                        test_value = value_match.group(1) if value_match else "N/A"

                        # Final status formatting
                        if "✅ Final Cover Open Status: OPEN" in raw_output:
                            test_value = "✅ Final Cover Open Status: OPEN"
                        elif "✅ Final Cover Open Status: CLOSED" in raw_output:
                            test_value = "✅ Final Cover Open Status: CLOSED"
                        else:
                            test_value = f"Cover Status: {test_value}"
                    else:
                        test_status = "FAIL"
                        test_value = "N/A"
                        error_message = "COVER_STATUS_RESULT not found"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"
                    error_message = "No COVER_STATUS_RESULT line found in response"

            elif task_name == "RX/TX Status Test":
                # Look for "RX/TX Status    : 0 - Not Communicated" or "RX/TX Status    : 1 - Communicated"
                if "RX/TX Status" in raw_output:
                    # Extract RX/TX status - fix the regex pattern
                    status_match = re.search(r"RX/TX Status\s*:\s*(\d+)\s*-\s*([\w\s]+)", raw_output)
                    if status_match:
                        status_value = int(status_match.group(1))
                        status_text = status_match.group(2).strip()
                        
                        # Look for the final status with emoji
                        if "RX/TX Communication: ✅ Communicated" in raw_output:
                            test_value = "RX/TX Communication: ✅ Communicated"
                        elif "RX/TX Communication: ❌ Not Communicated" in raw_output:
                            test_value = "RX/TX Communication: ❌ Not Communicated"
                        else:
                            test_value = f"RX/TX Status: {status_value} - {status_text}"
                        
                        test_status = "PASS"  # Both communicated and not communicated are valid states
                    else:
                        test_status = "FAIL"
                        test_value = "N/A"
                        error_message = "No RX/TX status received"
                else:
                    test_status = "FAIL"
                    test_value = "N/A"
                    error_message = "No RX/TX Status data in response"


            # Check if this is a programming phase test and if it failed
            if test_status == "FAIL" and task_name in ["Test Firmware Download", "NIC Status Test", "Memory Test", "Live Version Test"]:
                # Mark the programming phase as failed
                self.programming_phase_failed = True
                # Mark this station as failed
                self.failed_stations.add(station_num)
                self.station_stop_flags[station_num] = True
                logging.error(f"Station {station_num}: Programming phase test {task_name} failed - stopping further tests for this station")
        
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
        
        # Log detailed test information to Excel
        self.excel_logger.log_individual_test(
            self.session_id, station_num, serial_number, task_name,
            start_time, end_time, ' '.join(cmd), raw_output[:200], 
            str(test_value)[:100], test_status, error_message
        )
        
        with self.test_completion_lock:
            if serial_number not in self.station_test_results:
                self.station_test_results[serial_number] = {}
            if serial_number not in self.station_test_times:
                self.station_test_times[serial_number] = {'start': start_time, 'end': end_time}
            else:
                self.station_test_times[serial_number]['end'] = end_time
                
            self.station_test_results[serial_number][task_name] = {"status": test_status, "value": test_value}
        
        return serial_number, test_status, station_num, task_name

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
                self.task_indicators[station_num][test_name].config(text="⏳", fg="#2196F3")
                ModernUI.update_status_indicator(self.status_indicators[station_num], "running")
            else:
                # Mark failed stations' tests as skipped
                self.task_indicators[station_num][test_name].config(text="⛔", fg="#9E9E9E")
                # Mark as completed for failed stations
                with self.test_completion_lock:
                    if test_name in self.station_completed_tests:
                        self.station_completed_tests[test_name][station_num] = True
    
        self.root.update()

        def run_and_update_with_retry(com_port, serial_number, station_num, test_name, max_retries=2):
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
                    time.sleep(3)  # Longer delay before retry for stability
                
                try:
                    # Use the enhanced test script runner
                    if test_name == "eFuse Mode Test":
                        result = self._run_efuse_mode_test(com_port, serial_number, station_num, test_name)
                    else:
                        result = self._run_test_script(script_name, com_port, serial_number, station_num, test_name, result_key, value_key)
                
                    if result and len(result) >= 2:
                        sn, status, st_num, task = result
                        
                        # if task == "Digital Input Test":
                        #     time.sleep(3)
                        if status in ["PASS", "OK"]:
                            # Test passed, update UI and return
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

    def check_firmware_log(self, output):
        """Extract verification results from firmware flash output"""
        pattern = r"#(\d+):\s+\.\.\s+(OK|failed)"
        matches = re.findall(pattern, output)
        ret_dict = {f"#{num}": status for num, status in matches}
        l = ['#1','#2','#3', '#4','#5', '#6', '#7', '#8']
        for num in l:
            if num not in ret_dict.keys():
                ret_dict[num] = 'failed'
        return ret_dict


    def FirmwareFlash(self, is_main_firmware=False):
        """Enhanced firmware flash with detailed logging and station isolation"""
        task_name = "Main Firmware Download" if is_main_firmware else "Test Firmware Download"
        Flashfile = "MainFirmwareFlash.py" if is_main_firmware else "FirmwareFlash.py"
        self.status_label.config(text=f"Running {task_name.lower()}...")

        with self.test_completion_lock:
            self.completed_tests["Test Firmware Download"] = False

        active_stations_for_flash = []
        for station_num in range(1, 3):
            if station_num in self.failed_stations:
                continue
            serial_number = self.station_numbers[station_num].get().strip()
            if serial_number:
                active_stations_for_flash.append((station_num, serial_number))
                self.task_indicators[station_num][task_name].config(text="⏳", fg="#2196F3")

        self.root.update()

        folder_path = r'ConfigFiles'
        # Config_file = '3Ph_GangConfig.cfg'
        Config_file = self.code_file
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), Flashfile)
        cmd = [sys.executable, script_path, os.path.join(folder_path, Config_file)]

        start_time = datetime.now()
        logging.info(f"Executing Firmware Flash command: {' '.join(cmd)}")

        flash_success = False
        raw_output = ""
        error_output = ""
        result_station_dict = {}

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                cwd=os.path.dirname(script_path)
            )

            raw_output, error_output = process.communicate()
            logging.debug(f"Firmware Flash raw output:\n{raw_output}")
            logging.debug(f"Firmware Flash error output:\n{error_output}")

            if process.returncode == 0 and not error_output:
                if "D O N E" in raw_output:
                    flash_success = True
                    result_station_dict = self.check_firmware_log(raw_output)
                    logging.info(result_station_dict)
                    logging.info("Firmware flash completed successfully.")
                else:
                    logging.error("Firmware flash exited with success code but 'D O N E' not found.")
            else:
                logging.error(f"Firmware flash failed with return code {process.returncode}: {error_output}")

        except Exception as e:
            error_output = str(e)
            logging.error(f"Failed to execute firmware flash: {e}")
        finally:
            end_time = datetime.now()

            for station_num, serial_number in active_stations_for_flash:
                self.excel_logger.log_individual_test(
                    self.session_id, station_num, serial_number, task_name,
                    start_time, end_time, ' '.join(cmd), raw_output[:200],
                    "Firmware flashed" if flash_success else "Flash failed",
                    "OK" if flash_success else "FAIL", error_output
                )

                with self.test_completion_lock:
                    if serial_number not in self.station_test_results:
                        self.station_test_results[serial_number] = {}
                    if serial_number not in self.station_test_times:
                        self.station_test_times[serial_number] = {'start': start_time, 'end': end_time}

                    if flash_success:
                        if (str(station_num) == "1") and (result_station_dict.get(self.station_1) == "OK"):
                            self.station_test_results[serial_number][task_name] = {"status": "OK", "value": "N/A"}
                            self.task_indicators[station_num][task_name].config(text="✓", fg="#4CAF50")
                            if station_num in self.failed_stations:
                                self.failed_stations.remove(station_num)
                                self.station_stop_flags[station_num] = False
                                self.is_break = False
                        elif (str(station_num) == "2") and (result_station_dict.get(self.station_2) == "OK"):
                            self.station_test_results[serial_number][task_name] = {"status": "OK", "value": "N/A"}
                            self.task_indicators[station_num][task_name].config(text="✓", fg="#4CAF50")
                            if station_num in self.failed_stations:
                                self.failed_stations.remove(station_num)
                                self.station_stop_flags[station_num] = False
                                self.is_break = False
                        else:
                            self.station_test_results[serial_number][task_name] = {"status": "FAIL", "value": "N/A"}
                            self.task_indicators[station_num][task_name].config(text="✕", fg="#F44336")
                            if station_num in self.failed_stations:
                                self.failed_stations.add(station_num)
                                self.station_stop_flags[station_num] = True
                                self.is_break = False
                    
                    else:
                        self.station_test_results[serial_number][task_name] = {"status": "FAIL", "value": "N/A"}
                        self.task_indicators[station_num][task_name].config(text="✕", fg="#F44336")
                        # Mark this station as failed in programming phase
                        self.programming_phase_failed = True
                        self.failed_stations.add(station_num)
                        self.station_stop_flags[station_num] = True

            with self.test_completion_lock:
                self.completed_tests["Test Firmware Download"] = True

            if flash_success:
                self.status_label.config(text="✅ Firmware Flash Successful. Proceeding with tests.")
                # REMOVED POWER RESET DIALOG - Replace with 14-second sleep
                self.status_label.config(text="Waiting 14 seconds for device reset...")
                self.root.update()
                time.sleep(14)  # 14-second sleep instead of power reset dialog

            # If firmware flash failed, force fail & stop testing for affected stations
            if not flash_success:
                logging.warning("Firmware flash failed — stopping all further tests for affected stations.")
                self.status_label.config(text="❌ Firmware Flash Failed. Affected stations will be skipped.")
                self.status_label.update_idletasks()

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
        # Close dialog and start a new batch
        dialog.destroy()
        
        # Clean up all processes before restarting
        self.process_manager.cleanup_all_processes()
        
        # Log the reset of counters
        logging.info(f"Resetting counters. Final values - Total cycles: {self.total_cycles}, Total passed PCBA: {self.total_passed_stations}")
        
        # Destroy the current root window
        self.root.destroy()
        
        # Create a new root window and initialize the GUI again
        new_root = tk.Tk()
        app = ManufacturingSuite(new_root)
        new_root.mainloop()
    
    def stop_test(self):
        """Enhanced stop test with proper cleanup and logging"""
        if self.timer_running:
            if self.timer_id:
                self.root.after_cancel(self.timer_id)
            self.timer_running = False
        
        # Kill all active processes
        self.process_manager.cleanup_all_processes()
        
        # Set all station stop flags
        for station_num in range(1, 3):
            self.station_stop_flags[station_num] = True
        
        # Log test stop event
        for station_num in range(1, 3):
            serial_number = self.station_numbers[station_num].get().strip()
            if serial_number:
                self.excel_logger.log_individual_test(
                    self.session_id, station_num, serial_number, "TEST_STOPPED",
                    datetime.now(), datetime.now(), "User stopped test", 
                    "", "", "STOPPED", "Test manually stopped by user"
                )
        
        self.status_label.config(text="Test stopped by user.")
        self.status.config(text="OFFLINE")
        self.batch_time.config(text="BATCH TIME: 00:00")

        for station_num in range(1, 3):
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

    def show_popup(self):
        
        popup = tk.Toplevel(self.root)
        popup.title("Action Required")

        window_width, window_height = 800, 200
        x = (popup.winfo_screenwidth() - window_width) // 2
        y = (popup.winfo_screenheight() - window_height) // 2
        popup.geometry(f"{window_width}x{window_height}+{x}+{y}")

        label = tk.Label(
            popup,
            text="Please press DI pulse button",
            font=("Courier New", 22, "bold"),
            fg="black"
        )
        label.pack(expand=True, pady=40)

        countdown_time = 6

        def update_text(time_left):
            if time_left == 6:
                label.config(text=f"Release DI pulse button")
                popup.after(1000, update_text, time_left - 1)
            if time_left >= 0:
                label.config(text=f"Please press DI pulse button for {time_left} seconds")
                popup.after(1000, update_text, time_left - 1)
            else:
                popup.destroy()
        update_text(countdown_time)


    def execute_dip_test(self):
        ttt2 = threading.Thread(target=self._execute_tests_in_parallel, args=("Digital Input Test", "digital_input_test.py", "DIGITAL_INPUT_RESULT", "DIGITAL_INPUT_VALUE"))
        ttt1 = threading.Thread(target=self.show_popup, args=())

        ttt1.start()
        ttt2.start()

        ttt1.join()
        ttt2.join()
    
    def _run_all_tests_sequence(self):
        """Enhanced test sequence with complete station isolation"""

        # Memory Test - Now with ProcessManager for robust timeout handling
        self._execute_tests_in_parallel("Memory Test", "memory_test.py", "EEPROM_RESULT")
        
        # Continue with other tests only for stations that haven't failed
        # Live Version Test
        self._execute_tests_in_parallel("Live Version Test", "live_version_test.py", "LIVE_VERSION_RESULT", "LIVE_VERSION_VALUE")
        
        # NIC Status Test
        self._execute_tests_in_parallel("NIC Status Test", "nic_status_test.py", "NIC_STATUS_RESULT", "NIC_STATUS_VALUE")
        
        
        # 3P Current Test
        self._execute_tests_in_parallel("3P Current Test", "current_test.py", "R_CURRENT_RESULT", "R_CURRENT")

        # 3P Voltage Test
        self._execute_tests_in_parallel("3P Voltage Test", "voltage_test.py", "R_VOLTAGE_RESULT", "R_VOLTAGE")

        while True:
            flag = 0
            if not self.completed_tests['Digital Input Test']:
                self.execute_dip_test()
                logging.info("Executing initial DIP test for all stations.")
            # elif (len(self.failed_stations) <= 1) and (self.completed_tests['Digital Input Test']):
                
            #     logging.info("Only one station failed Digital Input Test, retrying DIP test for that station.")
            else:
                self.execute_dip_test()
                # self.station_test_results[serial_number][task_name]
            for serial_num in list(self.station_test_results.keys()):
                if self.station_test_results[serial_num].get("Digital Input Test", {}).get("status") == "FAIL":
                    flag = 1
                    break
                else:
                    flag = 0
            if flag == 0:
                break


        # MD Reset Button Test
        self._execute_tests_in_parallel("MD Reset Button Test", "md_reset_button_test.py", "MD_RESET_BUTTON_RESULT", "MD_RESET_BUTTON_VALUE")
        
        # Magnet Status Test
        self._execute_tests_in_parallel("Magnet Status Test", "magnet_status_test.py", "MAGNET_STATUS_RESULT", "MAGNET_STATUS_VALUE")

        # Push Button 1 Test
        self._execute_tests_in_parallel("Push Button 1 Test", "push_button1_test.py", "PUSH_BUTTON1_RESULT", "PUSH_BUTTON1_VALUE")

        # Push Button 2 Test
        self._execute_tests_in_parallel("Push Button 2 Test", "push_button2_test.py", "PUSH_BUTTON2_RESULT", "PUSH_BUTTON2_VALUE")

        # RX/TX Status Test
        self._execute_tests_in_parallel("RX/TX Status Test", "rx_tx_status_test.py", "RXTX_STATUS_RESULT", "RXTX_STATUS_VALUE")

        # eFuse Mode Test - Now uses the enhanced set-and-verify test
        self._execute_tests_in_parallel("eFuse Mode Test", "get_efuse_mode.py", "EFUSE_MODE_RESULT", "EFUSE_MODE_VALUE")

        # Cover open Test
        self._execute_tests_in_parallel("Cover Open Test", "cover_open_test.py", "COVER_OPEN_RESULT", "COVER_OPEN_VALUE")
        
        # All tests are done, finalize status
        self.root.after(0, self.update_status_after_tests)

    def update_timer(self):
        """Update the batch time display"""
        if self.start_time and self.timer_running:
            elapsed_time = time.time() - self.start_time
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            self.batch_time.config(text=f"BATCH TIME: {minutes:02d}:{seconds:02d}")
            self.timer_id = self.root.after(1000, self.update_timer)

    def run_test(self):
        """Enhanced run test with comprehensive logging, progress tracking, and complete station isolation"""

        # Reset UI and internal states
        for station_num in range(1, 3):
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

        # Log test session start
        for station_num in range(1, 3):
            self.excel_logger.log_test_start(self.session_id, station_num, "PENDING_SCAN")

        # Step 0: Auto-scan serial numbers
        self.status_label.config(text="Starting auto-scan for serial numbers...")
        self.auto_scan_all_serials()
        self.root.update()
        time.sleep(2)

        # Count active stations and update status indicators
        valid_stations_to_test = []
        for station_num in range(1, 3):
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

        # Step 2: Test Firmware Download
        self.FirmwareFlash(is_main_firmware=False)
        self.root.update()
        # self.root.after(0, self.update_status_after_tests)
        # return
        
        # Now run the sequence of subsequent tests in a separate thread
        threading.Thread(target=self._run_all_tests_sequence, daemon=True).start()
        
        logging.info(f"Test sequence initiated for session {self.session_id}. Final status will update upon completion of all tests.")
    
    def check_all_pass(self, data):
        if not data:
            return False
        if all((test.get("status") == "PASS" )or (test.get("status") == "OK") for test in data.values()):
            return True
        else:
            return False

    def update_status_after_tests(self):
        """Enhanced status update with proper handling of failed stations and complete isolation"""
        logging.debug(f"Entering update_status_after_tests. Current completed_tests state: {self.completed_tests}")


        with self.test_completion_lock:
            # Check if all tests are completed - now we don't wait for failed stations
            all_tests_completed = all(self.completed_tests.values())
            
            if not all_tests_completed:
                logging.debug("Not all tests completed yet. Rescheduling update_status_after_tests.")
                self.root.after(200, self.update_status_after_tests)
                return

        logging.info("All tests completed. Finalizing...")

        overall_pass_count = 0
        overall_fail_count = 0

        for station_num in range(1, 3):
            serial_number = self.station_numbers[station_num].get().strip()
            if self.eng_var.get() and " - " in serial_number:
                serial_number = serial_number.split(" - ")[-1]

            if not serial_number or station_num in self.failed_stations:
                if station_num in self.failed_stations:
                    overall_fail_count += 1
                    ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")
                continue

            station_results = self.station_test_results.get(serial_number, {})
            
            critical_tests_passed = 0
            total_tests_run = 0

            for test_name, test_result in station_results.items():
                if test_name == 'Test Firmware Download':
                    continue
                total_tests_run += 1
                if test_result.get('status', 'FAIL') in ['PASS', 'OK']:
                    critical_tests_passed += 1

            pass_percentage = (critical_tests_passed / total_tests_run) if total_tests_run > 0 else 0
            firmware_passed = station_results.get('Test Firmware Download', {}).get('status', 'FAIL') in ['OK', 'PASS']

            # If station was stopped due to programming phase failure, mark it as failed
            if station_num in self.station_stop_flags:
                overall_station_status = "FAIL"
                # ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")
                overall_fail_count += 1
            elif firmware_passed and pass_percentage >= 0.7:
                overall_station_status = "PASS"
                
                overall_pass_count += 1
            else:
                overall_station_status = "FAIL"
                
                overall_fail_count += 1

            overall_station_status = "PASS" if self.check_all_pass(station_results) else "FAIL"

            if overall_station_status == "PASS":
                ModernUI.update_status_indicator(self.status_indicators[station_num], "success")
            else:
                ModernUI.update_status_indicator(self.status_indicators[station_num], "failure")

            logging.info(f"Station {station_num} ({serial_number}) final result: {overall_station_status}")
            self.excel_logger.log_final_results(
                self.session_id, station_num, serial_number, station_results,
                self.station_test_times.get(serial_number, {}).get('start', datetime.now()),
                self.station_test_times.get(serial_number, {}).get('end', datetime.now()),
                overall_station_status
            )

        self.total_cycles += 1
        self.total_passed_stations += overall_pass_count
        logging.debug(f"Updated total_cycles = {self.total_cycles}")
        logging.debug(f"Updated total_passed_stations = {self.total_passed_stations}")

        # Update cycle and pass labels
        try:
            if self.cycle_count_label:
                self.cycle_count_label.config(text=f"Total Cycles: {self.total_cycles}")
                self.cycle_count_label.update_idletasks()
            else:
                logging.warning("cycle_count_label is None")

            if self.passed_stations_label:
                self.passed_stations_label.config(text=f"Passed PCBA: {self.total_passed_stations}")
                self.passed_stations_label.update_idletasks()
            else:
                logging.warning("passed_stations_label is None")

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

        self.timer_running = False

if __name__ == "__main__":
    root = tk.Tk()
    app = ManufacturingSuite(root)
    root.mainloop()
