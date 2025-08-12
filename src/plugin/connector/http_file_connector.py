import logging
import pandas as pd
import numpy as np
import chardet
import requests
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

    @staticmethod
    def _search_csv_format(base_url: str) -> str:
        try:
            response = requests.get(base_url)
            response.encoding = chardet.detect(response.content)["encoding"]
            _LOGGER.debug(f"[_search_csv_format] encoding: {response.encoding}")
            return response.encoding

        except Exception as e:
            _LOGGER.error(f"[_search_csv_format] download error: {e}", exc_info=True)
            raise e
