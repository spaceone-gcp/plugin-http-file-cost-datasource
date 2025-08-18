import logging
import os
import tempfile
import gzip
from typing import List, Dict, Generator, Any

import google.oauth2.service_account
import numpy as np
import pandas as pd
from google.cloud import storage

from plugin.error.cost import (
    ERROR_EMPTY_FILE,
    ERROR_NO_DATA_ROWS,
    ERROR_EMPTY_HEADER,
    ERROR_NO_DATA_FOUND,
    ERROR_NO_COLUMNS,
    ERROR_CSV_PARSING,
    ERROR_FILE_DOWNLOAD_FAILED,
    ERROR_REQUIRED_PARAMETER
)
from spaceone.core.connector import BaseConnector
from spaceone.core.error import ERROR_UNKNOWN

# 상수 정의
_PAGE_SIZE = 1000  # 페이지 크기
_MIN_FILE_SIZE = 50  # 최소 파일 크기 (바이트)
_MAX_FILENAME_LENGTH = 100  # 최대 파일명 길이
_MAX_FINAL_FILENAME_LENGTH = 150  # 최종 파일명 최대 길이
_UNDERSCORE_RATIO_THRESHOLD = 0.3  # 언더스코어 비율 임계값
_SUPPORTED_EXTENSIONS = ['.csv', '.json', '.json.gz', '.parquet', '.parquet.gz', '.parquet.snappy', '.parquet.zst', '.parquet.sz', '.parquet.zstd']  # 지원되는 파일 확장자
_CSV_SEPARATORS = [',', ';', '\t', '|']  # CSV 구분자 목록
_LOGGER = logging.getLogger("spaceone")  # 로거 설정

