"""
Persian/Shamsi (Jalali) calendar utilities for the accounting software.
"""

import jdatetime
from datetime import datetime
from typing import Optional


def shamsi_now() -> str:
    """Get current date in Shamsi format (YYYY/MM/DD)."""
    return jdatetime.datetime.now().strftime('%Y/%m/%d')


def shamsi_today_iso() -> str:
    """Get current date in ISO format for database (YYYY-MM-DD)."""
    return datetime.now().strftime('%Y-%m-%d')


def shamsi_to_gregorian(shamsi_date: str) -> Optional[str]:
    """
    Convert Shamsi date to Gregorian for database storage.
    
    Args:
        shamsi_date: Date in format YYYY/MM/DD
        
    Returns:
        Gregorian date in ISO format (YYYY-MM-DD) or None if invalid
    """
    try:
        # Handle different input formats
        shamsi_date = shamsi_date.replace('/', '-').replace('.', '-')
        parts = shamsi_date.split('-')
        
        if len(parts) != 3:
            return None
        
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        
        # Create jdatetime object
        j_date = jdatetime.date(year, month, day)
        
        # Convert to Gregorian
        g_date = j_date.togregorian()
        
        return g_date.strftime('%Y-%m-%d')
    except:
        return None


def gregorian_to_shamsi(gregorian_date: str) -> str:
    """
    Convert Gregorian date to Shamsi for display.
    
    Args:
        gregorian_date: Date in ISO format (YYYY-MM-DD) or datetime string
        
    Returns:
        Shamsi date in format YYYY/MM/DD
    """
    try:
        # Handle datetime strings (YYYY-MM-DD HH:MM:SS)
        if ' ' in gregorian_date:
            gregorian_date = gregorian_date.split(' ')[0]
        
        # Parse the date
        if isinstance(gregorian_date, str):
            parts = gregorian_date.split('-')
            if len(parts) != 3:
                return gregorian_date
            
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            g_date = datetime(year, month, day)
        else:
            g_date = gregorian_date
        
        # Convert to Jalali
        j_date = jdatetime.date.fromgregorian(date=g_date)
        
        return j_date.strftime('%Y/%m/%d')
    except:
        return gregorian_date


def format_shamsi_datetime(gregorian_datetime: str) -> str:
    """
    Convert Gregorian datetime to Shamsi with time.
    
    Args:
        gregorian_datetime: Datetime string (YYYY-MM-DD HH:MM:SS)
        
    Returns:
        Formatted Shamsi datetime
    """
    try:
        # Parse datetime
        dt = datetime.strptime(gregorian_datetime, '%Y-%m-%d %H:%M:%S')
        
        # Convert to Jalali
        j_dt = jdatetime.datetime.fromgregorian(datetime=dt)
        
        return j_dt.strftime('%Y/%m/%d - %H:%M')
    except:
        return gregorian_datetime


def get_shamsi_month_start() -> str:
    """Get the first day of current Shamsi month in ISO format."""
    j_now = jdatetime.datetime.now()
    j_start = jdatetime.date(j_now.year, j_now.month, 1)
    g_start = j_start.togregorian()
    return g_start.strftime('%Y-%m-%d')


def get_shamsi_year_start() -> str:
    """Get the first day of current Shamsi year in ISO format."""
    j_now = jdatetime.datetime.now()
    j_start = jdatetime.date(j_now.year, 1, 1)
    g_start = j_start.togregorian()
    return g_start.strftime('%Y-%m-%d')


def validate_shamsi_date(date_str: str) -> bool:
    """
    Validate if a string is a valid Shamsi date.
    
    Args:
        date_str: Date string to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        date_str = date_str.replace('/', '-').replace('.', '-')
        parts = date_str.split('-')
        
        if len(parts) != 3:
            return False
        
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        
        # Check ranges
        if year < 1300 or year > 1500:  # Reasonable range
            return False
        if month < 1 or month > 12:
            return False
        if day < 1 or day > 31:
            return False
        
        # Try to create the date
        jdatetime.date(year, month, day)
        return True
    except:
        return False


def get_shamsi_month_name(month: int) -> str:
    """Get Persian month name."""
    months = {
        1: 'فروردین',
        2: 'اردیبهشت',
        3: 'خرداد',
        4: 'تیر',
        5: 'مرداد',
        6: 'شهریور',
        7: 'مهر',
        8: 'آبان',
        9: 'آذر',
        10: 'دی',
        11: 'بهمن',
        12: 'اسفند'
    }
    return months.get(month, '')


def get_shamsi_weekday_name(weekday: int) -> str:
    """Get Persian weekday name (0=Saturday in Persian calendar)."""
    days = {
        0: 'شنبه',
        1: 'یکشنبه',
        2: 'دوشنبه',
        3: 'سه‌شنبه',
        4: 'چهارشنبه',
        5: 'پنج‌شنبه',
        6: 'جمعه'
    }
    return days.get(weekday, '')
