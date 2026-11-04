"""
Synchronization module for Excel (.xlsx), CSV, and Google Sheets.
Columns: Name, PRN/Roll Number, Section, Date, Subject, Period, Faculty, Time, Attendance Status
"""

import os
import csv
import logging
import requests
from typing import Dict, Any, List
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from database import get_attendance_records, get_setting

logger = logging.getLogger("sheet_sync")

EXCEL_PATH = os.path.join(os.path.dirname(__file__), "data", "attendance.xlsx")
CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "attendance.csv")

HEADERS = ["Name", "PRN/Roll Number", "Section", "Date", "Subject", "Period", "Faculty", "Time", "Attendance Status"]
STATUS_COL = len(HEADERS)  # last column index (1-based)


def _row_from_record(record: Dict[str, Any]) -> list:
    """Convert a database attendance record to a spreadsheet row."""
    return [
        record.get("name", ""),
        record.get("prn", record.get("roll_number", "")),
        record.get("section", ""),
        record.get("date", ""),
        record.get("subject", ""),
        record.get("period", 1),
        record.get("faculty_name", ""),
        record.get("time", ""),
        record.get("status", "PRESENT"),
    ]


def ensure_excel_file():
    """Ensure the Excel attendance workbook exists with styled headers."""
    os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)
    if not os.path.exists(EXCEL_PATH):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Attendance Records"
        ws.append(HEADERS)

        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        center_align = Alignment(horizontal="center", vertical="center")
        thin_border = Border(
            left=Side(style='thin', color='D1D5DB'),
            right=Side(style='thin', color='D1D5DB'),
            top=Side(style='thin', color='D1D5DB'),
            bottom=Side(style='thin', color='D1D5DB')
        )

        for col_num in range(1, len(HEADERS) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = thin_border
            ws.column_dimensions[get_column_letter(col_num)].width = 22

        wb.save(EXCEL_PATH)
        logger.info("Initialized new Excel attendance workbook at %s", EXCEL_PATH)


def ensure_csv_file():
    """Ensure the CSV attendance file exists with headers."""
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)
        logger.info("Initialized new CSV attendance file at %s", CSV_PATH)


def append_to_excel(record: Dict[str, Any]):
    """Append an attendance record row to Excel (.xlsx)."""
    try:
        ensure_excel_file()
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb.active

        row_data = _row_from_record(record)
        ws.append(row_data)

        row_idx = ws.max_row
        row_font = Font(name="Arial", size=10)
        center_align = Alignment(horizontal="center", vertical="center")
        thin_border = Border(
            left=Side(style='thin', color='E5E7EB'),
            right=Side(style='thin', color='E5E7EB'),
            top=Side(style='thin', color='E5E7EB'),
            bottom=Side(style='thin', color='E5E7EB')
        )
        fill = PatternFill(
            start_color="F8FAFC" if row_idx % 2 == 0 else "FFFFFF",
            fill_type="solid"
        )

        for col_num in range(1, len(row_data) + 1):
            cell = ws.cell(row=row_idx, column=col_num)
            cell.font = row_font
            cell.alignment = center_align
            cell.border = thin_border
            cell.fill = fill

            if col_num == STATUS_COL:  # Attendance Status column
                cell.fill = PatternFill(start_color="DCFCE7", fill_type="solid")
                cell.font = Font(name="Arial", size=10, bold=True, color="166534")

            col_letter = get_column_letter(col_num)
            val_len = len(str(cell.value or ""))
            current_w = ws.column_dimensions[col_letter].width or 18
            ws.column_dimensions[col_letter].width = max(current_w, val_len + 4)

        wb.save(EXCEL_PATH)
        logger.info("Synchronized attendance record to Excel: %s", record.get("prn"))
    except Exception as e:
        logger.error("Error appending to Excel file: %s", str(e))


def append_to_csv(record: Dict[str, Any]):
    """Append attendance record to CSV."""
    try:
        ensure_csv_file()
        with open(CSV_PATH, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_row_from_record(record))
        logger.info("Synchronized attendance record to CSV: %s", record.get("prn"))
    except Exception as e:
        logger.error("Error appending to CSV file: %s", str(e))


def sync_to_google_sheets(record: Dict[str, Any]) -> bool:
    """Forward attendance record to Google Sheets via Apps Script Webhook."""
    webhook_url = get_setting("google_sheets_webhook", "").strip()
    if not webhook_url:
        return False

    payload = {
        "name": record.get("name", ""),
        "prn": record.get("prn", record.get("roll_number", "")),
        "section": record.get("section", ""),
        "date": record.get("date", ""),
        "subject": record.get("subject", ""),
        "period": record.get("period", 1),
        "faculty_name": record.get("faculty_name", ""),
        "time": record.get("time", ""),
        "status": record.get("status", "PRESENT"),
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=5)
        return response.status_code in [200, 201, 302]
    except Exception as e:
        logger.warning("Failed to forward attendance to Google Sheets: %s", str(e))
        return False


def sync_attendance_record(record: Dict[str, Any]):
    """Sync one record to Excel (.xlsx), CSV, and Google Sheets (best-effort)."""
    append_to_excel(record)
    append_to_csv(record)
    sync_to_google_sheets(record)


def rebuild_csv_from_db(records: List[Dict[str, Any]] = None):
    """Rebuild the entire CSV file from database records."""
    if records is None:
        records = get_attendance_records()

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for rec in records:
            writer.writerow(_row_from_record(rec))
    logger.info("Rebuilt CSV file from DB (%d records)", len(records))


def rebuild_excel_from_db(records: List[Dict[str, Any]] = None):
    """Rebuild the entire Excel file from database records."""
    if records is None:
        records = get_attendance_records()

    os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Records"
    ws.append(HEADERS)

    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color='D1D5DB'),
        right=Side(style='thin', color='D1D5DB'),
        top=Side(style='thin', color='D1D5DB'),
        bottom=Side(style='thin', color='D1D5DB')
    )

    for col_num in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border

    for idx, rec in enumerate(records, start=2):
        row_data = _row_from_record(rec)
        ws.append(row_data)

        fill = PatternFill(start_color="F8FAFC" if idx % 2 == 0 else "FFFFFF", fill_type="solid")
        for col_num in range(1, len(row_data) + 1):
            cell = ws.cell(row=idx, column=col_num)
            cell.font = Font(name="Arial", size=10)
            cell.alignment = center_align
            cell.border = thin_border
            cell.fill = fill
            if col_num == STATUS_COL:
                cell.fill = PatternFill(start_color="DCFCE7", fill_type="solid")
                cell.font = Font(name="Arial", size=10, bold=True, color="166534")

    for col_num in range(1, len(HEADERS) + 1):
        col_letter = get_column_letter(col_num)
        max_len = max(
            len(str(ws.cell(row=r, column=col_num).value or ""))
            for r in range(1, ws.max_row + 1)
        ) if ws.max_row > 0 else 18
        ws.column_dimensions[col_letter].width = max(max_len + 4, 18)

    wb.save(EXCEL_PATH)
    logger.info("Rebuilt Excel file from DB (%d records)", len(records))


# Initialize on import
ensure_excel_file()
ensure_csv_file()
