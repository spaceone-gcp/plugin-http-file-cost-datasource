from spaceone.core.error import *


class ERROR_EMPTY_BILLED_DATE(ERROR_UNKNOWN):
    _message = "Must have billed_date field or year, month fields.: {result}"


class ERROR_EMPTY_FILE(ERROR_UNKNOWN):
    _message = "File is empty or contains no data: {file_path}. Please check if the source file exists and contains valid data. This may be due to an empty blob, failed download, corrupted file, or attempting to download a directory-like blob."


class ERROR_NO_DATA_ROWS(ERROR_UNKNOWN):
    _message = "File has no data rows: {file_path}"


class ERROR_EMPTY_HEADER(ERROR_UNKNOWN):
    _message = "Empty header line: {file_path}"


class ERROR_NO_DATA_FOUND(ERROR_UNKNOWN):
    _message = "No data found in CSV file: {file_path}"


class ERROR_NO_COLUMNS(ERROR_UNKNOWN):
    _message = "No columns to parse from file: {file_path}"


class ERROR_CSV_PARSING(ERROR_UNKNOWN):
    _message = "CSV parsing error: {error_message}"


class ERROR_FILE_DOWNLOAD_FAILED(ERROR_UNKNOWN):
    _message = "Failed to download file: {file_path}. Please check the file URL and network connectivity."


class ERROR_INVALID_FILE_FORMAT(ERROR_UNKNOWN):
    _message = "Invalid file format: {file_path}. Expected CSV or JSON format."


class ERROR_DIRECTORY_BLOB(ERROR_UNKNOWN):
    _message = "Attempted to download a directory-like blob: {file_path}. Please ensure you are targeting actual files, not directories."
