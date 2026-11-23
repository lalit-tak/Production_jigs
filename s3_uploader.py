"""
Uploads this tool's logs to S3:

- upload_excel_log_async() sends one batch's own, uniquely time-stamped Excel
  test-result workbook once that whole batch finishes, then deletes the local
  copy - see main.py MainWindow.run_test() (creates the file) and
  MainWindow.on_station_finished() (triggers the upload).
- upload_old_text_logs_async() sweeps Log files/ for finalized (not today's)
  *.txt program logs once, when the tool opens - see main.py
  MainWindow.__init__().

Bucket/credentials/key format follow img_s3_upload.py (this same folder) -
the convention already used to upload other jigs' results to this bucket.
"""

import logging
import os
import threading
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# ---------------------------------------------------------------- AWS config --

AWS_ACCESS_KEY_ID = "PUT_YOUR_S3_ACCESS_KEY"
AWS_SECRET_ACCESS_KEY = "PUT_YOUR_S3_SECRET_KEY"
AWS_REGION = "PUT_YOUR_AWS_REGION"
S3_BUCKET_NAME = "PUT_YOUR_BUCKET_NAME"

# This jig's folder under the bucket.

# >>> FILL IN BEFORE USE <<< - this jig's folder under the bucket, e.g.
# "BETTER_METER_JIG" (img_s3_upload.py's equivalent jig uses
# "IMG_JIG_STAGE_1.1"). Left blank, the key just starts at the date instead
# of a jig-name folder.
S3_KEY_PREFIX = "PUT_YOUR_S3_KEY_PREFIX"

# Sub-folder each upload type lands in under S3_KEY_PREFIX, so the Excel
# workbooks and the text logs never mix in the same S3 folder.
EXCEL_LOG_S3_FOLDER = "Excel_log"
TEXT_LOG_S3_FOLDER = "text_log"


def _client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION or None,
        aws_access_key_id=AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
    )


def _s3_key(file_path, folder_name, test_mode = 'ems', date_str=None):
    """
    S3_KEY_PREFIX/{folder_name}/{year}/{month}/{date}/{file_name} - same
    dated-folder layout as img_s3_upload.py's s3_key. folder_name is
    EXCEL_LOG_S3_FOLDER or TEXT_LOG_S3_FOLDER (passed by the caller, not
    derived from file_path) so the two upload types never land in the same
    S3 folder. date_str defaults to today (the excel workbook is always
    uploaded the same day it was written); upload_old_text_logs passes each
    log file's own date instead, since those are never today's.
    """
    if 'ems' in test_mode:
        S3_KEY_PREFIX = f'SURBHI/Better_Meter'
    else:
        S3_KEY_PREFIX = f'TOKYO/Better_Meter'
    test_date = date_str or datetime.now().strftime("%Y-%m-%d")
    year, month, _day = test_date.split("-")
    file_name = os.path.basename(file_path)
    prefix = f"{S3_KEY_PREFIX.rstrip('/')}/" if S3_KEY_PREFIX else ""
    return f"{prefix}{folder_name}/{year}/{month}/{test_date}/{file_name}"


def upload_excel_log(file_path, test_mode_value = 'ems'):
    """
    Uploads `file_path` to s3://S3_BUCKET_NAME/<_s3_key(file_path)>,
    synchronously - blocks the calling thread until the upload finishes or
    fails. Returns True/False; never raises (a failed upload is logged, not
    fatal to the test run). Prefer upload_excel_log_async() from the GUI
    thread so a slow network never blocks the UI.

    On a successful upload, the local file is deleted - safe to do
    unconditionally here because main.py MainWindow.run_test() now hands this
    function a brand-new, uniquely time-stamped workbook for EVERY batch (see
    its docstring/comment there), not one shared file reused across a whole
    day. Each batch therefore gets its own S3 key (the timestamp is part of
    the filename, which _s3_key() uses as-is) - a later batch's upload can
    never land on the same key as an earlier one, so deleting the local copy
    the moment it's safely in S3 can never lose another batch's data. (An
    earlier version of this function reused one fixed-named file for the
    whole day and deleted it after every batch's upload - that silently
    overwrote each earlier batch's already-uploaded rows in S3 the next time
    a batch finished, since ExcelLogger.ensure_exists() would just start a
    fresh, empty workbook under that same name/key. Giving every batch its
    own name instead of reusing one is what actually fixed that, not keeping
    files around - a read-merge-before-write approach isn't available either
    way, since this bucket's credentials are write-only, see the HeadObject
    note in upload_old_text_logs.) A failed upload leaves the file in place,
    so nothing is lost - it will simply sit in Test Result Excel File/
    unuploaded until someone investigates (see program log for the error).
    """
    if not S3_BUCKET_NAME:
        logging.warning(
            f"S3 upload skipped for {file_path}: S3_BUCKET_NAME not configured (see s3_uploader.py)"
        )
        return False

    if not os.path.exists(file_path):
        logging.error(f"S3 upload skipped: {file_path} does not exist")
        return False

    key = _s3_key(file_path, EXCEL_LOG_S3_FOLDER, test_mode = test_mode_value)
    try:
        _client().upload_file(file_path, S3_BUCKET_NAME, key)
    except (BotoCoreError, ClientError, OSError) as exc:
        logging.error(f"S3 upload failed for {file_path} -> s3://{S3_BUCKET_NAME}/{key}: {exc}")
        return False

    logging.info(f"Uploaded {file_path} to s3://{S3_BUCKET_NAME}/{key}")

    try:
        os.remove(file_path)
        logging.info(f"Deleted local {file_path} after successful S3 upload")
    except OSError as exc:
        logging.error(f"Uploaded {file_path} but could not delete the local copy: {exc}")

    return True


