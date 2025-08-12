import logging
import os
import tempfile
from typing import List

import google.oauth2.service_account
import numpy as np
import pandas as pd
from google.cloud import storage

from plugin.error import *
from spaceone.core.connector import BaseConnector
from spaceone.core.error import ERROR_UNKNOWN

_PAGE_SIZE = 1000

_LOGGER = logging.getLogger("spaceone")


class GoogleStorageConnector(BaseConnector):
    """
    Google Cloud Storage에서 비용 데이터를 수집하는 커넥터
    
    Google Cloud Storage 버킷에 저장된 CSV/JSON 형태의 비용 데이터를
    다운로드하고 파싱하여 비용 정보를 추출합니다.
    """
    google_client_service = "storage"
    version = "v1"

    def __init__(self, *args, **kwargs):
        """
        Google Storage Connector 초기화
        
        Args:
            *args: 기본 인자들
            **kwargs: 키워드 인자들 (secret_data 포함)
        """
        super().__init__(*args, **kwargs)

        self.secret_data = kwargs.get("secret_data")
        self.project_id = self.secret_data.get("project_id")
        self.credentials = (
            google.oauth2.service_account.Credentials.from_service_account_info(
                self.secret_data
            )
        )
        self.client = storage.Client(
            project=self.secret_data["project_id"], credentials=self.credentials
        )

    def get_cost_data(self, bucket_name: str):
        """
        Google Cloud Storage 버킷에서 비용 데이터를 수집하는 메인 함수
        
        버킷 내의 모든 파일을 순회하며 CSV/JSON 파일을 찾아 다운로드하고
        비용 데이터를 파싱하여 페이지네이션 형태로 반환합니다.
        
        Args:
            bucket_name (str): Google Cloud Storage 버킷 이름
            
        Yields:
            List[dict]: 비용 데이터 리스트 (페이지당 최대 1000개)
            
        Raises:
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
            ERROR_FILE_DOWNLOAD_FAILED: 파일 다운로드 실패 시
            ERROR_UNKNOWN: 기타 알 수 없는 오류
        """
        # 1. 버킷 객체 가져오기
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
                # 4. 파일 확장자 검증 (.csv, .json만 허용)
                file_extension = os.path.splitext(blob_name)[1].lower()
                supported_extensions = ['.csv', '.json']
                if file_extension not in supported_extensions:
                    _LOGGER.warning(f"[get_cost_data] Skipping unsupported file type: {blob_name} (extension: {file_extension})")
                    continue
                # 5. Blob이 비어있는지 미리 확인
                if blob.size == 0:
                    raise ERROR_EMPTY_FILE(file_path=blob_name)
                # 6. Blob 크기가 너무 작은 경우 경고 (헤더만 있을 수 있음)
                if blob.size < 50:  # 50바이트 미만이면 의심스러움
                    _LOGGER.warning(f"[get_cost_data] Blob size is very small: {blob.size} bytes for {blob_name}")
                    _LOGGER.warning(f"[get_cost_data] This might indicate an empty or header-only file")
                # 7. 임시 디렉토리 경로 확보
                tmpdir = tempfile.gettempdir()
                # 8. 안전한 임시 파일명 생성 (경로 구분자 제거, 특수문자 처리, 해시 적용)
                import hashlib, re
                # 8-1. 경로 구분자를 언더스코어로 변경
                normalized_name = blob_name.replace('/', '_').replace('\\', '_')
                # 8-2. 연속된 언더스코어를 하나로 줄이기
                normalized_name = re.sub(r'_+', '_', normalized_name)
                # 8-3. 안전하지 않은 문자 제거(확장자 보존)
                base_name, extension = os.path.splitext(normalized_name)
                safe_base_name = re.sub(r'[^\w\-_.]', '_', base_name)
                # 8-4. 연속된 언더스코어 다시 하나로 줄이기
                safe_base_name = re.sub(r'_+', '_', safe_base_name)
                # 8-5. 앞뒤 언더스코어 제거
                safe_base_name = safe_base_name.strip('_')
                # 8-6. 빈 파일명이면 기본값 사용
                if not safe_base_name:
                    safe_base_name = "billing_data"
                safe_filename = safe_base_name + extension
                # 8-7. 파일명이 너무 길거나 언더스코어 비율이 높으면 해시 적용
                if len(safe_filename) > 100 or safe_filename.count('_') > len(safe_filename) * 0.3:
                    filename_hash = hashlib.md5(blob_name.encode()).hexdigest()
                    file_extension = os.path.splitext(blob_name)[1] if '.' in blob_name else ''
                    safe_filename = f"billing_data_{filename_hash}{file_extension}"
                # 8-8. 최종 파일명이 여전히 너무 길면 더 짧게 해시 적용
                if len(safe_filename) > 150:
                    filename_hash = hashlib.md5(blob_name.encode()).hexdigest()[:8]
                    file_extension = os.path.splitext(blob_name)[1] if '.' in blob_name else ''
                    safe_filename = f"billing_{filename_hash}{file_extension}"
                # 8-9. 임시 파일 전체 경로 생성
                csv_file_path = os.path.join(tmpdir, safe_filename)
                # 9. blob 파일을 임시 파일로 안전하게 다운로드
                try:
                    blob.download_to_filename(csv_file_path)
                except Exception as e:
                    raise ERROR_FILE_DOWNLOAD_FAILED(file_path=blob_name)
                # 10. 파일이 실제로 다운로드되었는지 확인
                if not os.path.exists(csv_file_path):
                    raise ERROR_UNKNOWN(message=f"Failed to download file: {blob_name} to {csv_file_path}")
                # 11. 파일 크기 확인
                file_size = os.path.getsize(csv_file_path)
                # 12. 파일이 비어있으면 예외 발생
                if file_size == 0:
                    # 12-1. 파일 내용 미리보기 시도(디버깅용)
                    try:
                        with open(csv_file_path, 'rb') as f:
                            content_preview = f.read(200)
                    except Exception as e:
                        _LOGGER.error(f"[get_cost_data] Failed to read file content: {e}")
                    raise ERROR_EMPTY_FILE(file_path=blob_name)
                # 13. 파일에서 비용 데이터 읽기 (CSV/JSON 자동 판별)
                costs_data = self._get_csv(csv_file_path)
                # 14. 페이지네이션 처리 (1000개씩 분할)
                page_count = int(len(costs_data) / _PAGE_SIZE) + 1
                for page_num in range(page_count):
                    offset = _PAGE_SIZE * page_num
                    yield costs_data[offset : offset + _PAGE_SIZE]
                # 15. 임시 파일 정리(삭제)
                try:
                    if os.path.exists(csv_file_path):
                        os.remove(csv_file_path)
                except Exception as e:
                    _LOGGER.warning(f"[get_cost_data] Failed to clean up temporary file {csv_file_path}: {e}")

    @staticmethod
    def _check_options(options: dict) -> None:
        """
        필수 옵션 파라미터 검증
        
        Args:
            options (dict): 검증할 옵션 딕셔너리
            
        Raises:
            ERROR_REQUIRED_PARAMETER: bucket_name이 없는 경우
        """
        if "bucket_name" not in options:
            raise ERROR_REQUIRED_PARAMETER(key="options.bucket_name")

    @staticmethod
    def _get_csv(csv_file: str) -> List[dict]:
        """
        CSV 또는 JSON 파일을 읽어서 비용 데이터를 반환하는 함수
        
        파일의 첫 번째 줄을 확인하여 JSON 형식인지 CSV 형식인지 자동으로 판단하고
        적절한 파서를 사용하여 데이터를 읽습니다.
        
        Args:
            csv_file (str): 읽을 파일 경로
            
        Returns:
            List[dict]: 파싱된 비용 데이터 리스트
            
        Raises:
            Exception: 파일 읽기 실패 시
        """
        try:
            # 먼저 파일 내용을 확인하여 JSON인지 CSV인지 판단
            with open(csv_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
            
            # JSON 형태인지 확인 (Google Cloud Billing Export는 JSON 형태일 수 있음)
            if first_line.startswith('{') or '"billing_account_id"' in first_line:
                return GoogleStorageConnector._get_json(csv_file)
            else:
                return GoogleStorageConnector._read_csv_file(csv_file)

        except Exception as e:
            _LOGGER.error(f"[_get_csv] download error: {e}", exc_info=True)
            raise e

    @staticmethod
    def _read_csv_file(csv_file: str) -> List[dict]:
        """
        CSV 파일을 읽어서 비용 데이터를 반환하는 함수
        
        다양한 구분자(쉼표, 세미콜론, 탭, 파이프)를 자동으로 감지하고
        pandas를 사용하여 CSV 파일을 파싱합니다.
        
        Args:
            csv_file (str): 읽을 CSV 파일 경로
            
        Returns:
            List[dict]: 파싱된 비용 데이터 리스트
            
        Raises:
            ERROR_EMPTY_FILE: 파일이 비어있는 경우
            ERROR_NO_DATA_ROWS: 데이터 행이 없는 경우
            ERROR_EMPTY_HEADER: 헤더가 비어있는 경우
            ERROR_NO_DATA_FOUND: 파싱 후 데이터가 없는 경우
            ERROR_NO_COLUMNS: 컬럼이 없는 경우
            ERROR_CSV_PARSING: CSV 파싱 오류
        """
        try:
            # 먼저 파일 내용을 확인
            with open(csv_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            # 파일이 비어있는지 확인
            if not content:
                _LOGGER.error(f"[_read_csv_file] File is empty: {csv_file}")
                _LOGGER.error(f"[_read_csv_file] File size: {os.path.getsize(csv_file)} bytes")
                _LOGGER.error(f"[_read_csv_file] File exists: {os.path.exists(csv_file)}")
                raise ERROR_EMPTY_FILE(file_path=csv_file)
            
            lines = content.split('\n')
            
            # 헤더가 있는지 확인
            if len(lines) < 2:
                _LOGGER.error(f"[_read_csv_file] File has no data rows: {csv_file}")
                raise ERROR_NO_DATA_ROWS(file_path=csv_file)
            
            # 첫 번째 줄(헤더) 확인
            header_line = lines[0].strip()
            if not header_line:
                _LOGGER.error(f"[_read_csv_file] Empty header line: {csv_file}")
                raise ERROR_EMPTY_HEADER(file_path=csv_file)
            
            # 구분자 자동 감지
            separators = [',', ';', '\t', '|']
            detected_sep = ','
            
            for sep in separators:
                if sep in header_line:
                    detected_sep = sep
                    break
            
            # pandas로 CSV 읽기
            df = pd.read_csv(
                csv_file, 
                encoding="utf-8-sig",
                sep=detected_sep,
                skip_blank_lines=True,
                on_bad_lines='skip'
            )
            
            # 데이터프레임이 비어있는지 확인
            if df.empty:
                _LOGGER.error(f"[_read_csv_file] DataFrame is empty after parsing: {csv_file}")
                raise ERROR_NO_DATA_FOUND(file_path=csv_file)
            
            # 컬럼이 없는지 확인
            if len(df.columns) == 0:
                _LOGGER.error(f"[_read_csv_file] No columns found in CSV file: {csv_file}")
                raise ERROR_NO_COLUMNS(file_path=csv_file)
            
            df = df.replace({np.nan: None})

            costs_data = df.to_dict("records")
            
            # if costs_data:
            #     _LOGGER.debug(f"[_read_csv_file] First record keys: {list(costs_data[0].keys())}")
            #     _LOGGER.debug(f"[_read_csv_file] First record sample: {dict(list(costs_data[0].items())[:5])}")
            
            return costs_data

        except pd.errors.EmptyDataError:
            _LOGGER.error(f"[_read_csv_file] Empty data error for {csv_file}")
            raise ERROR_NO_COLUMNS(file_path=csv_file)
        except pd.errors.ParserError as e:
            _LOGGER.error(f"[_read_csv_file] Parser error for {csv_file}: {e}")
            raise ERROR_CSV_PARSING(error_message=str(e))
        except Exception as e:
            _LOGGER.error(f"[_read_csv_file] CSV read error: {e}", exc_info=True)
            raise e

    @staticmethod
    def _get_json(json_file: str) -> List[dict]:
        """
        JSON 파일을 읽어서 비용 데이터를 반환하는 함수
        
        Google Cloud Billing Export에서 생성되는 JSONL(JSON Lines) 형식을 지원합니다.
        각 라인을 개별 JSON 객체로 파싱하여 리스트로 반환합니다.
        
        Args:
            json_file (str): 읽을 JSON 파일 경로
            
        Returns:
            List[dict]: 파싱된 비용 데이터 리스트
            
        Raises:
            Exception: JSON 읽기 실패 시
        """
        try:
            import json
            
            with open(json_file, 'r', encoding='utf-8') as f:
                # 각 라인을 개별 JSON 객체로 읽기 (JSONL 형식)
                costs_data = []
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line:  # 빈 라인 건너뛰기
                        try:
                            record = json.loads(line)
                            costs_data.append(record)
                        except json.JSONDecodeError as e:
                            _LOGGER.warning(f"[_get_json] Failed to parse JSON at line {line_num}: {e}")
                            continue
                
                # if costs_data:
                #     _LOGGER.debug(f"[_get_json] First record keys: {list(costs_data[0].keys())}")
                #     _LOGGER.debug(f"[_get_json] First record sample: {dict(list(costs_data[0].items())[:5])}")
                
                return costs_data

        except Exception as e:
            _LOGGER.error(f"[_get_json] JSON read error: {e}", exc_info=True)
            raise e
