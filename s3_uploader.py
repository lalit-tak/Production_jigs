"""
Uploads this tool's logs to S3 - same convention as the Better Meter jig's
s3_uploader.py and img_s3_upload.py (this bucket/credentials/key layout is
already used to upload other jigs' results here).

- upload_excel_log_async() is called after every batch - see
  SmartManufacturingSuite.py update_status_after_tests(). Every batch writes
  its own workbook "<YYYY-MM-DD_HHMMSS>_IMG_TEST_RESULT.xlsx"
  (ExcelLogger.log_final_results()), so each upload has its own S3 key and
  never overwrites an earlier batch. The local workbook is deleted after a
  successful upload and kept if the upload fails.

- upload_pending_logs_async() runs when the tool opens and after every
  batch. It uploads:
    * the text logs of every Log files/ day-folder except today's (and
      except the folder this run is still writing to - logging.basicConfig
      keeps its program log open, even past midnight). A folder is moved to
      Log files/Uploaded/ once all its files are up, so it is never sent
      twice; archived folders older than TEXT_LOG_KEEP_DAYS are removed.
    * any batch workbook still on disk because its upload failed earlier.
"""

import logging
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from openpyxl import load_workbook

# The app logs at DEBUG, which boto3/botocore inherit - ~40 lines per upload
# (including request headers) in the program log. Keep only their warnings.
for _name in ("boto3", "botocore", "s3transfer", "urllib3"):
    logging.getLogger(_name).setLevel(logging.WARNING)

# ---------------------------------------------------------------- AWS config ----------------------
AWS_ACCESS_KEY_ID = "PUT_YOUR_S3_ACCESS_KEY"
AWS_SECRET_ACCESS_KEY = "PUT_YOUR_S3_SECRET_KEY"
AWS_REGION = "PUT_YOUR_AWS_REGION"
S3_BUCKET_NAME = "PUT_YOUR_BUCKET_NAME"

# This jig's folder under the bucket.
S3_KEY_PREFIX = "PUT_YOUR_S3_KEY_PREFIX"

# Sub-folder each upload type lands in under S3_KEY_PREFIX, so the Excel
# workbooks and the text logs never mix in the same S3 folder.
EXCEL_LOG_S3_FOLDER = "Excel_log"
TEXT_LOG_S3_FOLDER = "text_log"

def _get_pc_name():
    """
    This PC's name (e.g. "PGLT0188"), read with PowerShell's $env:COMPUTERNAME
    - a plain user-level read, no admin rights needed. Put in every S3 key so
    Jig 1 and Jig 2 (same file names, e.g. action_log.txt) never overwrite
    each other's uploads. Falls back to the process environment if
    PowerShell cannot be run.
    """
    name = ""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "$env:COMPUTERNAME"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        name = result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        logging.warning(f"Could not read PC name with PowerShell: {exc}")
    if not name:
        name = os.environ.get("COMPUTERNAME", "")
    # Keep it safe as one S3 key folder.
    name = re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("_")
    return name or "UNKNOWN_PC"

# Read on the first upload, not at import: SmartManufacturingSuite imports
# this module before logging.basicConfig(), and logging here at import would
# stop the program log file from being set up.
_pc_name = None

def pc_name():
    global _pc_name
    if _pc_name is None:
        _pc_name = _get_pc_name()
        logging.info(f"S3 uploads of this PC go under {S3_KEY_PREFIX}/{_pc_name}/")
    return _pc_name


def _client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION or None,
        aws_access_key_id=AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
    )

def _s3_key(file_path, folder_name, date_str):
    """S3_KEY_PREFIX/Duas/Duas_01/{folder_name}/{year}/{month}/{date}/{pc name}_{file_name}."""
    year, month, _day = date_str.split("-")
    file_name = os.path.basename(file_path)
    prefix = f"{S3_KEY_PREFIX.rstrip('/')}/" if S3_KEY_PREFIX else ""
    return f"{prefix}Duas/Duas_01/{folder_name}/{year}/{month}/{date_str}/{pc_name()}_{file_name}"