def upload_excel_log_async(file_path, test_mode_value = 'ems'):
    """
    Fire-and-forget: runs upload_excel_log() on a background thread so the
    GUI thread never blocks on the network. Success/failure only reaches the
    program log (logging is thread-safe); nothing calls back into the GUI,
    since a plain thread (not QThread) may not touch Qt widgets.
    """
    threading.Thread(target=upload_excel_log, args=(file_path, test_mode_value.lower()), daemon=True).start()


def upload_pending_excel_logs(result_dir, test_mode_value = 'ems'):
    """
    Uploads every *.xlsx still sitting in result_dir - workbooks whose upload
    failed or never ran (tool closed mid-batch, network down, ...). Meant to
    run once at startup (see main.py MainWindow.__init__), when no batch of
    this session exists yet, so nothing here can be a file still being
    written. Each workbook goes to the S3 date folder of its own filename
    ("YYYY-MM-DD_HHMMSS_TEST_RESULT.xlsx"), not today's, and is deleted
    locally after a successful upload - same as upload_excel_log.
    """
    if not S3_BUCKET_NAME:
        logging.warning("S3 upload skipped for pending Excel logs: S3_BUCKET_NAME not configured (see s3_uploader.py)")
        return

    if not os.path.isdir(result_dir):
        return

    client = _client()
    for name in sorted(os.listdir(result_dir)):
        # "~$..." are Excel's lock files for a workbook someone has open.
        if name.startswith("~$") or not name.lower().endswith(".xlsx"):
            continue
        file_path = os.path.join(result_dir, name)
        if not os.path.isfile(file_path):
            continue

        file_date = name.split("_", 1)[0]
        try:
            datetime.strptime(file_date, "%Y-%m-%d")
        except ValueError:
            logging.warning(f"Pending Excel log {file_path} skipped: filename has no YYYY-MM-DD date prefix")
            continue

        key = _s3_key(file_path, EXCEL_LOG_S3_FOLDER, test_mode = test_mode_value, date_str=file_date)
        try:
            client.upload_file(file_path, S3_BUCKET_NAME, key)
        except (BotoCoreError, ClientError, OSError) as exc:
            logging.error(f"S3 upload failed for {file_path} -> s3://{S3_BUCKET_NAME}/{key}: {exc}")
            continue

        logging.info(f"Uploaded pending {file_path} to s3://{S3_BUCKET_NAME}/{key}")

        try:
            os.remove(file_path)
            logging.info(f"Deleted local {file_path} after successful S3 upload")
        except OSError as exc:
            logging.error(f"Uploaded {file_path} but could not delete the local copy: {exc}")


def upload_pending_excel_logs_async(result_dir, test_mode_value = 'ems'):
    """Fire-and-forget version of upload_pending_excel_logs() - see
    upload_excel_log_async() for why this runs on a plain background thread."""
    threading.Thread(
        target=upload_pending_excel_logs, args=(result_dir, test_mode_value.lower()), daemon=True
    ).start()


def upload_old_text_logs(log_dir, today_log_filename, test_mode_value = 'ems'):
    """
    Uploads every *.txt log in log_dir to S3, except today_log_filename -
    today's log is still being appended to (logging.basicConfig has it open)
    so it's skipped and picked up the next time the tool starts, once it's
    finalized. Meant to run once, when the tool opens (see main.py
    MainWindow.__init__), not after every batch - old logs don't change
    once the day that wrote them is over, so there's nothing new to catch
    mid-session.

    Each file is deleted locally right after a successful upload (same as
    upload_excel_log) - that's what keeps re-running this on every startup
    safe, not a pre-upload existence check. A HeadObject check was tried
    here before; it was removed because HeadObject needs s3:GetObject, which
    this bucket's write-only credentials don't grant - S3 returns 403 (not
    404) for a HeadObject you're not allowed to make at all, so the check
    itself failed and silently skipped every file, uploading nothing.
    """
    if not S3_BUCKET_NAME:
        logging.warning("S3 upload skipped for old text logs: S3_BUCKET_NAME not configured (see s3_uploader.py)")
        return

    if not os.path.isdir(log_dir):
        return

    client = _client()
    for name in sorted(os.listdir(log_dir)):
        if name == today_log_filename or not name.lower().endswith(".txt"):
            continue
        file_path = os.path.join(log_dir, name)
        if not os.path.isfile(file_path):
            continue

        # Log filenames are "YYYY-MM-DD_program_log.txt" (main.py) - the
        # date prefix is the log's own date, not today's.
        log_date = name.split("_", 1)[0]
        key = _s3_key(file_path, TEXT_LOG_S3_FOLDER, test_mode = test_mode_value, date_str=log_date)

        try:
            client.upload_file(file_path, S3_BUCKET_NAME, key)
        except (BotoCoreError, ClientError, OSError) as exc:
            logging.error(f"S3 upload failed for {file_path} -> s3://{S3_BUCKET_NAME}/{key}: {exc}")
            continue

        logging.info(f"Uploaded {file_path} to s3://{S3_BUCKET_NAME}/{key}")

        try:
            os.remove(file_path)
            logging.info(f"Deleted local {file_path} after successful S3 upload")
        except OSError as exc:
            logging.error(f"Uploaded {file_path} but could not delete the local copy: {exc}")


def upload_old_text_logs_async(log_dir, today_log_filename, test_mode_value = 'ems'):
    """Fire-and-forget version of upload_old_text_logs() - see
    upload_excel_log_async() for why this runs on a plain background thread."""
    threading.Thread(
        target=upload_old_text_logs, args=(log_dir, today_log_filename, test_mode_value), daemon=True
    ).start()
