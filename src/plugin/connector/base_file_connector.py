# 파일 파싱 공통 로직을 담은 베이스 클래스
import gzip
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, Generator, List

import chardet
import numpy as np
import pandas as pd
import requests
from spaceone.core.connector import BaseConnector

from plugin.error.cost import (
    ERROR_CSV_PARSING,  # CSV 파싱 오류
    ERROR_EMPTY_FILE,  # 파일이 비어있는 경우
    ERROR_EMPTY_HEADER,  # 헤더가 비어있는 경우
    ERROR_FILE_DOWNLOAD_FAILED,  # 파일 다운로드 실패
    ERROR_NO_COLUMNS,  # 컬럼이 없는 경우
    ERROR_NO_DATA_FOUND,  # 파싱 후 데이터가 없는 경우
    ERROR_NO_DATA_ROWS,  # 데이터 행이 없는 경우
)
from plugin.validation.payload_validator import PayloadValidator

# 공통 상수 정의
PAGE_SIZE = 1000  # 페이지 크기
MIN_FILE_SIZE = 50  # 최소 파일 크기
MAX_FILENAME_LENGTH = 100  # 최대 파일명 길이
MAX_FINAL_FILENAME_LENGTH = 150  # 최종 파일명 길이
UNDERSCORE_RATIO_THRESHOLD = 0.3  # 언더스코어 비율 임계값
SUPPORTED_EXTENSIONS = [
    ".csv",
    ".json",
    ".json.gz",
    ".parquet",
    ".parquet.gz",
    ".parquet.snappy",
    ".parquet.zst",
    ".parquet.sz",
    ".parquet.zstd",
]  # 지원되는 파일 확장자
CSV_SEPARATORS = [",", ";", "\t", "|"]  # CSV 구분자
PARQUET_EXTENSIONS = [
    ".parquet",
    ".parquet.gz",
    ".parquet.snappy",
    ".parquet.zst",
    ".parquet.sz",
    ".parquet.zstd",
]  # Parquet 파일 확장자

_LOGGER = logging.getLogger(__name__)  # 로거 설정


def convert_numpy_types(obj):
    """
    numpy 및 pandas 타입을 Python 기본 타입으로 변환하는 재귀 함수

    Args:
        obj: 변환할 객체 (dict, list, numpy/pandas 타입 등)

    Returns:
        Python 기본 타입으로 변환된 객체
    """
    if isinstance(obj, np.ndarray):
        # numpy 배열을 리스트로 변환
        return [convert_numpy_types(item) for item in obj.tolist()]
    elif isinstance(obj, (np.integer, np.floating)):
        # numpy 숫자 타입을 Python 기본 타입으로 변환
        return obj.item()
    elif isinstance(obj, np.bool_):
        # numpy bool을 Python bool로 변환
        return bool(obj)
    elif isinstance(obj, pd.Timestamp):
        # pandas Timestamp를 문자열로 변환
        return str(obj)
    elif hasattr(obj, "to_pydatetime"):
        # pandas datetime 객체를 Python datetime으로 변환 후 문자열로 변환
        return str(obj.to_pydatetime())
    elif isinstance(obj, dict):
        # 딕셔너리의 모든 값에 대해 재귀적으로 변환
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        # 리스트의 모든 요소에 대해 재귀적으로 변환
        return [convert_numpy_types(item) for item in obj]
    elif pd.isna(obj):
        # pandas NaN을 None으로 변환
        return None
    else:
        # 기타 타입은 그대로 반환
        return obj