def _upload(file_path, key):
    """
    Uploads file_path to S3_BUCKET_NAME/key. Never raises and never deletes
    anything - callers decide what to do with the local file. Returns
    True/False.
    """
    if not S3_BUCKET_NAME:
        logging.warning(f"S3 upload skipped for {file_path}: S3_BUCKET_NAME not configured (see s3_uploader.py)")
        return False

    try:
        _client().upload_file(file_path, S3_BUCKET_NAME, key)
    except (BotoCoreError, ClientError, OSError) as exc:
        logging.error(f"S3 upload failed for {file_path} -> s3://{S3_BUCKET_NAME}/{key}: {exc}")
        return False

    logging.info(f"Uploaded {file_path} to s3://{S3_BUCKET_NAME}/{key}")
    return True
    # return False

def _date_from_name(name):
    """'2026-10-09_101530_IMG_TEST_RESULT.xlsx' / 'Log_file_2026-10-09' -> '2026-10-09' (None if absent)."""
    match = re.search(r"\d{4}-\d{2}-\d{2}", name)
    return match.group(0) if match else None

# ---------------------------------------------------------------- Excel workbook (every batch) -----

# The per-batch upload and the sweep can reach the same workbook at the same
# time - this makes sure it is uploaded and deleted only once.
_excel_upload_lock = threading.Lock()

def upload_excel_log(file_path):
    """
    Uploads one batch workbook, synchronously, then deletes the local copy.
    A workbook that does not open is renamed to *.xlsx.corrupt (kept for
    investigation, never uploaded or retried). A headers-only workbook is
    the empty one ExcelLogger.reset_workbook() made for the next batch - it
    is left alone. Returns True/False.
    """
    with _excel_upload_lock:
        if not os.path.exists(file_path):
            return False    # already uploaded by the other thread

        try:
            wb = load_workbook(file_path, read_only=True)
            try:
                has_results = len(list(wb.active.iter_rows(max_row=2))) > 1
            finally:
                wb.close()
            if not has_results:
                return False
        except Exception as exc:
            logging.error(f"S3 upload skipped: {file_path} is corrupted ({exc}) - renamed to .corrupt")
            try:
                os.replace(file_path, file_path + ".corrupt")
            except OSError:
                pass
            return False

        date_str = _date_from_name(os.path.basename(file_path)) or datetime.now().strftime("%Y-%m-%d")
        if not _upload(file_path, _s3_key(file_path, EXCEL_LOG_S3_FOLDER, date_str)):
            return False    # kept locally, retried by the next sweep

        try:
            os.remove(file_path)
            logging.info(f"Deleted local {file_path} after successful S3 upload")
        except OSError as exc:
            logging.error(f"Uploaded {file_path} but could not delete the local copy: {exc}")
        return True

def upload_excel_log_async(file_path):
    """
    Fire-and-forget: runs upload_excel_log() on a background thread so the
    GUI thread never blocks on the network. Success/failure only reaches the
    program log (logging is thread-safe).
    """
    threading.Thread(target=upload_excel_log, args=(file_path,), daemon=True).start()

def _is_headers_only(file_path):
    try:
        wb = load_workbook(file_path, read_only=True)
        try:
            return len(list(wb.active.iter_rows(max_row=2))) == 1
        finally:
            wb.close()
    except Exception:
        return False

def upload_pending_excel_logs(test_result_root):
    """
    Uploads every batch workbook still under test_result_root's day-folders
    (left there by a failed upload). Safe to run at any time: a workbook only
    appears on disk once complete (ExcelLogger saves to *.tmp, then renames).
    Headers-only workbooks of earlier days (an unused reset_workbook() file
    from a previous run) and then-empty day-folders of earlier days are
    removed.
    """
    if not os.path.isdir(test_result_root):
        return

    today_folder = f"Test_Result_{datetime.now().strftime('%Y-%m-%d')}"
    for folder_name in sorted(os.listdir(test_result_root)):
        folder_path = os.path.join(test_result_root, folder_name)
        if not os.path.isdir(folder_path):
            continue
        for name in sorted(os.listdir(folder_path)):
            file_path = os.path.join(folder_path, name)
            if (name.lower().endswith(".xlsx") and not name.startswith("~$")
                    and not upload_excel_log(file_path) and folder_name != today_folder
                    and _is_headers_only(file_path)):
                os.remove(file_path)
        if folder_name != today_folder and not os.listdir(folder_path):
            try:
                os.rmdir(folder_path)
            except OSError:
                pass

