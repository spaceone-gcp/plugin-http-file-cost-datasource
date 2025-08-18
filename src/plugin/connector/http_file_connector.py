# HTTP 파일에서 비용 데이터를 수집하는 커넥터
# CSV, JSON, Parquet 형식의 파일을 지원하며, HTTP/HTTPS URL을 통해 파일을 다운로드하여 처리
import logging
import pandas as pd
import numpy as np
import chardet
import requests
import json
import gzip
import io
from spaceone.core.connector import BaseConnector
from spaceone.core.error import ERROR_REQUIRED_PARAMETER
from typing import List

# 커스텀 에러 클래스들 import
from plugin.error.cost import (
    ERROR_EMPTY_FILE,
    ERROR_NO_DATA_ROWS,
    ERROR_EMPTY_HEADER,
    ERROR_NO_DATA_FOUND,
    ERROR_NO_COLUMNS,
    ERROR_CSV_PARSING,
    ERROR_FILE_DOWNLOAD_FAILED,
    ERROR_JSON_PARSING,
)

# 모듈 내보내기 
__all__ = ["HTTPFileConnector"]
# 로거 설정     
_LOGGER = logging.getLogger(__name__)
# 페이지네이션을 위한 페이지 크기 설정
_PAGE_SIZE = 1000

class HTTPFileConnector(BaseConnector):
    """
    HTTP/HTTPS URL을 통해 파일을 다운로드하고 비용 데이터를 추출하는 커넥터
    
    지원하는 파일 형식:
    - CSV (쉼표, 세미콜론, 탭, 파이프로 구분)
    - JSON (일반 JSON, JSON Lines 형식)
    - Parquet (압축된 Parquet 파일 포함)
    """
    # 초기화 메서드 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)   # 기본 설정값들을 None으로 초기화   
        self.base_url = None                # 기본 URL
        self.field_mapper = None            # 필드 매핑 설정
        self.default_vars = None            # 기본 변수들

    # 세션 생성 메서드 
    def create_session(
        self, options: dict, secret_data: dict, schema: str = None
    ) -> None:
        """
        세션 생성 및 설정
        
        Args:
            options: 설정 옵션 (base_url, field_mapper, default_vars 포함)
            secret_data: 인증 정보 (현재 사용되지 않음)
            schema: 스키마 정보 (현재 사용되지 않음)
        """
        # 필수 옵션 검증
        self._check_options(options)
        # 기본 URL 설정
        self.base_url = options["base_url"]
        # 선택적 옵션들 설정
        if "field_mapper" in options:
            self.field_mapper = options["field_mapper"]  # 필드 매핑 설정
        if "default_vars" in options:
            self.default_vars = options["default_vars"]  # 기본 변수들

    # 비용 데이터 가져오기 메서드 
    def get_cost_data(self, base_url):
        """
        비용 데이터를 가져오는 메인 메서드
        
        파일 형식을 자동 감지하여 적절한 파서를 사용하고,
        결과를 페이지 단위로 반환합니다.
        
        Args:
            base_url: 파일 URL
            
        Yields:
            List[dict]: 페이지 단위의 비용 데이터
        """
        # 1. 파일 형식에 따른 파싱 메서드 호출
        # 1-1. JSON 파일 파싱
        if self._is_json_file(base_url): 
            costs_data = self._get_json(base_url)
        # 1-2. Parquet 파일 파싱
        elif self._is_parquet_file(base_url):
            costs_data = self._get_parquet(base_url)
        # 1-3. CSV 파일 파싱
        else:
            costs_data = self._get_csv(base_url)

        # 2. 페이지네이션 처리
        page_count = int(len(costs_data) / _PAGE_SIZE) + 1
        # 2-1. 페이지 단위로 데이터 반환
        for page_num in range(page_count):
            # 2-1-1. 페이지 오프셋 계산     
            offset = _PAGE_SIZE * page_num
            # 2-1-2. 페이지 단위로 데이터 반환
            yield costs_data[offset : offset + _PAGE_SIZE]

    @staticmethod
    def _check_options(options: dict) -> None:
        """
        필수 옵션 검증
        
        Args:
            options: 검증할 옵션 딕셔너리
            
        Raises:
            ERROR_REQUIRED_PARAMETER: base_url이 없는 경우
        """
        # 1. base_url이 없는 경우 예외 발생
        if "base_url" not in options:
            raise ERROR_REQUIRED_PARAMETER(key="options.base_url")

    def _get_csv(self, base_url: str) -> List[dict]:
        """
        CSV 파일에서 비용 데이터를 읽어오는 메서드
        
        처리 과정:
        1. 파일 인코딩 자동 감지
        2. 파일 다운로드 및 응답/내용 검증
        3. 파일 내용 디코딩
        4. 헤더 및 데이터 행 검증
        5. 구분자 자동 감지
        6. pandas를 활용한 CSV 파싱
        7. 컬럼 및 데이터 유효성 검증 및 변환
        
        Args:
            base_url: CSV 파일 URL
            
        Returns:
            List[dict]: 파싱된 비용 데이터 리스트
            
        Raises:
            ERROR_FILE_DOWNLOAD_FAILED: 파일 다운로드 실패
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
            ERROR_NO_DATA_ROWS: 데이터 행이 없는 경우
            ERROR_EMPTY_HEADER: 헤더가 비어있는 경우
            ERROR_NO_DATA_FOUND: 파싱 후 데이터가 없는 경우
            ERROR_NO_COLUMNS: 컬럼이 없는 경우
            ERROR_CSV_PARSING: CSV 파싱 오류
        """
        try:
            # 1. CSV 형식 감지 (인코딩 등)
            csv_format = self._search_csv_format(base_url)
            
            # 2. 파일 다운로드
            try:
                # 1-1. 파일 다운로드
                response = requests.get(base_url, timeout=30)
                # 1-2. 파일 다운로드 성공 검증
                response.raise_for_status()
            # 2-1. 파일 다운로드 실패 예외 발생
            except requests.exceptions.RequestException as e:
                # 2-2. 파일 다운로드 실패 로깅
                _LOGGER.error(f"[_get_csv] Failed to download file from {base_url}: {e}")
                raise ERROR_FILE_DOWNLOAD_FAILED(file_path=base_url)
            
            # 3. 응답 크기 및 내용 검증
            content_length = len(response.content)
            # 3-1. 응답 크기 확인
            if content_length == 0:
                _LOGGER.error(f"[_get_csv] File is empty (content length 0): {base_url}")
                raise ERROR_EMPTY_FILE(file_path=base_url)
            # 3-1. 파일이 비어있는지 확인
            if not response.content.strip():
                _LOGGER.error(f"[_get_csv] File is empty (no content after strip): {base_url}")
                raise ERROR_EMPTY_FILE(file_path=base_url)
            
            # 4. 파일 내용 디코딩
            try:
                # 4-1. csv_format이 None이거나 빈 문자열인 경우 기본값 사용 (선택)
                if not csv_format:
                    csv_format = 'utf-8' # 기본 인코딩 설정     
                # 4-2. 파일 내용 디코딩
                content = response.content.decode(csv_format, errors='ignore')
            # 4-3. 파일 내용 디코딩 실패 예외 발생
            except UnicodeDecodeError as e:
                _LOGGER.error(f"[_get_csv] Failed to decode content with encoding {csv_format}: {e}")
                for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:  # 다른 인코딩 시도 
                    try:
                        content = response.content.decode(encoding, errors='ignore')  # 다른 인코딩 시도 
                        break
                    except UnicodeDecodeError: # 다른 인코딩 시도 실패 예외 발생
                        continue
                else: # 다른 인코딩 시도 실패 예외 발생 
                    raise ERROR_CSV_PARSING(error_message="Failed to decode file content with any encoding")
            
            # 5. 라인별 분석 및 헤더 검증
            lines = content.strip().split('\n')
            # 5-1. 헤더가 있는지 확인
            if len(lines) < 2:
                _LOGGER.error(f"[_get_csv] File has no data rows: {base_url}")
                raise ERROR_NO_DATA_ROWS(file_path=base_url)
            # 5-2. 첫 번째 줄(헤더) 확인
            header_line = lines[0].strip()
            if not header_line:
                _LOGGER.error(f"[_get_csv] Empty header line: {base_url}")
                raise ERROR_EMPTY_HEADER(file_path=base_url)
            
            # 6. 구분자 자동 감지
            separators = [',', ';', '\t', '|']
            # 6-1. 구분자 초기값 설정
            detected_sep = ','
            # 6-2. 구분자 자동 감지
            for sep in separators:
                # 6-2-1. 구분자가 헤더 라인에 있는지 확인
                if sep in header_line:
                    # 6-2-2. 구분자 감지
                    detected_sep = sep
                    # 6-2-3. 구분자 감지 종료
                    break
            
            # 7. pandas를 사용한 CSV 파싱
            # 7-1. csv_format이 None이거나 빈 문자열인 경우 기본값 사용
            if not csv_format:
                csv_format = 'utf-8' # 기본 인코딩 설정 
            # 7-2. pandas를 사용한 CSV 파싱 
            df = pd.read_csv(
                base_url,  # 파일 URL
                header=0,  # 헤더 행 번호
                sep=detected_sep,  # 구분자
                engine="python",  # 엔진 설정
                encoding=csv_format,  # 인코딩
                dtype=str,  # 데이터 타입
                skip_blank_lines=True,  # 빈 줄 건너뛰기
                on_bad_lines='skip'  # 잘못된 줄 건너뛰기
            )
            
            # 8. 데이터프레임 검증
            # 8-1. 데이터프레임이 비어있는지 확인
            if df.empty:
                _LOGGER.error(f"[_get_csv] DataFrame is empty after parsing: {base_url}")
                raise ERROR_NO_DATA_FOUND(file_path=base_url)
            
            # 8-2. 컬럼이 없는지 확인
            if len(df.columns) == 0:
                _LOGGER.error(f"[_get_csv] No columns found in CSV file: {base_url}")
                raise ERROR_NO_COLUMNS(file_path=base_url)
            
            # 9. 데이터 정리 및 변환
            df = df.replace({np.nan: None})  # NaN 값을 None으로 변환
            costs_data = df.to_dict("records")  # 데이터프레임을 딕셔너리 리스트로 변환
            if costs_data: # 데이터가 있는지 확인
                _LOGGER.debug(f"[_get_csv] Columns found: {list(costs_data[0].keys())}")
            return costs_data

        except pd.errors.EmptyDataError: # 데이터프레임이 비어있는 경우 예외 발생
            _LOGGER.error(f"[_get_csv] Empty data error for {base_url}")
            raise ERROR_NO_COLUMNS(file_path=base_url)
        except pd.errors.ParserError as e: # 파서 오류 예외 발생
            _LOGGER.error(f"[_get_csv] Parser error for {base_url}: {e}")
            raise ERROR_CSV_PARSING(error_message=str(e))
        except Exception as e: # 기타 오류 예외 발생
            _LOGGER.error(f"[_get_csv] download error: {e}", exc_info=True)
            raise e

    def _get_json(self, base_url: str) -> List[dict]:
        """
        JSON 파일에서 비용 데이터를 읽어오는 메서드
        
        처리 과정:
        1. 파일 다운로드 및 응답 검증
        2. 압축 파일 처리 (.json.gz)
        3. JSON 형식 감지 (일반 JSON vs JSON Lines)
        4. JSON 파싱 및 데이터 검증
        
        Args:
            base_url: JSON 파일 URL
            
        Returns:
            List[dict]: 파싱된 비용 데이터 리스트
            
        Raises:
            ERROR_FILE_DOWNLOAD_FAILED: 파일 다운로드 실패
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
            ERROR_NO_DATA_FOUND: 파싱 후 데이터가 없는 경우
            ERROR_JSON_PARSING: JSON 파싱 오류
        """
        try:
            # 1. 파일 다운로드
            try:
                response = requests.get(base_url, timeout=30)  # 파일 다운로드
                response.raise_for_status()  # 파일 다운로드 성공 검증
            except requests.exceptions.RequestException as e:  # 파일 다운로드 실패 예외 발생
                _LOGGER.error(f"[_get_json] Failed to download file from {base_url}: {e}")
                raise ERROR_FILE_DOWNLOAD_FAILED(file_path=base_url)
            
            # 2. 응답 크기 확인
            content_length = len(response.content)  # 응답 크기 확인
            if content_length == 0:  # 응답 크기 확인
                _LOGGER.error(f"[_get_json] File is empty (content length 0): {base_url}")
                raise ERROR_EMPTY_FILE(file_path=base_url)
            
            # 3. 파일 내용 디코딩 (압축 파일 처리 포함)
            try:
                if base_url.lower().endswith('.json.gz'):  # .json.gz 파일인 경우
                    with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as gz_file:  # 압축 해제
                        content = gz_file.read().decode('utf-8', errors='ignore')  # 파일 내용 디코딩
                else:  # 압축 파일이 아닌 경우
                    content = response.content.decode('utf-8', errors='ignore')  # 파일 내용 디코딩
            except UnicodeDecodeError as e: # 파일 내용 디코딩 실패 예외 발생
                _LOGGER.error(f"[_get_json] Failed to decode content: {e}")
                raise ERROR_CSV_PARSING(error_message="Failed to decode file content")
            except Exception as e: # 기타 오류 예외 발생
                _LOGGER.error(f"[_get_json] Failed to process gzipped content: {e}")
                raise ERROR_CSV_PARSING(error_message="Failed to process gzipped file content")
            
            # 4. JSON 파싱
            try:
                # JSON Lines 형식 (각 줄이 개별 JSON 객체)인지 확인
                lines = content.strip().split('\n')
                if len(lines) > 1:
                    # JSON Lines 형식 처리
                    json_data = [] # JSON 데이터 초기화
                    for line_num, line in enumerate(lines, 1):  # 줄 번호 및 줄 내용 반복
                        line = line.strip()  # 줄 내용 공백 제거
                        if line:  # 빈 줄 건너뛰기
                            try:  # JSON 파싱 시도
                                json_obj = json.loads(line)  # JSON 파싱
                                json_data.append(json_obj)  # JSON 객체 추가
                            except json.JSONDecodeError as e:  # JSON 파싱 오류 예외 발생
                                _LOGGER.warning(f"[_get_json] Failed to parse line {line_num}: {e}")
                                continue
                else:
                    json_data = json.loads(content)  # JSON 파싱
                    if not isinstance(json_data, list):  # 배열이 아닌 단일 객체인 경우 배열로 변환
                        json_data = [json_data]
                
                if not json_data:  # JSON 데이터가 없는 경우 예외 발생
                    _LOGGER.error(f"[_get_json] No valid JSON data found: {base_url}")
                    raise ERROR_NO_DATA_FOUND(file_path=base_url)

                return json_data
                
            except json.JSONDecodeError as e:  # JSON 파싱 오류 예외 발생
                _LOGGER.error(f"[_get_json] JSON parsing error for {base_url}: {e}")
                raise ERROR_JSON_PARSING(error_message=str(e))
                
        except Exception as e:  # 기타 오류 예외 발생
            _LOGGER.error(f"[_get_json] download error: {e}", exc_info=True)
            raise e

    def _get_parquet(self, base_url: str) -> List[dict]:
        """
        Parquet 파일을 다운로드하고 파싱하여 비용 데이터를 반환하는 메서드
        
        처리 과정:
        1. 파일 다운로드 및 응답 검증
        2. 임시 파일에 저장
        3. pyarrow 또는 fastparquet 엔진으로 파싱
        4. 데이터 검증 및 변환
        5. 임시 파일 정리
        
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
            # 1. 파일 다운로드
            try:
                response = requests.get(base_url, timeout=30)  # 파일 다운로드
                response.raise_for_status()  # 파일 다운로드 성공 검증
            except requests.exceptions.RequestException as e:  # 파일 다운로드 실패 예외 발생
                _LOGGER.error(f"[_get_parquet] Failed to download file from {base_url}: {e}")
                raise ERROR_FILE_DOWNLOAD_FAILED(file_path=base_url)
            
            # 2. 응답 크기 확인
            content_length = len(response.content)  # 응답 크기 확인
            if content_length == 0:
                _LOGGER.error(f"[_get_parquet] File is empty (content length 0): {base_url}")
                raise ERROR_EMPTY_FILE(file_path=base_url)
            
            # 3. 임시 파일에 저장
            import tempfile  # 임시 파일 생성
            import os  # 파일 시스템 접근
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.parquet') as temp_file:  # 임시 파일 생성
                temp_file.write(response.content)  # 파일 내용 쓰기
                temp_file_path = temp_file.name  # 임시 파일 경로
            
            try:
                # 4. Parquet 파일 파싱
                df = None  # DataFrame 초기화
                
                # pyarrow 엔진으로 읽기 시도
                try:
                    df = pd.read_parquet(temp_file_path, engine='pyarrow')  # pyarrow 엔진으로 읽기 시도
                except ImportError:  # pyarrow가 없으면 fastparquet 엔진으로 재시도
                    try:
                        df = pd.read_parquet(temp_file_path, engine='fastparquet')  # fastparquet 엔진으로 읽기 시도
                    except ImportError:  # 두 엔진 모두 없으면 에러 발생
                        error_msg = "pyarrow or fastparquet library is required to read Parquet files."
                        _LOGGER.error(f"[_get_parquet] {error_msg}")
                        raise ImportError(error_msg)
                
                if df is None:  # DataFrame이 정상적으로 읽혔는지 확인
                    _LOGGER.error(f"[_get_parquet] Failed to read parquet file with any available engine: {base_url}")
                    raise Exception("Failed to read parquet file with any available engine")
                
                if df.empty:  # DataFrame이 비어있는지 확인
                    _LOGGER.error(f"[_get_parquet] DataFrame is empty: {base_url}")
                    raise ERROR_NO_DATA_FOUND(file_path=base_url)
                
                # 6. 데이터 정리 및 변환
                df = df.replace({np.nan: None})  # NaN 값을 None으로 변환
                costs_data = df.to_dict("records")  # DataFrame을 딕셔너리 리스트로 변환
                if not costs_data:  # 데이터가 없는지 확인
                    _LOGGER.error(f"[_get_parquet] No valid data found: {base_url}")
                    raise ERROR_NO_DATA_FOUND(file_path=base_url)
                
                return costs_data
                
            finally:
                # 7. 임시 파일 정리
                try:
                    os.unlink(temp_file_path)  # 임시 파일 삭제
                except Exception as e:  # 임시 파일 삭제 실패 예외 발생
                    _LOGGER.warning(f"[_get_parquet] Failed to delete temporary file {temp_file_path}: {e}")
                
        except Exception as e:  # 기타 오류 예외 발생
            _LOGGER.error(f"[_get_parquet] Parquet processing error: {e}", exc_info=True)
            raise e

    def _is_json_file(self, base_url: str) -> bool:
        """
        URL이나 파일 확장자를 기반으로 JSON 파일인지 확인하는 메서드
        
        감지 방법:
        1. 파일 확장자 확인 (.json, .json.gz)
        2. Content-Type 헤더 확인
        3. 파일 내용의 첫 번째 문자 확인
        
        Args:
            base_url: 확인할 파일 URL
            
        Returns:
            bool: JSON 파일이면 True, 아니면 False
        """
        # 1. URL에 .json 확장자가 있는지 확인 (.json.gz 포함)
        if base_url.lower().endswith('.json') or base_url.lower().endswith('.json.gz'):
            _LOGGER.debug("[_is_json_file] Detected .json or .json.gz extension")
            return True
        
        # 2. Content-Type 헤더를 확인하기 위해 HEAD 요청 시도
        try:
            response = requests.head(base_url, timeout=10)  # HEAD 요청 시도
            content_type = response.headers.get('content-type', '').lower()  # Content-Type 헤더 확인
            if 'application/json' in content_type or 'text/json' in content_type:
                _LOGGER.debug("[_is_json_file] Detected JSON content type")  # JSON 콘텐츠 타입 감지
                return True
        except Exception as e:  # 기타 오류 예외 발생
            _LOGGER.debug(f"[_is_json_file] HEAD request failed: {e}")  # HEAD 요청 실패 로깅
        
        # 3. 파일의 첫 번째 문자를 확인하여 JSON인지 판단
        try:
            response = requests.get(base_url, timeout=10)  # GET 요청 시도
            content = response.content.decode('utf-8', errors='ignore').strip()  # 파일 내용 디코딩
            if content.startswith('{') or content.startswith('['):
                _LOGGER.debug("[_is_json_file] Detected JSON structure")  # JSON 구조 감지
                return True
        except Exception as e:  # 기타 오류 예외 발생
            _LOGGER.debug(f"[_is_json_file] GET request failed: {e}")  # GET 요청 실패 로깅
        
        return False

    def _is_parquet_file(self, base_url: str) -> bool:
        """
        URL이나 파일 확장자를 기반으로 Parquet 파일인지 확인하는 메서드
        
        감지 방법:
        1. 파일 확장자 확인 (다양한 압축 형식 포함)
        2. Content-Type 헤더 확인
        
        Args:
            base_url: 확인할 파일 URL
            
        Returns:
            bool: Parquet 파일이면 True, 아니면 False
        """
        # 1. URL에 .parquet 확장자가 있는지 확인 (압축된 Parquet 파일 포함)
        parquet_extensions = ['.parquet', '.parquet.gz', '.parquet.snappy', '.parquet.zst', '.parquet.sz', '.parquet.zstd']
        for ext in parquet_extensions:  # 파일 확장자 확인
            if base_url.lower().endswith(ext):  # 파일 확장자 확인
                _LOGGER.debug(f"[_is_parquet_file] Detected {ext} extension")  # 파일 확장자 감지
                return True
        
        # 2. Content-Type 헤더를 확인하기 위해 HEAD 요청 시도
        try:
            response = requests.head(base_url, timeout=10)  # HEAD 요청 시도
            content_type = response.headers.get('content-type', '').lower()  # Content-Type 헤더 확인
            if 'application/octet-stream' in content_type or 'application/parquet' in content_type:  # Parquet 콘텐츠 타입 확인
                return True
        except Exception as e:  # 기타 오류 예외 발생
            _LOGGER.debug(f"[_is_parquet_file] HEAD request failed: {e}")
        
        return False

    @staticmethod
    def _search_csv_format(base_url: str) -> str:
        """
        CSV 파일의 인코딩을 자동으로 감지하는 메서드
        
        chardet 라이브러리를 사용하여 파일 내용의 인코딩을 감지합니다.
        감지에 실패하면 기본값으로 'utf-8'을 반환합니다.
        
        Args:
            base_url: CSV 파일 URL
            
        Returns:
            str: 감지된 인코딩 (기본값: 'utf-8')
        """
        try:
            # 1. 파일 다운로드
            response = requests.get(base_url)
            
            # 2. chardet을 사용한 인코딩 감지
            detected_encoding = chardet.detect(response.content)
            
            # 3. 감지 결과 검증 및 기본값 처리
            if detected_encoding is None or detected_encoding.get("encoding") is None:  # chardet이 None을 반환하거나 encoding이 None인 경우 기본값 사용
                _LOGGER.warning("[_search_csv_format] chardet failed to detect encoding, using utf-8 as default")
                return "utf-8"
            
            encoding = detected_encoding["encoding"]  # 감지된 인코딩
            _LOGGER.debug(f"[_search_csv_format] encoding: {encoding}")
            return encoding

        except Exception as e:  # 기타 오류 예외 발생
            _LOGGER.error(f"[_search_csv_format] download error: {e}", exc_info=True)  # 다운로드 오류 로깅
            return "utf-8"
