from spaceone.core.error import ERROR_UNKNOWN


class ErrorEmptyBilledDate(ERROR_UNKNOWN):
    _message = "Must have billed_date field or year, month fields.: {result}"


class ErrorEmptyFile(ERROR_UNKNOWN):
    _message = "File is empty or contains no data: {file_path}. Please check if the source file exists and contains valid data. This may be due to an empty blob, failed download, corrupted file, or attempting to download a directory-like blob."


class ErrorNoDataRows(ERROR_UNKNOWN):
    _message = "File has no data rows: {file_path}"


class ErrorEmptyHeader(ERROR_UNKNOWN):
    _message = "Empty header line: {file_path}"


class ErrorNoDataFound(ERROR_UNKNOWN):
    _message = "No data found in CSV file: {file_path}"


class ErrorNoColumns(ERROR_UNKNOWN):
    _message = "No columns to parse from file: {file_path}"


class ErrorCsvParsing(ERROR_UNKNOWN):
    _message = "CSV parsing error: {error_message}"


class ErrorFileDownloadFailed(ERROR_UNKNOWN):
    _message = "Failed to download file: {file_path}. Please check the file URL and network connectivity."


class ErrorInvalidFileFormat(ERROR_UNKNOWN):
    _message = "Invalid file format: {file_path}. Expected CSV or JSON format."


class ErrorJsonParsing(ERROR_UNKNOWN):
    _message = "JSON parsing error: {error_message}"


class ErrorDirectoryBlob(ERROR_UNKNOWN):
    _message = "Attempted to download a directory-like blob: {file_path}. Please ensure you are targeting actual files, not directories."


class ErrorRequiredParameter(ERROR_UNKNOWN):
    _message = "Required parameter is missing: {key}"


# Error constants for import
ERROR_EMPTY_BILLED_DATE = ErrorEmptyBilledDate
ERROR_EMPTY_FILE = ErrorEmptyFile
ERROR_NO_DATA_ROWS = ErrorNoDataRows
ERROR_EMPTY_HEADER = ErrorEmptyHeader
ERROR_NO_DATA_FOUND = ErrorNoDataFound
ERROR_NO_COLUMNS = ErrorNoColumns
ERROR_CSV_PARSING = ErrorCsvParsing
ERROR_FILE_DOWNLOAD_FAILED = ErrorFileDownloadFailed
ERROR_INVALID_FILE_FORMAT = ErrorInvalidFileFormat
ERROR_JSON_PARSING = ErrorJsonParsing
ERROR_DIRECTORY_BLOB = ErrorDirectoryBlob
ERROR_REQUIRED_PARAMETER = ErrorRequiredParameter
