import logging
import time
import threading
import serial

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
            logging.debug(f"[Station {station_num}] Sent trigger command to {port}{retry_text}")
                            
            time.sleep(1)
            # scanned_data = ser.readline().decode('utf-8', errors='ignore').strip()
            # scanned_data = ser.read_all()

            # scanned_data = "ABC-123E2"

            # with self.scan_lock:
            #     if scanned_data:
            #         self.scan_results[station_num] = {
            #             'serial': scanned_data,
            #             'port': port,
            #             'status': 'success',
            #             'retry_attempt': is_retry
            #         }
            #         self.retry_stations.discard(station_num)
            #         logging.info(f"[Station {station_num}] Successfully scanned{retry_text}: {scanned_data}")
            #     else:
            #         self.scan_results[station_num] = {
            #             'serial': None,
            #             'port': port,
            #             'status': 'no_data',
            #             'retry_attempt': is_retry
            #         }
            #         if not is_retry:
            #             self.retry_stations.add(station_num)
            #         logging.warning(f"[Station {station_num}] No data received from {port}{retry_text}")
            
            with serial.Serial(port, self.baud_rate, timeout=self.timeout) as ser:
                # Discard whatever is already sitting in the input buffer
                # before triggering a new scan - without this, a leftover
                # unread line from an earlier scan (e.g. the previous batch's
                # barcode) gets returned by readline() below even when no new
                # barcode is presented this time, making a "no scan" look
                # like a stale successful one.
                ser.reset_input_buffer()
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