class GoogleStorageConnector(BaseConnector):
    """
    Google Cloud Storage에서 비용 데이터를 수집하는 커넥터
    
    Google Cloud Storage 버킷에 저장된 CSV/JSON 형태의 비용 데이터를
    다운로드하고 파싱하여 비용 정보를 추출합니다.
    """
    google_client_service = "storage"  # 서비스 이름
    version = "v1"  # 버전

    def __init__(self, *args, **kwargs):
        """
        Google Storage Connector 초기화
        
        Args:
            *args: 기본 인자들
            **kwargs: 키워드 인자들 (secret_data 포함)
        """
        super().__init__(*args, **kwargs)  # 기본 설정값들을 None으로 초기화

        self.secret_data = kwargs.get("secret_data")  # 시크릿 데이터 가져오기
        self.project_id = self.secret_data.get("project_id")  # 프로젝트 아이디 가져오기
        self.credentials = (
            google.oauth2.service_account.Credentials.from_service_account_info(
                self.secret_data  # 시크릿 데이터 가져오기
            )
        )  # 자격 증명 가져오기
        self.client = storage.Client(  # 클라이언트 생성
            project=self.secret_data["project_id"], credentials=self.credentials  # 프로젝트 아이디 및 자격 증명 설정
        )  # 클라이언트 생성

    def create_session(self, options: dict, secret_data: dict, schema: str = None) -> None:
        """
        세션 생성 및 설정
        
        Args:
            options: 설정 옵션 (현재 사용되지 않음)
            secret_data: 인증 정보
            schema: 스키마 정보 (현재 사용되지 않음)
        """
        # secret_data가 제공된 경우 자격 증명 업데이트
        if secret_data:  
            self.secret_data = secret_data  # 시크릿 데이터 업데이트
            self.project_id = secret_data.get("project_id")  # 프로젝트 아이디 업데이트
            self.credentials = (  # 자격 증명 업데이트
                google.oauth2.service_account.Credentials.from_service_account_info(
                    secret_data
                )
            )
            self.client = storage.Client(  # 클라이언트 업데이트
                project=secret_data["project_id"], credentials=self.credentials
            )

    def get_cost_data(self, task_options: dict) -> Generator[List[Dict[str, Any]], None, None]:  # 비용 데이터 가져오기
        """
        Google Cloud Storage 버킷에서 비용 데이터를 수집하는 메인 함수
        
        버킷 내의 모든 파일을 순회하며 CSV/JSON/Parquet 파일을 찾아 다운로드하고
        비용 데이터를 파싱하여 페이지네이션 형태로 반환합니다.
        
        Args:
            task_options (dict): 작업 옵션 (bucket_name 포함)
            
        Yields:
            List[Dict[str, Any]]: 비용 데이터 리스트 (페이지당 최대 1000개)
            
        Raises:
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
            ERROR_FILE_DOWNLOAD_FAILED: 파일 다운로드 실패 시
            ERROR_UNKNOWN: 기타 알 수 없는 오류
        """
        # 1. bucket_name 추출
        bucket_name = task_options.get("bucket_name")
        if not bucket_name:
            raise ERROR_REQUIRED_PARAMETER(key="task_options.bucket_name")
        
        # 2. 버킷 객체 가져오기
        bucket = self.client.get_bucket(bucket_name)
        # 2. 버킷 내 모든 blob 이름 리스트업
        blob_names = [blob.name for blob in bucket.list_blobs()]
        # 3. 각 blob(파일) 순회
        for blob_name in blob_names:
            # 3-1. 디렉토리 또는 빈 blob 이름은 건너뜀
            if not blob_name.strip() or blob_name.endswith('/'):
                continue
            # 3-2. blob 객체 가져오기
            blob = bucket.get_blob(blob_name)
            if blob:
                # 4. 파일 확장자 검증
                file_extension = os.path.splitext(blob_name)[1].lower()
                if file_extension not in _SUPPORTED_EXTENSIONS:
                    _LOGGER.warning(f"[get_cost_data] Skipping unsupported file type: {blob_name} (extension: {file_extension})")
                    continue
                # 5. Blob이 비어있는지 미리 확인
                if blob.size == 0:
                    raise ERROR_EMPTY_FILE(file_path=blob_name)
                # 6. Blob 크기가 너무 작은 경우 경고 (헤더만 있을 수 있음)
                if blob.size < _MIN_FILE_SIZE:
                    _LOGGER.warning(f"[get_cost_data] Blob size is very small: {blob.size} bytes for {blob_name}")
                    _LOGGER.warning("[get_cost_data] This might indicate an empty or header-only file")
                # 7. 임시 디렉토리 경로 확보
                tmpdir = tempfile.gettempdir()
                # 8. 안전한 임시 파일명 생성
                safe_filename = self._generate_safe_filename(blob_name)
                # 9. 임시 파일 전체 경로 생성
                temp_file_path = os.path.join(tmpdir, safe_filename)
                # 10. blob 파일을 임시 파일로 안전하게 다운로드
                try:
                    blob.download_to_filename(temp_file_path)
                except Exception:
                    raise ERROR_FILE_DOWNLOAD_FAILED(file_path=blob_name)
                # 11. 파일이 실제로 다운로드되었는지 확인
                if not os.path.exists(temp_file_path):
                    raise ERROR_UNKNOWN(message=f"Failed to download file: {blob_name} to {temp_file_path}")
                # 12. 파일 크기 확인
                file_size = os.path.getsize(temp_file_path)
                # 13. 파일이 비어있으면 예외 발생
                if file_size == 0:
                    # 13-1. 파일 내용 미리보기 시도(디버깅용)
                    try:
                        with open(temp_file_path, 'rb') as f:
                            f.read(200)
                    except Exception as e:
                        _LOGGER.error(f"[get_cost_data] Failed to read file content: {e}")
                    raise ERROR_EMPTY_FILE(file_path=blob_name)
                # 14. 파일에서 비용 데이터 읽기 (CSV/JSON/Parquet 자동 판별)
                costs_data = self._parse_cost_file(temp_file_path)
                # 15. 페이지네이션 처리 (1000개씩 분할)
                page_count = int(len(costs_data) / _PAGE_SIZE) + 1
                for page_num in range(page_count):
                    offset = _PAGE_SIZE * page_num  # 오프셋 계산
                    yield costs_data[offset : offset + _PAGE_SIZE]  # 페이지네이션 처리
                # 16. 임시 파일 정리(삭제)
                self._cleanup_temp_file(temp_file_path)

    @staticmethod
    def _check_options(options: dict) -> None:
        """
        필수 옵션 파라미터 검증
        
        Args:
            options (dict): 검증할 옵션 딕셔너리
            
        Raises:
            ERROR_REQUIRED_PARAMETER: bucket_name이 없는 경우
        """
        if "bucket_name" not in options:  # bucket_name이 없는 경우 예외 발생
            raise ERROR_REQUIRED_PARAMETER(key="options.bucket_name")

    @staticmethod
    def _validate_dataframe(df: pd.DataFrame, file_path: str) -> None:
        """
        DataFrame 유효성 검증 공통 메서드
        
        Args:
            df (pd.DataFrame): 검증할 DataFrame
            file_path (str): 파일 경로 (오류 메시지용)
            
        Raises:
            ERROR_NO_DATA_FOUND: DataFrame이 비어있는 경우
            ERROR_NO_COLUMNS: 컬럼이 없는 경우
        """
        if df.empty:  # DataFrame이 비어있는 경우 예외 발생
            _LOGGER.error(f"DataFrame is empty after parsing: {file_path}")
            raise ERROR_NO_DATA_FOUND(file_path=file_path)

        if len(df.columns) == 0:
            _LOGGER.error(f"No columns found in file: {file_path}")
            raise ERROR_NO_COLUMNS(file_path=file_path)

    def _generate_safe_filename(self, blob_name: str) -> str:
        """
        안전한 임시 파일명 생성
        
        경로 구분자 제거, 특수문자 처리, 해시 적용 등을 통해
        안전한 임시 파일명을 생성합니다.
        
        Args:
            blob_name (str): 원본 blob 이름
            
        Returns:
            str: 안전한 임시 파일명
        """
        import hashlib  # 해시 모듈 임포트
        import re  # 정규 표현식 모듈 임포트
        
        # 1. 경로 구분자를 언더스코어로 변경
        normalized_name = blob_name.replace('/', '_').replace('\\', '_')
        
        # 2. 연속된 언더스코어를 하나로 줄이기
        normalized_name = re.sub(r'_+', '_', normalized_name)
        
        # 3. 안전하지 않은 문자 제거(확장자 보존)
        base_name, extension = os.path.splitext(normalized_name)
        safe_base_name = re.sub(r'[^\w\-_.]', '_', base_name)
        
        # 4. 연속된 언더스코어 다시 하나로 줄이기
        safe_base_name = re.sub(r'_+', '_', safe_base_name)
        
        # 5. 앞뒤 언더스코어 제거
        safe_base_name = safe_base_name.strip('_')
        
        # 6. 빈 파일명이면 기본값 사용
        if not safe_base_name:
            safe_base_name = "billing_data"

        safe_filename = safe_base_name + extension  # 확장자 보존
        
        # 7. 파일명이 너무 길거나 언더스코어 비율이 높으면 해시 적용
        if (len(safe_filename) > _MAX_FILENAME_LENGTH or 
            safe_filename.count('_') > len(safe_filename) * _UNDERSCORE_RATIO_THRESHOLD):  # 파일명이 너무 길거나 언더스코어 비율이 높으면 해시 적용
            filename_hash = hashlib.md5(blob_name.encode()).hexdigest()  # 해시 생성
            file_extension = os.path.splitext(blob_name)[1] if '.' in blob_name else ''  # 확장자 추출
            safe_filename = f"billing_data_{filename_hash}{file_extension}"  # 파일명 생성
        
        # 8. 최종 파일명이 여전히 너무 길면 더 짧게 해시 적용
        if len(safe_filename) > _MAX_FINAL_FILENAME_LENGTH:  # 최종 파일명이 너무 길면 더 짧게 해시 적용
            filename_hash = hashlib.md5(blob_name.encode()).hexdigest()[:8]  # 해시 생성
            file_extension = os.path.splitext(blob_name)[1] if '.' in blob_name else ''  # 확장자 추출
            safe_filename = f"billing_{filename_hash}{file_extension}"  # 파일명 생성
        
        return safe_filename

    def _cleanup_temp_file(self, temp_file_path: str) -> None:
        """
        임시 파일 정리
        
        Args:
            temp_file_path (str): 삭제할 임시 파일 경로
        """
        try:
            if os.path.exists(temp_file_path):  # 임시 파일이 존재하는지 확인
                os.remove(temp_file_path)  # 임시 파일 삭제
                _LOGGER.debug(f"Successfully cleaned up temporary file: {temp_file_path}")
        except Exception as e:  # 기타 예외 발생
            _LOGGER.warning(f"Failed to clean up temporary file {temp_file_path}: {e}")

    @staticmethod
    def _parse_cost_file(cost_file: str) -> List[Dict[str, Any]]:
        """
        비용 데이터 파일을 읽어서 파싱하는 함수

        파일 확장자와 내용을 확인하여 CSV, JSON, Parquet 형식을 자동으로 판단하고
        적절한 파서를 사용하여 데이터를 읽습니다.

        Args:
            cost_file (str): 읽을 파일 경로

        Returns:
            List[Dict[str, Any]]: 파싱된 비용 데이터 리스트

        Raises:
            Exception: 파일 읽기 실패 시
        """
        try:
            # 1. 파일 확장자 추출 (소문자로 변환)
            file_extension = os.path.splitext(cost_file)[1].lower()

            # 2. Parquet 파일인 경우 (압축된 Parquet 파일 포함)
            parquet_extensions = ['.parquet', '.parquet.gz', '.parquet.snappy', '.parquet.zst', '.parquet.sz', '.parquet.zstd']
            if file_extension == '.parquet' or any(cost_file.lower().endswith(ext) for ext in parquet_extensions):
                # Parquet 파서 호출
                return GoogleStorageConnector._read_parquet_file(cost_file)

            # 3. JSON 파일인 경우 (.json.gz 포함)
            elif file_extension == '.json' or file_extension == '.json.gz':
                # JSON 파서 호출
                return GoogleStorageConnector._read_json_file(cost_file)

            # 4. 그 외(주로 CSV)인 경우
            else:
                # 4-1. 파일을 열어서 첫 번째 줄을 읽음 (명시적 인코딩 지정으로 None 인코딩 문제 방지)
                with open(cost_file, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()

                # 4-2. 첫 줄이 JSON 형식인지 확인
                if first_line.startswith('{') or '"billing_account_id"' in first_line:
                    # JSON 파서 호출
                    return GoogleStorageConnector._read_json_file(cost_file)
                else:
                    # CSV 파서 호출
                    return GoogleStorageConnector._read_csv_file(cost_file)

        except Exception as e:
            # 예외 발생 시 에러 로그 출력
            _LOGGER.error(f"[_parse_cost_file] file parsing error: {e}", exc_info=True)
            raise e

    @staticmethod
    def _read_csv_file(csv_file: str) -> List[Dict[str, Any]]:
        """
        CSV 파일을 읽어서 비용 데이터를 반환하는 함수

        다양한 구분자(쉼표, 세미콜론, 탭, 파이프)를 자동으로 감지하고
        pandas를 사용하여 CSV 파일을 파싱합니다.

        Args:
            csv_file (str): 읽을 CSV 파일 경로

        Returns:
            List[Dict[str, Any]]: 파싱된 비용 데이터 리스트

        Raises:
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
            ERROR_NO_DATA_ROWS: 데이터 행이 없는 경우
            ERROR_EMPTY_HEADER: 헤더가 비어있는 경우
            ERROR_NO_DATA_FOUND: 파싱 후 데이터가 없는 경우
            ERROR_NO_COLUMNS: 컬럼이 없는 경우
            ERROR_CSV_PARSING: CSV 파싱 오류
        """
        try:
            # 1. 파일을 열어서 전체 내용을 읽고 앞뒤 공백 제거 (명시적 인코딩 지정으로 None 인코딩 문제 방지)
            with open(csv_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            # 2. 파일이 비어있는지 확인
            if not content:
                _LOGGER.error(f"[_read_csv_file] File is empty: {csv_file}")
                raise ERROR_EMPTY_FILE(file_path=csv_file)

            # 3. 파일을 줄 단위로 분리
            lines = content.split('\n')

            # 4. 데이터 행이 존재하는지(최소 2줄 이상) 확인
            if len(lines) < 2:
                _LOGGER.error(f"[_read_csv_file] File has no data rows: {csv_file}")
                raise ERROR_NO_DATA_ROWS(file_path=csv_file)

            # 5. 첫 번째 줄(헤더)이 비어있는지 확인
            header_line = lines[0].strip()
            if not header_line:
                _LOGGER.error(f"[_read_csv_file] Empty header line: {csv_file}")
                raise ERROR_EMPTY_HEADER(file_path=csv_file)

            # 6. 구분자 자동 감지 (쉼표, 세미콜론, 탭, 파이프 중에서 탐색)
            detected_sep = ','
            for sep in _CSV_SEPARATORS:
                if sep in header_line:
                    detected_sep = sep
                    break

            # 7. pandas를 사용하여 CSV 파일을 읽음
            # 인코딩을 명시적으로 지정하여 None 인코딩 문제 방지
            df = pd.read_csv(
                csv_file,
                encoding="utf-8-sig",
                sep=detected_sep,
                skip_blank_lines=True,
                on_bad_lines='skip'
            )

            # 8. DataFrame 검증 함수 호출 (컬럼, 데이터 등 체크)
            GoogleStorageConnector._validate_dataframe(df, csv_file)

            # 9. NaN 값을 None으로 변환하여 일관성 유지
            df = df.replace({np.nan: None})
            costs_data = df.to_dict("records")

            # 10. 성공적으로 파싱된 레코드 수 로그 출력
            _LOGGER.info(f"[_read_csv_file] Successfully parsed {len(costs_data)} records from {csv_file}")
            return costs_data

        except pd.errors.EmptyDataError:
            # pandas에서 컬럼이 없을 때 발생하는 예외 처리
            _LOGGER.error(f"[_read_csv_file] Empty data error for {csv_file}")
            raise ERROR_NO_COLUMNS(file_path=csv_file)
        except pd.errors.ParserError as e:
            # pandas에서 파싱 오류 발생 시 예외 처리
            _LOGGER.error(f"[_read_csv_file] Parser error for {csv_file}: {e}")
            raise ERROR_CSV_PARSING(error_message=str(e))
        except Exception as e:
            # 기타 예외 처리 및 에러 로그 출력
            _LOGGER.error(f"[_read_csv_file] CSV read error: {e}", exc_info=True)
            raise e

    @staticmethod
    def _read_json_file(json_file: str) -> List[Dict[str, Any]]:
        """
        JSON 파일을 읽어서 비용 데이터를 반환하는 함수

        Google Cloud Billing Export에서 생성되는 JSONL(JSON Lines) 형식을 지원합니다.
        각 라인을 개별 JSON 객체로 파싱하여 리스트로 반환합니다.

        Args:
            json_file (str): 읽을 JSON 파일 경로

        Returns:
            List[Dict[str, Any]]: 파싱된 비용 데이터 리스트

        Raises:
            Exception: JSON 읽기 실패 시
        """
        try:
            import json  # 1. json 모듈 임포트

            # 2. 파일을 utf-8로 오픈 (명시적 인코딩 지정으로 None 인코딩 문제 방지)
            # .json.gz 파일인 경우 압축 해제하여 처리
            if json_file.lower().endswith('.json.gz'):
                _LOGGER.debug(f"[_read_json_file] Processing gzipped JSON file: {json_file}")
                with gzip.open(json_file, 'rt', encoding='utf-8') as f:
                    costs_data = []  # 3. 결과를 저장할 리스트 생성

                    # 4. 파일의 각 라인을 순회
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()  # 5. 양쪽 공백 제거
                        if line:  # 6. 빈 라인 건너뛰기
                            try:
                                record = json.loads(line)  # 7. JSON 파싱 시도
                                costs_data.append(record)  # 8. 파싱 성공 시 리스트에 추가
                            except json.JSONDecodeError as e:
                                # 9. 파싱 실패 시 경고 로그 남기고 계속 진행
                                _LOGGER.warning(f"[_read_json_file] Failed to parse JSON at line {line_num}: {e}")
                                continue

                    # 10. 성공적으로 파싱된 레코드 수 로그 출력
                    _LOGGER.info(f"[_read_json_file] Successfully parsed {len(costs_data)} records from {json_file}")
                    return costs_data  # 11. 결과 반환
            else:
                with open(json_file, 'r', encoding='utf-8') as f:
                    costs_data = []  # 3. 결과를 저장할 리스트 생성

                    # 4. 파일의 각 라인을 순회
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()  # 5. 양쪽 공백 제거
                        if line:  # 6. 빈 라인 건너뛰기
                            try:
                                record = json.loads(line)  # 7. JSON 파싱 시도
                                costs_data.append(record)  # 8. 파싱 성공 시 리스트에 추가
                            except json.JSONDecodeError as e:
                                # 9. 파싱 실패 시 경고 로그 남기고 계속 진행
                                _LOGGER.warning(f"[_read_json_file] Failed to parse JSON at line {line_num}: {e}")
                                continue

                    # 10. 성공적으로 파싱된 레코드 수 로그 출력
                    _LOGGER.info(f"[_read_json_file] Successfully parsed {len(costs_data)} records from {json_file}")
                    return costs_data  # 11. 결과 반환

        except Exception as e:
            # 12. 예외 발생 시 에러 로그 출력 및 재전파
            _LOGGER.error(f"[_read_json_file] JSON read error: {e}", exc_info=True)
            raise e

    @staticmethod
    def _read_parquet_file(parquet_file: str) -> List[Dict[str, Any]]:
        """
        Parquet 파일을 읽어서 비용 데이터를 반환하는 함수

        Google Cloud Billing Export에서 생성되는 Parquet 형식을 지원합니다.
        압축된 Parquet 파일(.parquet.gz, .parquet.snappy, .parquet.zst, .parquet.sz, .parquet.zstd)도 지원합니다.
        pyarrow 또는 fastparquet 라이브러리를 사용하여 Parquet 파일을 파싱합니다.

        Args:
            parquet_file (str): 읽을 Parquet 파일 경로

        Returns:
            List[Dict[str, Any]]: 파싱된 비용 데이터 리스트

        Raises:
            Exception: Parquet 읽기 실패 시
        """
        try:
            df = None  # 1. DataFrame 초기화
            file_extension = os.path.splitext(parquet_file)[1].lower()

            # 2. 압축된 Parquet 파일인지 확인
            is_compressed = file_extension in ['.parquet.gz', '.parquet.snappy', '.parquet.zst', '.parquet.sz', '.parquet.zstd']
            
            if is_compressed:
                _LOGGER.debug(f"[_read_parquet_file] Processing compressed Parquet file: {parquet_file} (extension: {file_extension})")

            # 3. pyarrow 엔진으로 읽기 시도
            try:
                df = pd.read_parquet(parquet_file, engine='pyarrow')
                _LOGGER.debug(f"[_read_parquet_file] Using pyarrow engine for {parquet_file}")
            except ImportError:
                # 4. pyarrow가 없으면 fastparquet 엔진으로 재시도
                try:
                    df = pd.read_parquet(parquet_file, engine='fastparquet')
                    _LOGGER.debug(f"[_read_parquet_file] Using fastparquet engine for {parquet_file}")
                except ImportError:
                    # 5. 두 엔진 모두 없으면 에러 발생
                    error_msg = "pyarrow or fastparquet library is required to read Parquet files."
                    _LOGGER.error(f"[_read_parquet_file] {error_msg}")
                    raise ImportError(error_msg)

            # 6. DataFrame이 정상적으로 읽혔는지 확인
            if df is None:
                raise Exception("Failed to read parquet file with any available engine")

            # 7. DataFrame 검증 함수 호출
            GoogleStorageConnector._validate_dataframe(df, parquet_file)

            # 8. NaN 값을 None으로 변환
            df = df.replace({np.nan: None})
            costs_data = df.to_dict("records")  # 9. DataFrame을 dict 리스트로 변환

            # 10. 성공적으로 파싱된 레코드 수 로그 출력
            _LOGGER.info(f"[_read_parquet_file] Successfully parsed {len(costs_data)} records from {parquet_file}")
            return costs_data  # 11. 결과 반환

        except Exception as e:
            # 12. 예외 발생 시 에러 로그 출력 및 재전파
            _LOGGER.error(f"[_read_parquet_file] Parquet read error: {e}", exc_info=True)
            raise e