class BaseFileConnector(BaseConnector):
    """
    파일 파싱 공통 로직을 담은 베이스 클래스

    CSV, JSON, Parquet 파일 파싱에 대한 공통 기능을 제공합니다.
    """

    def __init__(self, *args, **kwargs):  # 초기화 메서드
        super().__init__(*args, **kwargs)

    def get_cost_data_paginated(
        self, costs_data: List[Dict[str, Any]]
    ) -> Generator[List[Dict[str, Any]], None, None]:
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
        if file_path.lower().endswith((".json", ".json.gz")):
            return True

        # Content-Type 헤더 확인 (URL인 경우)
        if file_path.startswith(("http://", "https://")):
            try:
                response = requests.head(
                    file_path, timeout=None
                )  # HEAD 요청 실행 (timeout 제거)
                content_type = response.headers.get("content-type", "").lower()
                if (
                    "application/json" in content_type or "text/json" in content_type
                ):  # JSON 형식 확인
                    return True
            except Exception as e:
                _LOGGER.debug(f"HEAD request failed: {e}")

        # 파일 내용 확인
        try:
            if file_path.startswith(("http://", "https://")):
                response = requests.get(
                    file_path, timeout=None
                )  # GET 요청 실행 (timeout 제거)
                content = response.content.decode("utf-8", errors="ignore").strip()
            else:
                with open(file_path, encoding="utf-8") as f:  # 파일 읽기
                    content = f.read(100).strip()

            if content.startswith("{") or content.startswith("["):  # JSON 형식 확인
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
        if file_path.startswith(("http://", "https://")):
            try:
                response = requests.head(
                    file_path, timeout=None
                )  # HEAD 요청 실행 (timeout 제거)
                content_type = response.headers.get(
                    "content-type", ""
                ).lower()  # Content-Type 헤더 확인
                if (
                    "application/octet-stream" in content_type
                    or "application/parquet" in content_type
                ):  # Parquet 형식 확인
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
            if file_path.startswith(("http://", "https://")):  # URL인 경우
                response = requests.get(file_path)  # GET 요청 실행
                content = response.content
            else:  # 파일 경로인 경우
                with open(file_path, "rb") as f:  # 파일 읽기
                    content = f.read()

            detected_encoding = chardet.detect(content)  # 인코딩 감지

            if (
                detected_encoding is None or detected_encoding.get("encoding") is None
            ):  # 인코딩 감지 실패 시
                _LOGGER.warning(
                    "chardet failed to detect encoding, using utf-8 as default"
                )
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
        return ","  # 기본 구분자 반환

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
            # 인코딩 감지 시도
            detected_encoding = "utf-8"
            try:
                import chardet

                with open(file_path, "rb") as f:
                    raw_data = f.read(1024)
                detected = chardet.detect(raw_data)
                if detected.get("encoding"):
                    detected_encoding = detected["encoding"]
                    _LOGGER.debug(
                        f"Detected encoding for CSV file {file_path}: {detected_encoding}"
                    )
            except Exception:
                pass  # 감지 실패시 utf-8 사용

            # 파일 내용 읽기 (여러 인코딩 시도)
            content = None

            for encoding in [
                detected_encoding,
                "utf-8",
                "latin-1",
                "cp1252",
                "iso-8859-1",
            ]:
                try:
                    with open(file_path, encoding=encoding) as f:
                        content = f.read().strip()  # 파일 내용 읽기

                    _LOGGER.debug(
                        f"Successfully read CSV file with {encoding} encoding: {file_path}"
                    )
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                _LOGGER.error(f"Failed to read CSV file with any encoding: {file_path}")
                raise ERROR_CSV_PARSING(message=f"Could not decode file: {file_path}")

            if not content:  # 파일 내용이 비어있는 경우
                _LOGGER.error(f"File is empty: {file_path}")
                raise ERROR_EMPTY_FILE(
                    file_path=file_path
                )  # 파일이 비어있는 경우 오류 발생

            lines = content.split("\n")  # 파일 내용을 줄 단위로 분할
            if len(lines) < 2:  # 줄이 2개 미만인 경우
                _LOGGER.error(
                    f"File has no data rows: {file_path}"
                )  # 줄이 없는 경우 로깅
                raise ERROR_NO_DATA_ROWS(
                    file_path=file_path
                )  # 줄이 없는 경우 오류 발생

            header_line = lines[0].strip()  # 첫 번째 줄 제거
            if not header_line:  # 헤더 라인이 비어있는 경우
                _LOGGER.error(
                    f"Empty header line: {file_path}"
                )  # 헤더 라인이 비어있는 경우 로깅
                raise ERROR_EMPTY_HEADER(
                    file_path=file_path
                )  # 헤더 라인이 비어있는 경우 오류 발생

            # 구분자 감지
            detected_sep = BaseFileConnector.detect_csv_separator(header_line)

            # pandas로 CSV 파싱
            df = pd.read_csv(
                file_path,  # 파일 경로
                encoding="utf-8-sig",  # 인코딩
                sep=detected_sep,  # 구분자
                skip_blank_lines=True,  # 빈 줄 건너뛰기
                on_bad_lines="skip",
            )

            # DataFrame 검증
            BaseFileConnector.validate_dataframe(df, file_path)

            # 데이터 변환
            df = df.replace({np.nan: None})  # NaN 값을 None으로 변환
            costs_data = df.to_dict("records")  # DataFrame을 딕셔너리 리스트로 변환

            # numpy 타입을 Python 기본 타입으로 변환
            costs_data = [convert_numpy_types(record) for record in costs_data]

            # 🔥 최종 보안: 모든 비딕셔너리 데이터 완전 제거
            # 딕셔너리가 아닌 데이터 필터링
            costs_data = [record for record in costs_data if isinstance(record, dict)]

            _LOGGER.info(
                f"Successfully parsed {len(costs_data)} records from {file_path}"
            )  # 파싱된 데이터 수 로깅
            return costs_data

        except pd.errors.EmptyDataError as e:
            _LOGGER.error(
                f"Empty data error for {file_path}"
            )  # 데이터가 비어있는 경우 로깅
            raise ERROR_NO_COLUMNS(
                file_path=file_path
            ) from e  # 데이터가 비어있는 경우 오류 발생
        except pd.errors.ParserError as e:
            _LOGGER.error(f"Parser error for {file_path}: {e}")  # 파서 오류 로깅
            raise ERROR_CSV_PARSING(error_message=str(e)) from e  # 파서 오류 오류 발생
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
            if file_path.lower().endswith(".json.gz"):
                start_time = time.time()
                line_count = 0
                processed_count = 0
                file_size = os.path.getsize(file_path)

                _LOGGER.info(
                    f"Processing gzipped JSON file: {file_path} (Compressed size: {file_size / 1024 / 1024:.2f} MB)"
                )

                try:
                    with gzip.open(
                        file_path, "rt", encoding="utf-8"
                    ) as f:  # gzip 압축 파일 읽기
                        for line in f:  # 줄 내용 반복
                            line_count += 1
                            line = line.strip()  # 줄 내용 제거 공백

                            # 대용량 파일 진행 상황 로깅 (10000줄마다로 조정하여 성능 향상)
                            if line_count % 10000 == 0:
                                elapsed = time.time() - start_time
                                rate = processed_count / elapsed if elapsed > 0 else 0
                                _LOGGER.info(
                                    f"📊 Processing line {line_count:,}, parsed {processed_count:,} records "
                                    f"({elapsed:.1f}s, {rate:.0f} records/sec)"
                                )

                            if line:  # 줄 내용이 비어있지 않은 경우
                                try:
                                    record = json.loads(line)  # JSON 파싱
                                    # 딕셔너리 타입 검증 강화
                                    if isinstance(record, dict):
                                        costs_data.append(
                                            record
                                        )  # 비용 데이터 리스트에 추가
                                        processed_count += 1
                                    else:
                                        # 모든 비딕셔너리 데이터를 자세히 로깅
                                        _LOGGER.error(
                                            f"CRITICAL: Found non-dict data in JSON at line {line_count}: {type(record).__name__} = {repr(record)[:200]}"
                                        )
                                        # 통계 카운트 (모든 비딕셔너리 데이터)
                                        if line_count % 1000 == 0:
                                            _LOGGER.info(
                                                f"Found {line_count - processed_count} non-dict records so far"
                                            )
                                except json.JSONDecodeError as e:
                                    if line_count <= 10:  # 처음 10줄만 경고 표시
                                        _LOGGER.warning(
                                            f"Failed to parse JSON at line {line_count}: {e}"
                                        )  # JSON 파싱 실패 로깅
                                    continue

                    elapsed_time = time.time() - start_time
                    _LOGGER.info(
                        f"Completed gzip processing {processed_count} records from {line_count} lines ({elapsed_time:.2f}s)"
                    )

                except UnicodeDecodeError as e:
                    _LOGGER.error(
                        f"UTF-8 decode error for gzipped JSON file {file_path}: {e}"
                    )
                    # gzip 파일도 다른 인코딩 시도
                    for fallback_encoding in ["latin-1", "cp1252", "iso-8859-1"]:
                        try:
                            _LOGGER.debug(
                                f"Trying fallback encoding {fallback_encoding} for gzipped file {file_path}"
                            )
                            with gzip.open(
                                file_path, "rt", encoding=fallback_encoding
                            ) as f:
                                costs_data = []
                                for line_num, line in enumerate(f, 1):
                                    line = line.strip()
                                    if line:
                                        try:
                                            record = json.loads(line)
                                            # 딕셔너리 타입 검증 추가
                                            if isinstance(record, dict):
                                                costs_data.append(record)
                                            else:
                                                _LOGGER.error(
                                                    f"CRITICAL: Non-dict in gzipped file at line {line_num}: {type(record).__name__} = {repr(record)[:200]}"
                                                )
                                        except json.JSONDecodeError:
                                            continue
                            _LOGGER.info(
                                f"Successfully read gzipped JSON file with {fallback_encoding} encoding: {file_path}"
                            )
                            break
                        except Exception:
                            continue
                    else:
                        raise e
            else:  # gzip 압축 파일이 아닌 경우
                # 인코딩 감지 시도
                detected_encoding = "utf-8"
                try:
                    import chardet

                    with open(file_path, "rb") as f:
                        raw_data = f.read(1024)
                    detected = chardet.detect(raw_data)
                    if detected.get("encoding"):
                        detected_encoding = detected["encoding"]
                        _LOGGER.debug(
                            f"Detected encoding for JSON file {file_path}: {detected_encoding}"
                        )
                except Exception:
                    pass  # 감지 실패시 utf-8 사용

                try:
                    start_time = time.time()
                    line_count = 0
                    processed_count = 0
                    file_size = os.path.getsize(file_path)

                    _LOGGER.info(
                        f"Processing JSON file: {file_path} (Size: {file_size / 1024 / 1024:.2f} MB)"
                    )

                    with open(
                        file_path, encoding=detected_encoding
                    ) as f:  # 감지된 인코딩으로 파일 읽기
                        for line in f:
                            line_count += 1
                            line = line.strip()  # 줄 내용 제거 공백

                            # 대용량 파일 진행 상황 로깅 (10000줄마다로 조정하여 성능 향상)
                            if line_count % 10000 == 0:
                                elapsed = time.time() - start_time
                                rate = processed_count / elapsed if elapsed > 0 else 0
                                _LOGGER.info(
                                    f"📊 Processing line {line_count:,}, parsed {processed_count:,} records "
                                    f"({elapsed:.1f}s, {rate:.0f} records/sec)"
                                )

                            if line:  # 줄 내용이 비어있지 않은 경우
                                try:
                                    record = json.loads(line)  # JSON 파싱
                                    # 딕셔너리 타입 검증 강화
                                    if isinstance(record, dict):
                                        costs_data.append(
                                            record
                                        )  # 비용 데이터 리스트에 추가
                                        processed_count += 1
                                    else:
                                        # 모든 비딕셔너리 데이터를 자세히 로깅
                                        _LOGGER.error(
                                            f"CRITICAL: Found non-dict data in JSON at line {line_count}: {type(record).__name__} = {repr(record)[:200]}"
                                        )
                                        # 통계 카운트 (모든 비딕셔너리 데이터)
                                        if line_count % 1000 == 0:
                                            _LOGGER.info(
                                                f"Found {line_count - processed_count} non-dict records so far"
                                            )
                                except json.JSONDecodeError as e:
                                    if line_count <= 10:  # 처음 10줄만 경고 표시
                                        _LOGGER.warning(
                                            f"Failed to parse JSON at line {line_count}: {e}"
                                        )  # JSON 파싱 실패 로깅
                                    continue

                    elapsed_time = time.time() - start_time
                    avg_rate = processed_count / elapsed_time if elapsed_time > 0 else 0
                    _LOGGER.info(
                        f"✅ Completed processing {processed_count:,} records from {line_count:,} lines "
                        f"({elapsed_time:.2f}s, average {avg_rate:.0f} records/sec)"
                    )
                except UnicodeDecodeError as e:
                    _LOGGER.error(f"UTF-8 decode error for JSON file {file_path}: {e}")
                    # 폴백 인코딩들 시도
                    for fallback_encoding in ["latin-1", "cp1252", "iso-8859-1"]:
                        try:
                            _LOGGER.debug(
                                f"Trying fallback encoding {fallback_encoding} for {file_path}"
                            )
                            with open(file_path, encoding=fallback_encoding) as f:
                                for line_num, line in enumerate(f, 1):
                                    line = line.strip()
                                    if line:
                                        try:
                                            record = json.loads(line)
                                            costs_data.append(record)
                                        except json.JSONDecodeError as e:
                                            _LOGGER.warning(
                                                f"Failed to parse JSON at line {line_num} with {fallback_encoding}: {e}"
                                            )
                                            continue
                            _LOGGER.info(
                                f"Successfully read JSON file with {fallback_encoding} encoding: {file_path}"
                            )
                            break  # 성공한 인코딩이 있으면 중단
                        except Exception:
                            continue  # 다음 인코딩 시도
                    else:
                        # 모든 인코딩이 실패한 경우
                        _LOGGER.error(
                            f"All encoding attempts failed for JSON file: {file_path}"
                        )
                        raise e  # 원래 오류 다시 발생

            # numpy 타입을 Python 기본 타입으로 변환 (안전성을 위해)
            costs_data = [convert_numpy_types(record) for record in costs_data]

            # 🔥 최종 보안: 모든 비딕셔너리 데이터 완전 제거
            # 딕셔너리가 아닌 데이터 필터링
            costs_data = [record for record in costs_data if isinstance(record, dict)]

            _LOGGER.info(
                f"Successfully parsed {len(costs_data)} records from {file_path}"
            )  # 파싱된 데이터 수 로깅
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
                df = pd.read_parquet(
                    file_path, engine="pyarrow"
                )  # pyarrow 엔진으로 읽기
                _LOGGER.debug(
                    f"Using pyarrow engine for {file_path}"
                )  # pyarrow 엔진 사용 로깅
            except ImportError:
                # fastparquet 엔진으로 재시도
                try:
                    df = pd.read_parquet(
                        file_path, engine="fastparquet"
                    )  # fastparquet 엔진으로 읽기
                    _LOGGER.debug(
                        f"Using fastparquet engine for {file_path}"
                    )  # fastparquet 엔진 사용 로깅
                except ImportError:
                    error_msg = "pyarrow or fastparquet library is required to read Parquet files."  # 오류 메시지
                    _LOGGER.error(error_msg)  # 오류 메시지 로깅
                    raise ImportError(error_msg) from None  # 오류 발생

            if df is None:
                raise Exception(
                    "Failed to read parquet file with any available engine"
                )  # Parquet 파일 읽기 실패 시 오류 발생

            # DataFrame 검증
            BaseFileConnector.validate_dataframe(df, file_path)

            # 데이터 변환
            df = df.replace({np.nan: None})  # NaN 값을 None으로 변환
            costs_data = df.to_dict("records")  # DataFrame을 딕셔너리 리스트로 변환

            # numpy 타입을 Python 기본 타입으로 변환
            costs_data = [convert_numpy_types(record) for record in costs_data]

            # 🔥 최종 보안: 모든 비딕셔너리 데이터 완전 제거
            # 딕셔너리가 아닌 데이터 필터링
            costs_data = [record for record in costs_data if isinstance(record, dict)]

            _LOGGER.info(
                f"Successfully parsed {len(costs_data)} records from {file_path}"
            )  # 파싱된 데이터 수 로깅
            return costs_data

        except Exception as e:
            _LOGGER.error(
                f"Parquet read error: {e}", exc_info=True
            )  # Parquet 읽기 오류 로깅
            raise e  # 오류 발생

    @staticmethod
    def parse_cost_file(file_path: str) -> List[Dict[str, Any]]:
        """
        파일 형식을 자동 감지하여 파싱 (강화된 인코딩 및 파일 타입 감지)

        Args:
            file_path: 파일 경로

        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트

        Raises:
            Exception: 파일 읽기 실패 시
        """
        try:
            _LOGGER.info(f"Starting enhanced file parsing: {file_path}")

            # 1단계: 바이너리 매직 넘버로 파일 타입 감지
            try:
                with open(file_path, "rb") as f:
                    header = f.read(16)

                _LOGGER.debug(f"File header bytes: {header[:8].hex()}")

                # Parquet 매직 넘버 확인 (PAR1)
                if header.startswith(b"PAR1") or b"PAR1" in header[:8]:
                    _LOGGER.info(f"Detected Parquet file by magic number: {file_path}")
                    return BaseFileConnector.read_parquet_file(file_path)

                # gzip 매직 넘버 확인 (1f 8b)
                if header.startswith(b"\x1f\x8b"):
                    _LOGGER.info(f"Detected gzip compressed file: {file_path}")
                    return BaseFileConnector._handle_gzip_compressed_file(file_path)

            except Exception as header_error:
                _LOGGER.warning(f"Failed to read file header: {header_error}")

            # 2단계: 파일 확장자 기반 판별
            file_extension = os.path.splitext(file_path)[1].lower()

            # Parquet 확장자 확인
            if file_extension == ".parquet" or any(
                file_path.lower().endswith(ext) for ext in PARQUET_EXTENSIONS
            ):
                _LOGGER.info(f"Processing as Parquet by extension: {file_path}")
                return BaseFileConnector.read_parquet_file(file_path)

            # JSON 확장자 확인
            if file_extension in [".json", ".json.gz"]:
                _LOGGER.info(f"Processing as JSON by extension: {file_path}")
                return BaseFileConnector.read_json_file(file_path)

            # 3단계: 텍스트 파일 내용 감지 (안전한 인코딩 처리)
            return BaseFileConnector._detect_text_file_type(file_path)

        except Exception as e:
            _LOGGER.error(f"File parsing error for {file_path}: {e}", exc_info=True)
            # 개별 파일 오류는 전체 처리를 중단하지 않음
            _LOGGER.warning(f"Skipping problematic file: {file_path}")
            return []

    @staticmethod
    def _handle_gzip_compressed_file(file_path: str) -> List[Dict[str, Any]]:
        """
        gzip 압축 파일 처리

        Args:
            file_path: gzip 파일 경로

        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
        """
        import gzip
        import tempfile

        try:
            # gzip 파일 압축 해제
            with gzip.open(file_path, "rb") as gz_file:
                decompressed_data = gz_file.read()

            # 임시 파일에 압축 해제된 데이터 저장
            with tempfile.NamedTemporaryFile(
                mode="wb", delete=False, suffix=".tmp"
            ) as temp_file:
                temp_file.write(decompressed_data)
                temp_path = temp_file.name

            try:
                # 압축 해제된 파일을 다시 파싱
                _LOGGER.info(f"Processing decompressed file: {file_path}")
                result = BaseFileConnector.parse_cost_file(temp_path)
                return result
            finally:
                # 임시 파일 정리
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

        except Exception as e:
            _LOGGER.error(f"Failed to handle gzip file {file_path}: {e}")
            return []

    @staticmethod
    def _detect_text_file_type(file_path: str) -> List[Dict[str, Any]]:
        """
        텍스트 파일 타입 감지 및 처리 (강력한 인코딩 지원)

        Args:
            file_path: 텍스트 파일 경로

        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
        """
        try:
            # 인코딩 감지
            import chardet

            with open(file_path, "rb") as f:
                raw_sample = f.read(2048)  # 더 큰 샘플로 정확한 감지

            detected = chardet.detect(raw_sample)
            primary_encoding = detected.get("encoding", "utf-8")
            confidence = detected.get("confidence", 0)

            _LOGGER.debug(
                f"Detected encoding: {primary_encoding} (confidence: {confidence})"
            )

            # 시도할 인코딩 리스트 (감지된 인코딩을 우선순위로)
            encodings_to_try = [
                primary_encoding,
                "utf-8",
                "latin-1",
                "cp1252",
                "iso-8859-1",
            ]

            # 중복 제거
            encodings_to_try = list(dict.fromkeys(filter(None, encodings_to_try)))

            first_line = None

            # 각 인코딩으로 파일 읽기 시도
            for encoding in encodings_to_try:
                try:
                    with open(file_path, encoding=encoding) as f:
                        first_line = f.readline().strip()
                    _LOGGER.debug(f"Successfully read with {encoding}: {file_path}")
                    break
                except UnicodeDecodeError:
                    _LOGGER.debug(f"Failed to read with {encoding}: {file_path}")
                    continue

            if first_line is None:
                _LOGGER.error(f"Could not read file with any encoding: {file_path}")
                # 마지막 시도: Parquet으로 처리
                _LOGGER.info(f"Attempting Parquet parsing as fallback: {file_path}")
                return BaseFileConnector.read_parquet_file(file_path)

            # 파일 내용 기반 타입 결정
            if first_line.startswith("{") or '"billing_account_id"' in first_line:
                _LOGGER.info(f"Detected JSON content: {file_path}")
                return BaseFileConnector.read_json_file(file_path)
            else:
                _LOGGER.info(f"Detected CSV content: {file_path}")
                return BaseFileConnector.read_csv_file(file_path)

        except Exception as e:
            _LOGGER.error(f"Text file detection failed for {file_path}: {e}")
            # 최후의 수단: Parquet 시도
            try:
                _LOGGER.info(f"Final fallback to Parquet: {file_path}")
                return BaseFileConnector.read_parquet_file(file_path)
            except Exception:
                _LOGGER.error(f"All parsing attempts failed for: {file_path}")
                return []

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
        normalized_name = original_name.replace("/", "_").replace("\\", "_")

        # 연속된 언더스코어를 하나로 줄이기
        normalized_name = re.sub(r"_+", "_", normalized_name)

        # 안전하지 않은 문자 제거(확장자 보존)
        base_name, extension = os.path.splitext(normalized_name)
        safe_base_name = re.sub(r"[^\w\-_.]", "_", base_name)

        # 연속된 언더스코어 다시 하나로 줄이기
        safe_base_name = re.sub(r"_+", "_", safe_base_name)

        # 앞뒤 언더스코어 제거
        safe_base_name = safe_base_name.strip("_")

        # 빈 파일명이면 기본값 사용
        if not safe_base_name:
            safe_base_name = "billing_data"  # 기본 파일명

        safe_filename = safe_base_name + extension  # 파일명 생성

        # 파일명이 너무 길거나 언더스코어 비율이 높으면 해시 적용
        if (
            len(safe_filename) > MAX_FILENAME_LENGTH
            or safe_filename.count("_")
            > len(safe_filename) * UNDERSCORE_RATIO_THRESHOLD
        ):  # 파일명이 너무 길거나 언더스코어 비율이 높으면 해시 적용
            filename_hash = hashlib.md5(original_name.encode()).hexdigest()  # 해시 생성
            file_extension = (
                os.path.splitext(original_name)[1] if "." in original_name else ""
            )  # 파일 확장자 추출
            safe_filename = (
                f"billing_data_{filename_hash}{file_extension}"  # 파일명 생성
            )

        # 최종 파일명이 여전히 너무 길면 더 짧게 해시 적용
        if len(safe_filename) > MAX_FINAL_FILENAME_LENGTH:
            filename_hash = hashlib.md5(original_name.encode()).hexdigest()[
                :8
            ]  # 해시 생성
            file_extension = (
                os.path.splitext(original_name)[1] if "." in original_name else ""
            )  # 파일 확장자 추출
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
                _LOGGER.debug(
                    f"Successfully cleaned up temporary file: {temp_file_path}"
                )  # 임시 파일 삭제 로깅
        except Exception as e:
            _LOGGER.warning(
                f"Failed to clean up temporary file {temp_file_path}: {e}"
            )  # 임시 파일 삭제 실패 로깅

    @staticmethod
    def download_file_from_url(url: str, timeout: int = None) -> bytes:
        """
        URL에서 파일을 다운로드 (보안 강화)

        Args:
            url: 파일 URL
            timeout: 타임아웃 시간 (초, None이면 기본값 30초 사용)

        Returns:
            bytes: 다운로드된 파일 내용

        Raises:
            ERROR_FILE_DOWNLOAD_FAILED: 파일 다운로드 실패 시
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
        """
        # URL 검증
        try:
            validated_url = PayloadValidator._validate_single_url(url)
        except Exception as e:
            _LOGGER.error(f"URL 검증 실패: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=url) from e

        # 기본 타임아웃 설정 (보안 강화)
        if timeout is None:
            timeout = 30  # 기본 30초 타임아웃
        elif timeout > 300:  # 최대 5분 제한
            timeout = 300

        try:
            # 보안 강화: User-Agent 설정 및 스트리밍 다운로드
            headers = {"User-Agent": "SpaceONE-HTTP-File-Cost-DataSource/1.1.21"}

            response = requests.get(
                validated_url,
                timeout=timeout,
                headers=headers,
                stream=True,  # 스트리밍 다운로드로 메모리 효율성 향상
            )
            response.raise_for_status()  # 요청 상태 확인

            # Content-Length 헤더로 파일 크기 사전 확인
            content_length = response.headers.get("content-length")
            if content_length:
                content_length = int(content_length)
                if content_length > PayloadValidator.MAX_FILE_SIZE:
                    raise ERROR_FILE_DOWNLOAD_FAILED(file_path=validated_url)
                if content_length == 0:
                    raise ERROR_EMPTY_FILE(file_path=validated_url)

            # 실제 콘텐츠를 청크 단위로 다운로드하며 크기 제한
            content = b""
            downloaded_size = 0

            for chunk in response.iter_content(chunk_size=8192):  # 8KB 청크
                if chunk:  # 빈 청크 필터링
                    downloaded_size += len(chunk)

                    # 다운로드 중 파일 크기 제한 확인
                    if downloaded_size > PayloadValidator.MAX_FILE_SIZE:
                        raise ERROR_FILE_DOWNLOAD_FAILED(file_path=validated_url)

                    content += chunk

            # 다운로드 완료 후 검증
            if len(content) == 0:
                _LOGGER.error(
                    f"파일이 비어있습니다 (content length 0): {validated_url}"
                )
                raise ERROR_EMPTY_FILE(file_path=validated_url)

            if not content.strip():
                _LOGGER.error(
                    f"파일이 비어있습니다 (no content after strip): {validated_url}"
                )
                raise ERROR_EMPTY_FILE(file_path=validated_url)

            _LOGGER.info(f"파일 다운로드 완료: {validated_url} ({len(content)} bytes)")
            return content

        except requests.exceptions.Timeout as e:
            _LOGGER.error(
                f"파일 다운로드 타임아웃: {validated_url} (timeout: {timeout}s)"
            )
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=validated_url) from e
        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"파일 다운로드 실패: {validated_url}: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=validated_url) from e

    def _ensure_only_dict_records_final(
        self, costs_data: list, source_file: str
    ) -> list:
        """
        🔥 최종 보안: BaseFileConnector에서 모든 비딕셔너리 데이터를 완전 제거

        이 함수는 모든 파일 파싱 메서드의 최종 단계에서 실행되어
        'int' object has no attribute 'keys' 오류를 완전히 방지합니다.

        Args:
            costs_data (list): 파싱된 원본 데이터 리스트
            source_file (str): 소스 파일명 (로깅용)

        Returns:
            list: 딕셔너리만 포함된 완전 정제된 데이터 리스트
        """
        if not costs_data:
            return []

        original_count = len(costs_data)
        filtered_data = []
        non_dict_count = 0
        non_dict_types = {}

        for idx, record in enumerate(costs_data):
            if isinstance(record, dict) and record:  # 딕셔너리이며 비어있지 않은 경우
                filtered_data.append(record)
            else:
                # 비딕셔너리 또는 빈 딕셔너리는 완전 차단
                non_dict_count += 1
                type_name = type(record).__name__ if record else "empty_dict"
                non_dict_types[type_name] = non_dict_types.get(type_name, 0) + 1

                # 상세 로깅 (처음 3개만)
                if non_dict_count <= 3:
                    _LOGGER.error(
                        f"🛡️ FINAL FILTER: Removed non-dict in {source_file} at index {idx}: "
                        f"{type_name} = {repr(record)[:100]}"
                    )

        # 정제 결과 로깅
        if non_dict_count > 0:
            _LOGGER.warning(
                f"🛡️ FINAL SECURITY FILTER applied to {source_file}: "
                f"Removed {non_dict_count}/{original_count} invalid records. "
                f"Types removed: {non_dict_types}"
            )

        filtered_count = len(filtered_data)
        _LOGGER.info(
            f"🛡️ Final security check complete for {source_file}: "
            f"{filtered_count}/{original_count} valid dict records secured"
        )

        return filtered_data
