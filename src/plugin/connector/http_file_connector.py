import logging
import pandas as pd
import numpy as np
import chardet
import requests
import json
import gzip
import io
from spaceone.core.connector import BaseConnector
from spaceone.core.error import ERROR_UNKNOWN
from typing import List

from plugin.error import *

__all__ = ["HTTPFileConnector"]

_LOGGER = logging.getLogger(__name__)

_PAGE_SIZE = 1000


class HTTPFileConnector(BaseConnector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = None
        self.field_mapper = None
        self.default_vars = None

    def create_session(
        self, options: dict, secret_data: dict, schema: str = None
    ) -> None:
        self._check_options(options)
        self.base_url = options["base_url"]

        if "field_mapper" in options:
            self.field_mapper = options["field_mapper"]

        if "default_vars" in options:
            self.default_vars = options["default_vars"]

    def get_cost_data(self, base_url):
        _LOGGER.debug(f"[get_cost_data] base url: {base_url}")

        # 파일 확장자나 URL을 기반으로 파일 형식 감지
        is_json = self._is_json_file(base_url)
        is_parquet = self._is_parquet_file(base_url)
        _LOGGER.debug(f"[get_cost_data] is_json_file result: {is_json}")
        _LOGGER.debug(f"[get_cost_data] is_parquet_file result: {is_parquet}")
        
        if is_json:
            _LOGGER.debug(f"[get_cost_data] Processing as JSON file")
            costs_data = self._get_json(base_url)
        elif is_parquet:
            _LOGGER.debug(f"[get_cost_data] Processing as Parquet file")
            costs_data = self._get_parquet(base_url)
        else:
            _LOGGER.debug(f"[get_cost_data] Processing as CSV file")
            costs_data = self._get_csv(base_url)

        _LOGGER.debug(f"[get_cost_data] costs count: {len(costs_data)}")

        # Paginate
        page_count = int(len(costs_data) / _PAGE_SIZE) + 1

        for page_num in range(page_count):
            offset = _PAGE_SIZE * page_num
            yield costs_data[offset : offset + _PAGE_SIZE]

    @staticmethod
    def _check_options(options: dict) -> None:
        if "base_url" not in options:
            raise ERROR_REQUIRED_PARAMETER(key="options.base_url")

    def _get_csv(self, base_url: str) -> List[dict]:
        try:
            csv_format = self._search_csv_format(base_url)
            
            # 먼저 파일 내용을 확인
            try:
                response = requests.get(base_url, timeout=30)
                response.raise_for_status()
                _LOGGER.debug(f"[_get_csv] Successfully downloaded file from {base_url}")
            except requests.exceptions.RequestException as e:
                _LOGGER.error(f"[_get_csv] Failed to download file from {base_url}: {e}")
                raise ERROR_FILE_DOWNLOAD_FAILED(file_path=base_url)
            
            # 응답 크기 확인
            content_length = len(response.content)
            _LOGGER.debug(f"[_get_csv] Response content length: {content_length} bytes for {base_url}")
            
            # 파일이 비어있는지 확인
            if content_length == 0:
                _LOGGER.error(f"[_get_csv] File is empty (content length 0): {base_url}")
                _LOGGER.error(f"[_get_csv] Response status code: {response.status_code}")
                _LOGGER.error(f"[_get_csv] Response headers: {dict(response.headers)}")
                _LOGGER.error(f"[_get_csv] Response content preview: {repr(response.content[:200])}")
                raise ERROR_EMPTY_FILE(file_path=base_url)
            
            if not response.content.strip():
                _LOGGER.error(f"[_get_csv] File is empty (no content after strip): {base_url}")
                _LOGGER.error(f"[_get_csv] Raw content preview: {repr(response.content[:200])}")
                raise ERROR_EMPTY_FILE(file_path=base_url)
            
            # 파일 내용을 문자열로 디코딩
            try:
                # csv_format이 None이거나 빈 문자열인 경우 기본값 사용
                if not csv_format:
                    csv_format = 'utf-8'
                    _LOGGER.warning(f"[_get_csv] Using default encoding utf-8 as csv_format was {csv_format}")
                
                content = response.content.decode(csv_format, errors='ignore')
            except UnicodeDecodeError as e:
                _LOGGER.error(f"[_get_csv] Failed to decode content with encoding {csv_format}: {e}")
                # 다른 인코딩 시도
                for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
                    try:
                        content = response.content.decode(encoding, errors='ignore')
                        _LOGGER.debug(f"[_get_csv] Successfully decoded with {encoding}")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    raise ERROR_CSV_PARSING(error_message=f"Failed to decode file content with any encoding")
            
            lines = content.strip().split('\n')
            
            # 헤더가 있는지 확인
            if len(lines) < 2:
                _LOGGER.error(f"[_get_csv] File has no data rows: {base_url}")
                _LOGGER.error(f"[_get_csv] Content preview: {repr(content[:200])}")
                raise ERROR_NO_DATA_ROWS(file_path=base_url)
            
            # 첫 번째 줄(헤더) 확인
            header_line = lines[0].strip()
            if not header_line:
                _LOGGER.error(f"[_get_csv] Empty header line: {base_url}")
                raise ERROR_EMPTY_HEADER(file_path=base_url)
            
            # 구분자 자동 감지
            separators = [',', ';', '\t', '|']
            detected_sep = ','
            
            for sep in separators:
                if sep in header_line:
                    detected_sep = sep
                    break
            
            _LOGGER.debug(f"[_get_csv] Detected separator: '{detected_sep}' for {base_url}")
            
            # pandas로 CSV 읽기
            # csv_format이 None이거나 빈 문자열인 경우 기본값 사용
            if not csv_format:
                csv_format = 'utf-8'
                _LOGGER.warning(f"[_get_csv] Using default encoding utf-8 for pandas as csv_format was {csv_format}")
            
            df = pd.read_csv(
                base_url,
                header=0,
                sep=detected_sep,
                engine="python",
                encoding=csv_format,
                dtype=str,
                skip_blank_lines=True,
                on_bad_lines='skip'
            )
            
            # 데이터프레임이 비어있는지 확인
            if df.empty:
                _LOGGER.error(f"[_get_csv] DataFrame is empty after parsing: {base_url}")
                raise ERROR_NO_DATA_FOUND(file_path=base_url)
            
            # 컬럼이 없는지 확인
            if len(df.columns) == 0:
                _LOGGER.error(f"[_get_csv] No columns found in CSV file: {base_url}")
                raise ERROR_NO_COLUMNS(file_path=base_url)
            
            df = df.replace({np.nan: None})
            
            costs_data = df.to_dict("records")
            
            _LOGGER.debug(f"[_get_csv] Successfully read {len(costs_data)} records from {base_url}")
            if costs_data:
                _LOGGER.debug(f"[_get_csv] Columns found: {list(costs_data[0].keys())}")
            
            return costs_data

        except pd.errors.EmptyDataError:
            _LOGGER.error(f"[_get_csv] Empty data error for {base_url}")
            raise ERROR_NO_COLUMNS(file_path=base_url)
        except pd.errors.ParserError as e:
            _LOGGER.error(f"[_get_csv] Parser error for {base_url}: {e}")
            raise ERROR_CSV_PARSING(error_message=str(e))
        except Exception as e:
            _LOGGER.error(f"[_get_csv] download error: {e}", exc_info=True)
            raise e

    def _get_json(self, base_url: str) -> List[dict]:
        """JSON 파일에서 비용 데이터를 읽어오는 메서드"""
        try:
            # 파일 다운로드
            try:
                response = requests.get(base_url, timeout=30)
                response.raise_for_status()
                _LOGGER.debug(f"[_get_json] Successfully downloaded file from {base_url}")
            except requests.exceptions.RequestException as e:
                _LOGGER.error(f"[_get_json] Failed to download file from {base_url}: {e}")
                raise ERROR_FILE_DOWNLOAD_FAILED(file_path=base_url)
            
            # 응답 크기 확인
            content_length = len(response.content)
            _LOGGER.debug(f"[_get_json] Response content length: {content_length} bytes for {base_url}")
            
            # 파일이 비어있는지 확인
            if content_length == 0:
                _LOGGER.error(f"[_get_json] File is empty (content length 0): {base_url}")
                raise ERROR_EMPTY_FILE(file_path=base_url)
            
            # 파일 내용을 문자열로 디코딩 (압축 파일 처리 포함)
            try:
                # .json.gz 파일인 경우 압축 해제
                if base_url.lower().endswith('.json.gz'):
                    _LOGGER.debug(f"[_get_json] Processing gzipped JSON file: {base_url}")
                    with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as gz_file:
                        content = gz_file.read().decode('utf-8', errors='ignore')
                else:
                    content = response.content.decode('utf-8', errors='ignore')
            except UnicodeDecodeError as e:
                _LOGGER.error(f"[_get_json] Failed to decode content: {e}")
                raise ERROR_CSV_PARSING(error_message=f"Failed to decode file content")
            except Exception as e:
                _LOGGER.error(f"[_get_json] Failed to process gzipped content: {e}")
                raise ERROR_CSV_PARSING(error_message=f"Failed to process gzipped file content")
            
            # JSON 파싱
            try:
                # JSON Lines 형식 (각 줄이 개별 JSON 객체)인지 확인
                lines = content.strip().split('\n')
                if len(lines) > 1:
                    # JSON Lines 형식 처리
                    json_data = []
                    for line_num, line in enumerate(lines, 1):
                        line = line.strip()
                        if line:  # 빈 줄 건너뛰기
                            try:
                                json_obj = json.loads(line)
                                json_data.append(json_obj)
                            except json.JSONDecodeError as e:
                                _LOGGER.warning(f"[_get_json] Failed to parse line {line_num}: {e}")
                                continue
                else:
                    # 일반 JSON 형식 처리
                    json_data = json.loads(content)
                    # 배열이 아닌 단일 객체인 경우 배열로 변환
                    if not isinstance(json_data, list):
                        json_data = [json_data]
                
                _LOGGER.debug(f"[_get_json] Successfully parsed {len(json_data)} JSON objects from {base_url}")
                
                if not json_data:
                    _LOGGER.error(f"[_get_json] No valid JSON data found: {base_url}")
                    raise ERROR_NO_DATA_FOUND(file_path=base_url)
                
                # 첫 번째 객체의 키를 로깅
                if json_data:
                    _LOGGER.debug(f"[_get_json] Keys in first object: {list(json_data[0].keys())}")
                
                return json_data
                
            except json.JSONDecodeError as e:
                _LOGGER.error(f"[_get_json] JSON parsing error for {base_url}: {e}")
                raise ERROR_JSON_PARSING(error_message=str(e))
                
        except Exception as e:
            _LOGGER.error(f"[_get_json] download error: {e}", exc_info=True)
            raise e

    def _get_parquet(self, base_url: str) -> List[dict]:
        """
        Parquet 파일을 다운로드하고 파싱하여 비용 데이터를 반환하는 메서드
        
        압축된 Parquet 파일(.parquet.gz, .parquet.snappy, .parquet.zst, .parquet.sz, .parquet.zstd)도 지원합니다.
        
        Args:
            base_url (str): Parquet 파일의 URL
            
        Returns:
            List[dict]: 파싱된 비용 데이터 리스트
            
        Raises:
            ERROR_FILE_DOWNLOAD_FAILED: 파일 다운로드 실패 시
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
            ERROR_NO_DATA_FOUND: 파싱 후 데이터가 없는 경우
            Exception: 기타 오류
        """
        try:
            # 파일 다운로드
            try:
                response = requests.get(base_url, timeout=30)
                response.raise_for_status()
                _LOGGER.debug(f"[_get_parquet] Successfully downloaded file from {base_url}")
            except requests.exceptions.RequestException as e:
                _LOGGER.error(f"[_get_parquet] Failed to download file from {base_url}: {e}")
                raise ERROR_FILE_DOWNLOAD_FAILED(file_path=base_url)
            
            # 응답 크기 확인
            content_length = len(response.content)
            _LOGGER.debug(f"[_get_parquet] Response content length: {content_length} bytes for {base_url}")
            
            # 파일이 비어있는지 확인
            if content_length == 0:
                _LOGGER.error(f"[_get_parquet] File is empty (content length 0): {base_url}")
                raise ERROR_EMPTY_FILE(file_path=base_url)
            
            # 임시 파일에 저장
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.parquet') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name
            
            try:
                # Parquet 파일 파싱
                df = None
                
                # pyarrow 엔진으로 읽기 시도
                try:
                    df = pd.read_parquet(temp_file_path, engine='pyarrow')
                    _LOGGER.debug(f"[_get_parquet] Using pyarrow engine for {base_url}")
                except ImportError:
                    # pyarrow가 없으면 fastparquet 엔진으로 재시도
                    try:
                        df = pd.read_parquet(temp_file_path, engine='fastparquet')
                        _LOGGER.debug(f"[_get_parquet] Using fastparquet engine for {base_url}")
                    except ImportError:
                        # 두 엔진 모두 없으면 에러 발생
                        error_msg = "pyarrow or fastparquet library is required to read Parquet files."
                        _LOGGER.error(f"[_get_parquet] {error_msg}")
                        raise ImportError(error_msg)
                
                # DataFrame이 정상적으로 읽혔는지 확인
                if df is None:
                    raise Exception("Failed to read parquet file with any available engine")
                
                # DataFrame 검증
                if df.empty:
                    _LOGGER.error(f"[_get_parquet] DataFrame is empty: {base_url}")
                    raise ERROR_NO_DATA_FOUND(file_path=base_url)
                
                # NaN 값을 None으로 변환
                df = df.replace({np.nan: None})
                costs_data = df.to_dict("records")
                
                _LOGGER.debug(f"[_get_parquet] Successfully parsed {len(costs_data)} records from {base_url}")
                
                if not costs_data:
                    _LOGGER.error(f"[_get_parquet] No valid data found: {base_url}")
                    raise ERROR_NO_DATA_FOUND(file_path=base_url)
                
                return costs_data
                
            finally:
                # 임시 파일 삭제
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    _LOGGER.warning(f"[_get_parquet] Failed to delete temporary file {temp_file_path}: {e}")
                
        except Exception as e:
            _LOGGER.error(f"[_get_parquet] Parquet processing error: {e}", exc_info=True)
            raise e

    def _is_json_file(self, base_url: str) -> bool:
        """URL이나 파일 확장자를 기반으로 JSON 파일인지 확인하는 메서드"""
        _LOGGER.debug(f"[_is_json_file] Checking if {base_url} is a JSON file")
        
        # URL에 .json 확장자가 있는지 확인 (.json.gz 포함)
        if base_url.lower().endswith('.json') or base_url.lower().endswith('.json.gz'):
            _LOGGER.debug(f"[_is_json_file] Detected .json or .json.gz extension")
            return True
        
        # Content-Type 헤더를 확인하기 위해 HEAD 요청 시도
        try:
            response = requests.head(base_url, timeout=10)
            content_type = response.headers.get('content-type', '').lower()
            _LOGGER.debug(f"[_is_json_file] Content-Type: {content_type}")
            if 'application/json' in content_type or 'text/json' in content_type:
                _LOGGER.debug(f"[_is_json_file] Detected JSON content type")
                return True
        except Exception as e:
            _LOGGER.debug(f"[_is_json_file] HEAD request failed: {e}")
        
        # 파일의 첫 번째 문자를 확인하여 JSON인지 판단
        try:
            response = requests.get(base_url, timeout=10)
            content = response.content.decode('utf-8', errors='ignore').strip()
            _LOGGER.debug(f"[_is_json_file] First 100 chars: {repr(content[:100])}")
            if content.startswith('{') or content.startswith('['):
                _LOGGER.debug(f"[_is_json_file] Detected JSON structure")
                return True
        except Exception as e:
            _LOGGER.debug(f"[_is_json_file] GET request failed: {e}")
        
        _LOGGER.debug(f"[_is_json_file] Not detected as JSON file")
        return False

    def _is_parquet_file(self, base_url: str) -> bool:
        """URL이나 파일 확장자를 기반으로 Parquet 파일인지 확인하는 메서드"""
        _LOGGER.debug(f"[_is_parquet_file] Checking if {base_url} is a Parquet file")
        
        # URL에 .parquet 확장자가 있는지 확인 (압축된 Parquet 파일 포함)
        parquet_extensions = ['.parquet', '.parquet.gz', '.parquet.snappy', '.parquet.zst', '.parquet.sz', '.parquet.zstd']
        for ext in parquet_extensions:
            if base_url.lower().endswith(ext):
                _LOGGER.debug(f"[_is_parquet_file] Detected {ext} extension")
                return True
        
        # Content-Type 헤더를 확인하기 위해 HEAD 요청 시도
        try:
            response = requests.head(base_url, timeout=10)
            content_type = response.headers.get('content-type', '').lower()
            _LOGGER.debug(f"[_is_parquet_file] Content-Type: {content_type}")
            if 'application/octet-stream' in content_type or 'application/parquet' in content_type:
                _LOGGER.debug(f"[_is_parquet_file] Detected Parquet content type")
                return True
        except Exception as e:
            _LOGGER.debug(f"[_is_parquet_file] HEAD request failed: {e}")
        
        _LOGGER.debug(f"[_is_parquet_file] Not detected as Parquet file")
        return False

    @staticmethod
    def _search_csv_format(base_url: str) -> str:
        try:
            response = requests.get(base_url)
            detected_encoding = chardet.detect(response.content)
            
            # chardet이 None을 반환하거나 encoding이 None인 경우 기본값 사용
            if detected_encoding is None or detected_encoding.get("encoding") is None:
                _LOGGER.warning(f"[_search_csv_format] chardet failed to detect encoding, using utf-8 as default")
                return "utf-8"
            
            encoding = detected_encoding["encoding"]
            _LOGGER.debug(f"[_search_csv_format] encoding: {encoding}")
            return encoding

        except Exception as e:
            _LOGGER.error(f"[_search_csv_format] download error: {e}", exc_info=True)
            # 예외 발생 시에도 기본 인코딩 반환
            _LOGGER.warning(f"[_search_csv_format] Using utf-8 as fallback encoding due to error")
            return "utf-8"
