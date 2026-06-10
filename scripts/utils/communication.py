import serial
import threading
import queue
from datetime import datetime
import sys
import io
import time

# UTF-8 safe stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class Communication:
    SERIAL_BAUDRATE = 9600
    TIMEOUT = 10  # Increased from 7 to 10 seconds

    def __init__(self, serial_port):
        self.serial_port = serial_port
        self.ser = None
        self.response_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self.expected_payload_len = None
        self.fixed_packet_len = None
        self.lock = threading.Lock()  # Add thread safety

    def open(self, retries=3, delay=2):
        """Enhanced open method with better error handling and longer delays"""
        for i in range(retries):
            try:
                print(f"🔌 Trying to open {self.serial_port} (Attempt {i+1})...", flush=True)
                
                # Close any existing connection first
                if self.ser and self.ser.is_open:
                    try:
                        self.ser.close()
                        time.sleep(1)
                    except:
                        pass
                
                self.ser = serial.Serial(
                    self.serial_port,
                    self.SERIAL_BAUDRATE,
                    timeout=self.TIMEOUT,
                    write_timeout=self.TIMEOUT,  # Add write timeout
                    inter_byte_timeout=2  # Add inter-byte timeout
                )
                
                if self.ser.is_open:
                    print(f"✅ Port {self.serial_port} opened successfully.", flush=True)
                    # Clear any pending data
                    self.ser.reset_input_buffer()
                    self.ser.reset_output_buffer()
                    time.sleep(0.5)  # Brief stabilization delay
                    return True
                    
            except serial.SerialException as e:
                print(f"⚠️ SerialException on attempt {i+1}: {e}", flush=True)
                if i < retries - 1:  # Don't sleep on last attempt
                    time.sleep(delay)
            except Exception as e:
                print(f"⚠️ Unexpected exception on attempt {i+1}: {e}", flush=True)
                if i < retries - 1:
                    time.sleep(delay)
                    
        print(f"❌ Failed to open serial port {self.serial_port} after {retries} retries.", flush=True)
        return False

    def start_read_thread(self, expected_payload_len=None, fixed_packet_len=None):
        """Enhanced read thread management with better cleanup"""
        with self.lock:
            # Stop any existing thread
            self.stop_event.set()
            if self.thread and self.thread.is_alive():
                print("🧵 Stopping previous read thread...", flush=True)
                self.thread.join(timeout=3)  # Increased timeout
                if self.thread.is_alive():
                    print("⚠️ Previous thread did not stop gracefully", flush=True)

            # Clear and reset
            self.stop_event.clear()
            self.expected_payload_len = expected_payload_len
            self.fixed_packet_len = fixed_packet_len
            
            # Clear the queue
            while not self.response_queue.empty():
                try:
                    self.response_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Start new thread
            self.thread = threading.Thread(target=self._read_thread, daemon=True)
            self.thread.start()

    def _read_thread(self):
        """Enhanced read thread with better timeout and error handling"""
        packet = bytearray()
        expected_length = None
        last_byte_time = time.time()
        inter_byte_timeout = 3.0  # 3 seconds between bytes
        
        print(f"🧵 Read thread started for {self.serial_port}", flush=True)

        while not self.stop_event.is_set():
            try:
                if not self.ser or not self.ser.is_open:
                    print("❌ Serial port not open in read thread", flush=True)
                    break
                
                byte = self.ser.read(1)
                current_time = time.time()
                
                if byte:
                    packet.append(byte[0])
                    last_byte_time = current_time
                    print(f"🔍 Read byte: {byte.hex(' ')}", flush=True)

                    # Validate start byte
                    if len(packet) == 1 and packet[0] != 0xAA:
                        print(f"⚠️ Invalid start byte: {packet[0]:02x}, clearing packet", flush=True)
                        packet.clear()
                        continue

                    # Determine expected length
                    if self.fixed_packet_len:
                        expected_length = self.fixed_packet_len
                    elif len(packet) >= 12:  # We have enough bytes to read payload length
                        payload_len = packet[11]
                        expected_length = 12 + payload_len + 2
                        print(f"📏 Calculated expected length: {expected_length} (payload: {payload_len})", flush=True)

                    if not expected_length and self.expected_payload_len is not None:
                        expected_length = 12 + self.expected_payload_len + 2

                    # Check if packet is complete
                    if expected_length and len(packet) >= expected_length:
                        print(f"✅ Complete packet received: {packet.hex(' ')}", flush=True)
                        self.response_queue.put(bytes(packet))
                        break
                        
                else:
                    # No byte received, check for timeout
                    if current_time - last_byte_time > inter_byte_timeout:
                        if len(packet) > 0:
                            print(f"⏰ Inter-byte timeout after {inter_byte_timeout}s, partial packet: {packet.hex(' ')}", flush=True)
                        else:
                            print("⏰ No data received within timeout", flush=True)
                        break
                    
                    # Brief sleep to prevent busy waiting
                    time.sleep(0.01)

            except serial.SerialException as e:
                print(f"❌ Serial read error: {e}", flush=True)
                break
            except Exception as e:
                print(f"❌ Unexpected error in read thread: {e}", flush=True)
                break

        print(f"🧵 Read thread ending for {self.serial_port}", flush=True)

    def send_data(self, data, expected_payload_len=None, fixed_packet_len=None):
        """Enhanced send_data with better error handling"""
        if not self.ser or not self.ser.is_open:
            print("❌ Serial port not open for sending data", flush=True)
            if not self.open():
                return False

        try:
            # Clear buffers before sending
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            # Start read thread before sending
            self.start_read_thread(expected_payload_len, fixed_packet_len)
            
            # Brief delay to ensure read thread is ready
            time.sleep(0.1)
            
            # Send data
            bytes_written = self.ser.write(data)
            self.ser.flush()  # Ensure data is sent
            
            print(f"📤 Sent --> {data.hex(' ')} ({bytes_written} bytes)", flush=True)
            
            if bytes_written != len(data):
                print(f"⚠️ Warning: Expected to send {len(data)} bytes, actually sent {bytes_written}", flush=True)
            
            return True
            
        except serial.SerialException as e:
            print(f"❌ Failed to send data: {e}", flush=True)
            return False
        except Exception as e:
            print(f"❌ Unexpected error sending data: {e}", flush=True)
            return False

    def read_response(self, timeout=8):
        """Enhanced read_response with better timeout handling"""
        try:
            print(f"⏳ Waiting for response (timeout: {timeout}s)...", flush=True)
            response = self.response_queue.get(timeout=timeout)
            print(f"📥 Received --> {response.hex(' ')}", flush=True)
            return response
        except queue.Empty:
            print(f"❌ No response received within {timeout} seconds timeout.", flush=True)
            # Stop the read thread
            self.stop_event.set()
            return None
        except Exception as e:
            print(f"❌ Error reading response: {e}", flush=True)
            return None

    def close(self):
        """Enhanced close method with better cleanup"""
        print(f"🔌 Closing communication for {self.serial_port}...", flush=True)
        
        # Stop read thread
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            print("🧵 Waiting for read thread to stop...", flush=True)
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                print("⚠️ Read thread did not stop gracefully", flush=True)
        
        # Close serial port
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                print(f"🔌 COM port {self.serial_port} closed.", flush=True)
            except Exception as e:
                print(f"⚠️ Error closing port: {e}", flush=True)
        
        # Clean up
        self.ser = None
        self.thread = None
        
        # Clear queue
        while not self.response_queue.empty():
            try:
                self.response_queue.get_nowait()
            except queue.Empty:
                break