# ---------------------------------------------------------------- Text logs (daily) ----------------

UPLOADED_TEXT_LOG_FOLDER = "Uploaded"
TEXT_LOG_KEEP_DAYS = 30

def upload_old_text_logs(log_root_dir, active_folder_name):
    """
    Uploads every *.txt log in log_root_dir's day-subfolders (e.g.
    "Log_file_2026-10-08") except today's folder and active_folder_name -
    the folder this run is still writing to. They are picked up by a later
    sweep, once their day is over and the tool has been restarted.

    A folder whose files all uploaded is moved to log_root_dir/Uploaded/ so
    it is never sent twice (this bucket's write-only credentials rule out a
    HeadObject pre-check - see img_s3_upload.py / Better Meter's
    s3_uploader.py). If any file fails, the folder stays and is retried on
    the next sweep. Archived folders older than TEXT_LOG_KEEP_DAYS are
    deleted.
    """
    if not os.path.isdir(log_root_dir):
        return

    today = datetime.now().strftime("%Y-%m-%d")
    archive_root = os.path.join(log_root_dir, UPLOADED_TEXT_LOG_FOLDER)
    for folder_name in sorted(os.listdir(log_root_dir)):
        folder_path = os.path.join(log_root_dir, folder_name)
        date_str = _date_from_name(folder_name)
        if (folder_name in (active_folder_name, UPLOADED_TEXT_LOG_FOLDER) or not date_str
                or date_str >= today or not os.path.isdir(folder_path)):
            continue

        all_ok = True
        for name in sorted(os.listdir(folder_path)):
            file_path = os.path.join(folder_path, name)
            if name.lower().endswith(".txt") and os.path.isfile(file_path):
                all_ok &= _upload(file_path, _s3_key(file_path, TEXT_LOG_S3_FOLDER, date_str))

        if all_ok:
            try:
                os.makedirs(archive_root, exist_ok=True)
                shutil.move(folder_path, os.path.join(archive_root, folder_name))
                logging.info(f"Text logs of {folder_name} uploaded - moved to {archive_root}")
            except OSError as exc:
                logging.error(f"Uploaded {folder_name} but could not archive it: {exc}")

    _prune_archive(archive_root)

def _prune_archive(archive_root):
    if not os.path.isdir(archive_root):
        return
    today = datetime.now().date()
    for folder_name in os.listdir(archive_root):
        date_str = _date_from_name(folder_name)
        if not date_str:
            continue
        try:
            age = (today - datetime.strptime(date_str, "%Y-%m-%d").date()).days
        except ValueError:
            continue
        if age > TEXT_LOG_KEEP_DAYS:
            shutil.rmtree(os.path.join(archive_root, folder_name), ignore_errors=True)
            logging.info(f"Removed archived text logs {folder_name} (older than {TEXT_LOG_KEEP_DAYS} days)")

# ---------------------------------------------------------------- Combined sweep -------------------

# Only one sweep at a time - a sweep requested while one is running is skipped.
_sweep_lock = threading.Lock()

def upload_pending_logs(log_root_dir, active_log_folder_name, test_result_root):
    """Uploads earlier days' text logs and any batch workbook whose upload failed before."""
    if not _sweep_lock.acquire(blocking=False):
        return
    try:
        upload_old_text_logs(log_root_dir, active_log_folder_name)
        upload_pending_excel_logs(test_result_root)
    except Exception as exc:
        logging.error(f"S3 pending-log sweep failed: {exc}")
    finally:
        _sweep_lock.release()

def upload_pending_logs_async(log_root_dir, active_log_folder_name, test_result_root):
    """Fire-and-forget version of upload_pending_logs() - see
    upload_excel_log_async() for why this runs on a plain background thread."""
    threading.Thread(
        target=upload_pending_logs,
        args=(log_root_dir, active_log_folder_name, test_result_root),
        daemon=True,
    ).start()
