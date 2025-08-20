# 파일 파싱 공통 로직을 담은 베이스 클래스
import logging
import os
import json
import gzip
import hashlib
import re
from typing import List, Dict, Any, Generator
import numpy as np
import pandas as pd
import requests
import chardet

from spaceone.core.connector import BaseConnector
from plugin.error.cost import (
    ERROR_EMPTY_FILE,  # 파일이 비어있는 경우
    ERROR_NO_DATA_ROWS,  # 데이터 행이 없는 경우
    ERROR_EMPTY_HEADER,  # 헤더가 비어있는 경우 
    ERROR_NO_DATA_FOUND,  # 파싱 후 데이터가 없는 경우
    ERROR_NO_COLUMNS,  # 컬럼이 없는 경우
    ERROR_CSV_PARSING,  # CSV 파싱 오류
    ERROR_FILE_DOWNLOAD_FAILED,  # 파일 다운로드 실패 시
)

# 공통 상수 정의
PAGE_SIZE = 1000  # 페이지 크기
MIN_FILE_SIZE = 50  # 최소 파일 크기
MAX_FILENAME_LENGTH = 100  # 최대 파일명 길이
MAX_FINAL_FILENAME_LENGTH = 150  # 최종 파일명 길이
UNDERSCORE_RATIO_THRESHOLD = 0.3  # 언더스코어 비율 임계값
SUPPORTED_EXTENSIONS = [
    '.csv', '.json', '.json.gz', '.parquet', '.parquet.gz', 
    '.parquet.snappy', '.parquet.zst', '.parquet.sz', '.parquet.zstd'
]  # 지원되는 파일 확장자
CSV_SEPARATORS = [',', ';', '\t', '|']  # CSV 구분자
PARQUET_EXTENSIONS = [
    '.parquet', '.parquet.gz', '.parquet.snappy', 
    '.parquet.zst', '.parquet.sz', '.parquet.zstd'
]  # Parquet 파일 확장자

_LOGGER = logging.getLogger(__name__)  # 로거 설정

class BaseFileConnector(BaseConnector):
    """
    파일 파싱 공통 로직을 담은 베이스 클래스
    
    CSV, JSON, Parquet 파일 파싱에 대한 공통 기능을 제공합니다.
    """
    
    def __init__(self, *args, **kwargs):  # 초기화 메서드
        super().__init__(*args, **kwargs)
    
    def get_cost_data_paginated(self, costs_data: List[Dict[str, Any]]) -> Generator[List[Dict[str, Any]], None, None]:
        """
        비용 데이터를 페이지 단위로 분할하여 반환
        
        Args:
            costs_data: 전체 비용 데이터 리스트
            
        Yields:
            List[Dict[str, Any]]: 페이지 단위의 비용 데이터
        """
        page_count = int(len(costs_data) / PAGE_SIZE) + 1  # 페이지 수 계산
        for page_num in range(page_count):
            offset = PAGE_SIZE * page_num  # 페이지 오프셋 계산
            yield costs_data[offset : offset + PAGE_SIZE]  # 페이지 단위로 데이터 반환
    
    @staticmethod
    def validate_dataframe(df: pd.DataFrame, file_path: str) -> None:
        """
        DataFrame 유효성 검증
        
        Args:
            df: 검증할 DataFrame
            file_path: 파일 경로 (오류 메시지용)
            
        Raises:
            ERROR_NO_DATA_FOUND: DataFrame이 비어있는 경우
            ERROR_NO_COLUMNS: 컬럼이 없는 경우
        """
        if df.empty:  # DataFrame이 비어있는 경우
            _LOGGER.error(f"DataFrame is empty after parsing: {file_path}")
            raise ERROR_NO_DATA_FOUND(file_path=file_path)
        
        if len(df.columns) == 0:  # 컬럼이 없는 경우
            _LOGGER.error(f"No columns found in file: {file_path}")
            raise ERROR_NO_COLUMNS(file_path=file_path)
    
    @staticmethod
    def is_json_file(file_path: str) -> bool:
        """
        파일이 JSON 형식인지 확인
        
        Args:
            file_path: 파일 경로 또는 URL
            
        Returns:
            bool: JSON 파일이면 True
        """
        # 파일 확장자 확인
        if file_path.lower().endswith(('.json', '.json.gz')):
            return True
        
        # Content-Type 헤더 확인 (URL인 경우)
        if file_path.startswith(('http://', 'https://')):
            try:
                response = requests.head(file_path, timeout=10)  # HEAD 요청 실행
                content_type = response.headers.get('content-type', '').lower()
                if 'application/json' in content_type or 'text/json' in content_type:  # JSON 형식 확인
                    return True
            except Exception as e:
                _LOGGER.debug(f"HEAD request failed: {e}")
        
        # 파일 내용 확인
        try:
            if file_path.startswith(('http://', 'https://')):
                response = requests.get(file_path, timeout=10)  # GET 요청 실행
                content = response.content.decode('utf-8', errors='ignore').strip()
            else:
                with open(file_path, 'r', encoding='utf-8') as f:  # 파일 읽기
                    content = f.read(100).strip()
            
            if content.startswith('{') or content.startswith('['):  # JSON 형식 확인
                return True
        except Exception as e:
            _LOGGER.debug(f"Content check failed: {e}")
        
        return False
    
    @staticmethod
    def is_parquet_file(file_path: str) -> bool:
        """
        파일이 Parquet 형식인지 확인
        
        Args:
            file_path: 파일 경로 또는 URL
            
        Returns:
            bool: Parquet 파일이면 True
        """
        # 파일 확장자 확인
        for ext in PARQUET_EXTENSIONS:  # Parquet 파일 확장자 확인
            if file_path.lower().endswith(ext):  # 파일 확장자 확인
                return True
        
        # Content-Type 헤더 확인 (URL인 경우)
        if file_path.startswith(('http://', 'https://')):
            try:
                response = requests.head(file_path, timeout=10)  # HEAD 요청 실행
                content_type = response.headers.get('content-type', '').lower()  # Content-Type 헤더 확인
                if 'application/octet-stream' in content_type or 'application/parquet' in content_type:  # Parquet 형식 확인
                    return True
            except Exception as e:
                _LOGGER.debug(f"HEAD request failed: {e}")
        
        return False
    
    @staticmethod
    def detect_csv_encoding(file_path: str) -> str:
        """
        CSV 파일의 인코딩을 자동 감지
        
        Args:
            file_path: CSV 파일 경로 또는 URL
            
        Returns:
            str: 감지된 인코딩 (기본값: 'utf-8')
        """
        try:
            if file_path.startswith(('http://', 'https://')):  # URL인 경우
                response = requests.get(file_path)  # GET 요청 실행
                content = response.content
            else:  # 파일 경로인 경우
                with open(file_path, 'rb') as f:  # 파일 읽기
                    content = f.read()
            
            detected_encoding = chardet.detect(content)  # 인코딩 감지
            
            if detected_encoding is None or detected_encoding.get("encoding") is None:  # 인코딩 감지 실패 시
                _LOGGER.warning("chardet failed to detect encoding, using utf-8 as default")
                return "utf-8"
            
            encoding = detected_encoding["encoding"]  # 감지된 인코딩
            _LOGGER.debug(f"Detected encoding: {encoding}")  # 감지된 인코딩 로깅
            return encoding  # 감지된 인코딩 반환

        except Exception as e:
            _LOGGER.error(f"Encoding detection error: {e}", exc_info=True)
            return "utf-8"  # 기본 인코딩 반환
    
    @staticmethod
    def detect_csv_separator(header_line: str) -> str:
        """
        CSV 구분자를 자동 감지
        
        Args:
            header_line: 헤더 라인
            
        Returns:
            str: 감지된 구분자 (기본값: ',')
        """
        for sep in CSV_SEPARATORS:  # CSV 구분자 확인
            if sep in header_line:  # 구분자 확인
                return sep  # 구분자 반환
        return ','  # 기본 구분자 반환
    
    @staticmethod
    def read_csv_file(file_path: str) -> List[Dict[str, Any]]:
        """
        CSV 파일을 읽어서 파싱
        
        Args:
            file_path: CSV 파일 경로
            
        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
            
        Raises:
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
            ERROR_NO_DATA_ROWS: 데이터 행이 없는 경우
            ERROR_EMPTY_HEADER: 헤더가 비어있는 경우
            ERROR_NO_DATA_FOUND: 파싱 후 데이터가 없는 경우
            ERROR_NO_COLUMNS: 컬럼이 없는 경우
            ERROR_CSV_PARSING: CSV 파싱 오류
        """
        try:
            # 파일 내용 읽기
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()  # 파일 내용 읽기

            if not content:  # 파일 내용이 비어있는 경우
                _LOGGER.error(f"File is empty: {file_path}")
                raise ERROR_EMPTY_FILE(file_path=file_path)  # 파일이 비어있는 경우 오류 발생

            lines = content.split('\n')  # 파일 내용을 줄 단위로 분할
            if len(lines) < 2:  # 줄이 2개 미만인 경우
                _LOGGER.error(f"File has no data rows: {file_path}")  # 줄이 없는 경우 로깅
                raise ERROR_NO_DATA_ROWS(file_path=file_path)  # 줄이 없는 경우 오류 발생

            header_line = lines[0].strip()  # 첫 번째 줄 제거
            if not header_line:  # 헤더 라인이 비어있는 경우
                _LOGGER.error(f"Empty header line: {file_path}")  # 헤더 라인이 비어있는 경우 로깅
                raise ERROR_EMPTY_HEADER(file_path=file_path)  # 헤더 라인이 비어있는 경우 오류 발생

            # 구분자 감지
            detected_sep = BaseFileConnector.detect_csv_separator(header_line)

            # pandas로 CSV 파싱
            df = pd.read_csv(
                file_path,  # 파일 경로
                encoding="utf-8-sig",  # 인코딩
                sep=detected_sep,  # 구분자
                skip_blank_lines=True,  # 빈 줄 건너뛰기
                on_bad_lines='skip'
            )

            # DataFrame 검증
            BaseFileConnector.validate_dataframe(df, file_path)

            # 데이터 변환
            df = df.replace({np.nan: None})  # NaN 값을 None으로 변환
            costs_data = df.to_dict("records")  # DataFrame을 딕셔너리 리스트로 변환

            _LOGGER.info(f"Successfully parsed {len(costs_data)} records from {file_path}")  # 파싱된 데이터 수 로깅
            return costs_data

        except pd.errors.EmptyDataError:
            _LOGGER.error(f"Empty data error for {file_path}")  # 데이터가 비어있는 경우 로깅
            raise ERROR_NO_COLUMNS(file_path=file_path)  # 데이터가 비어있는 경우 오류 발생
        except pd.errors.ParserError as e:
            _LOGGER.error(f"Parser error for {file_path}: {e}")  # 파서 오류 로깅
            raise ERROR_CSV_PARSING(error_message=str(e))  # 파서 오류 오류 발생
        except Exception as e:
            _LOGGER.error(f"CSV read error: {e}", exc_info=True)  # CSV 읽기 오류 로깅
            raise e  # 오류 발생
    
    @staticmethod
    def read_json_file(file_path: str) -> List[Dict[str, Any]]:
        """
        JSON 파일을 읽어서 파싱
        
        Args:
            file_path: JSON 파일 경로
            
        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
            
        Raises:
            Exception: JSON 읽기 실패 시
        """
        try:
            costs_data = []  # 비용 데이터 리스트 초기화

            # gzip 압축 파일 처리
            if file_path.lower().endswith('.json.gz'):
                _LOGGER.debug(f"Processing gzipped JSON file: {file_path}")  # gzip 압축 파일 처리 로깅
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:  # gzip 압축 파일 읽기
                    for line_num, line in enumerate(f, 1):  # 줄 번호 및 줄 내용 반복
                        line = line.strip()  # 줄 내용 제거 공백
                        if line:  # 줄 내용이 비어있지 않은 경우
                            try:
                                record = json.loads(line)  # JSON 파싱
                                costs_data.append(record)  # 비용 데이터 리스트에 추가
                            except json.JSONDecodeError as e:
                                _LOGGER.warning(f"Failed to parse JSON at line {line_num}: {e}")  # JSON 파싱 실패 로깅
                                continue
            else:  # gzip 압축 파일이 아닌 경우
                with open(file_path, 'r', encoding='utf-8') as f:  # 파일 읽기
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()  # 줄 내용 제거 공백
                        if line:  # 줄 내용이 비어있지 않은 경우
                            try:
                                record = json.loads(line)  # JSON 파싱
                                costs_data.append(record)  # 비용 데이터 리스트에 추가
                            except json.JSONDecodeError as e:
                                _LOGGER.warning(f"Failed to parse JSON at line {line_num}: {e}")  # JSON 파싱 실패 로깅
                                continue

            _LOGGER.info(f"Successfully parsed {len(costs_data)} records from {file_path}")  # 파싱된 데이터 수 로깅
            return costs_data

        except Exception as e:
            _LOGGER.error(f"JSON read error: {e}", exc_info=True)
            raise e
    
    @staticmethod
    def read_parquet_file(file_path: str) -> List[Dict[str, Any]]:
        """
        Parquet 파일을 읽어서 파싱
        
        Args:
            file_path: Parquet 파일 경로
            
        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
            
        Raises:
            Exception: Parquet 읽기 실패 시
        """
        try:
            df = None  # DataFrame 초기화

            # pyarrow 엔진으로 읽기 시도
            try:
                df = pd.read_parquet(file_path, engine='pyarrow')  # pyarrow 엔진으로 읽기
                _LOGGER.debug(f"Using pyarrow engine for {file_path}")  # pyarrow 엔진 사용 로깅
            except ImportError:
                # fastparquet 엔진으로 재시도
                try:
                    df = pd.read_parquet(file_path, engine='fastparquet')  # fastparquet 엔진으로 읽기
                    _LOGGER.debug(f"Using fastparquet engine for {file_path}")  # fastparquet 엔진 사용 로깅
                except ImportError:
                    error_msg = "pyarrow or fastparquet library is required to read Parquet files."  # 오류 메시지
                    _LOGGER.error(error_msg)  # 오류 메시지 로깅
                    raise ImportError(error_msg)  # 오류 발생

            if df is None:
                raise Exception("Failed to read parquet file with any available engine")  # Parquet 파일 읽기 실패 시 오류 발생

            # DataFrame 검증
            BaseFileConnector.validate_dataframe(df, file_path)

            # 데이터 변환
            df = df.replace({np.nan: None})  # NaN 값을 None으로 변환
            costs_data = df.to_dict("records")  # DataFrame을 딕셔너리 리스트로 변환

            _LOGGER.info(f"Successfully parsed {len(costs_data)} records from {file_path}")  # 파싱된 데이터 수 로깅
            return costs_data

        except Exception as e:
            _LOGGER.error(f"Parquet read error: {e}", exc_info=True)  # Parquet 읽기 오류 로깅
            raise e  # 오류 발생
    
    @staticmethod
    def parse_cost_file(file_path: str) -> List[Dict[str, Any]]:
        """
        파일 형식을 자동 감지하여 파싱
        
        Args:
            file_path: 파일 경로
            
        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
            
        Raises:
            Exception: 파일 읽기 실패 시
        """
        try:
            file_extension = os.path.splitext(file_path)[1].lower()  # 파일 확장자 확인

            # Parquet 파일 처리
            if file_extension == '.parquet' or any(file_path.lower().endswith(ext) for ext in PARQUET_EXTENSIONS):  # Parquet 파일 처리
                return BaseFileConnector.read_parquet_file(file_path)  # Parquet 파일 읽기

            # JSON 파일 처리
            elif file_extension in ['.json', '.json.gz']:  # JSON 파일 처리
                return BaseFileConnector.read_json_file(file_path)  # JSON 파일 읽기

            # CSV 파일 처리
            else:
                # 첫 번째 줄을 읽어서 JSON 형식인지 확인
                with open(file_path, 'r', encoding='utf-8') as f:  # 파일 읽기
                    first_line = f.readline().strip()  # 첫 번째 줄 읽기

                if first_line.startswith('{') or '"billing_account_id"' in first_line:  # JSON 형식 확인
                    return BaseFileConnector.read_json_file(file_path)  # JSON 파일 읽기
                else:
                    return BaseFileConnector.read_csv_file(file_path)  # CSV 파일 읽기

        except Exception as e:
            _LOGGER.error(f"File parsing error: {e}", exc_info=True)  # 파일 파싱 오류 로깅
            raise e  # 오류 발생
    
    @staticmethod
    def generate_safe_filename(original_name: str) -> str:
        """
        안전한 임시 파일명 생성
        
        Args:
            original_name: 원본 파일명
            
        Returns:
            str: 안전한 임시 파일명
        """
        # 경로 구분자를 언더스코어로 변경
        normalized_name = original_name.replace('/', '_').replace('\\', '_')
        
        # 연속된 언더스코어를 하나로 줄이기
        normalized_name = re.sub(r'_+', '_', normalized_name)
        
        # 안전하지 않은 문자 제거(확장자 보존)
        base_name, extension = os.path.splitext(normalized_name)
        safe_base_name = re.sub(r'[^\w\-_.]', '_', base_name)
        
        # 연속된 언더스코어 다시 하나로 줄이기
        safe_base_name = re.sub(r'_+', '_', safe_base_name)
        
        # 앞뒤 언더스코어 제거
        safe_base_name = safe_base_name.strip('_')
        
        # 빈 파일명이면 기본값 사용
        if not safe_base_name:
            safe_base_name = "billing_data"  # 기본 파일명

        safe_filename = safe_base_name + extension  # 파일명 생성
        
        # 파일명이 너무 길거나 언더스코어 비율이 높으면 해시 적용
        if (len(safe_filename) > MAX_FILENAME_LENGTH or 
            safe_filename.count('_') > len(safe_filename) * UNDERSCORE_RATIO_THRESHOLD):  # 파일명이 너무 길거나 언더스코어 비율이 높으면 해시 적용
            filename_hash = hashlib.md5(original_name.encode()).hexdigest()  # 해시 생성
            file_extension = os.path.splitext(original_name)[1] if '.' in original_name else ''  # 파일 확장자 추출
            safe_filename = f"billing_data_{filename_hash}{file_extension}"  # 파일명 생성
        
        # 최종 파일명이 여전히 너무 길면 더 짧게 해시 적용
        if len(safe_filename) > MAX_FINAL_FILENAME_LENGTH:
            filename_hash = hashlib.md5(original_name.encode()).hexdigest()[:8]  # 해시 생성
            file_extension = os.path.splitext(original_name)[1] if '.' in original_name else ''  # 파일 확장자 추출
            safe_filename = f"billing_{filename_hash}{file_extension}"  # 파일명 생성
        
        return safe_filename
    
    @staticmethod
    def cleanup_temp_file(temp_file_path: str) -> None:
        """
        임시 파일 정리
        
        Args:
            temp_file_path: 삭제할 임시 파일 경로
        """
        try:
            if os.path.exists(temp_file_path):  # 임시 파일 경로가 존재하는 경우
                os.remove(temp_file_path)  # 임시 파일 삭제
                _LOGGER.debug(f"Successfully cleaned up temporary file: {temp_file_path}")  # 임시 파일 삭제 로깅
        except Exception as e:
            _LOGGER.warning(f"Failed to clean up temporary file {temp_file_path}: {e}")  # 임시 파일 삭제 실패 로깅
    
    @staticmethod
    def download_file_from_url(url: str, timeout: int = 30) -> bytes:
        """
        URL에서 파일을 다운로드
        
        Args:
            url: 파일 URL
            timeout: 타임아웃 시간 (초)
            
        Returns:
            bytes: 다운로드된 파일 내용
            
        Raises:
            ERROR_FILE_DOWNLOAD_FAILED: 파일 다운로드 실패 시
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
        """
        try:
            response = requests.get(url, timeout=timeout)  # GET 요청 실행
            response.raise_for_status()  # 요청 상태 확인
            
            content_length = len(response.content)  # 파일 내용 길이 확인
            if content_length == 0:  # 파일 내용이 비어있는 경우
                _LOGGER.error(f"File is empty (content length 0): {url}")  # 파일이 비어있는 경우 로깅
                raise ERROR_EMPTY_FILE(file_path=url)  # 파일이 비어있는 경우 오류 발생
            
            if not response.content.strip():  # 파일 내용이 비어있는 경우
                _LOGGER.error(f"File is empty (no content after strip): {url}")  # 파일이 비어있는 경우 로깅
                raise ERROR_EMPTY_FILE(file_path=url)  # 파일이 비어있는 경우 오류 발생
            
            return response.content  # 파일 내용 반환
            
        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Failed to download file from {url}: {e}")  # 파일 다운로드 실패 로깅
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=url)  # 파일 다운로드 실패 오류 발생
