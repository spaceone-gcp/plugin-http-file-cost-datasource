import os
import logging
import pandas as pd
import numpy as np
import tempfile
from typing import List
import google.oauth2.service_account
from google.cloud import storage
from plugin.error import *
from spaceone.core.connector import BaseConnector
from spaceone.core.error import ERROR_UNKNOWN

_PAGE_SIZE = 1000

_LOGGER = logging.getLogger("spaceone")


class GoogleStorageConnector(BaseConnector):
    google_client_service = "storage"
    version = "v1"

    def __init__(self, *args, **kwargs):
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

        bucket = self.client.get_bucket(bucket_name)
        blob_names = [blob.name for blob in bucket.list_blobs()]
        
        _LOGGER.debug(f"[get_cost_data] Found {len(blob_names)} blobs in bucket {bucket_name}")
        _LOGGER.debug(f"[get_cost_data] Blob names: {blob_names}")

        for blob_name in blob_names:
            # 디렉토리 형태의 blob은 건너뛰기
            if blob_name.endswith('/'):
                _LOGGER.warning(f"[get_cost_data] Skipping directory-like blob: {blob_name}")
                continue
                
            # 빈 blob 이름 건너뛰기
            if not blob_name.strip():
                _LOGGER.warning(f"[get_cost_data] Skipping empty blob name")
                continue
            
            blob = bucket.get_blob(blob_name)

            if blob:
                # Blob 정보 로깅
                _LOGGER.debug(f"[get_cost_data] Processing blob: {blob_name}")
                _LOGGER.debug(f"[get_cost_data] Blob size: {blob.size} bytes")
                _LOGGER.debug(f"[get_cost_data] Blob content type: {blob.content_type}")
                _LOGGER.debug(f"[get_cost_data] Blob updated: {blob.updated}")
                
                # 파일 확장자 검증
                file_extension = os.path.splitext(blob_name)[1].lower()
                supported_extensions = ['.csv', '.json']
                
                if file_extension not in supported_extensions:
                    _LOGGER.warning(f"[get_cost_data] Skipping unsupported file type: {blob_name} (extension: {file_extension})")
                    continue
                
                # Blob이 비어있는지 미리 확인
                if blob.size == 0:
                    _LOGGER.error(f"[get_cost_data] Blob is empty: {blob_name}")
                    _LOGGER.error(f"[get_cost_data] Blob size: {blob.size} bytes")
                    _LOGGER.error(f"[get_cost_data] Blob content type: {blob.content_type}")
                    _LOGGER.error(f"[get_cost_data] Blob updated: {blob.updated}")
                    _LOGGER.error(f"[get_cost_data] Blob generation: {blob.generation}")
                    _LOGGER.error(f"[get_cost_data] Blob metageneration: {blob.metageneration}")
                    raise ERROR_EMPTY_FILE(file_path=blob_name)
                
                # Blob 크기가 너무 작은 경우 경고 (헤더만 있을 수 있음)
                if blob.size < 50:  # 50바이트 미만이면 의심스러움
                    _LOGGER.warning(f"[get_cost_data] Blob size is very small: {blob.size} bytes for {blob_name}")
                    _LOGGER.warning(f"[get_cost_data] This might indicate an empty or header-only file")
                tmpdir = tempfile.gettempdir()
                # 파일명에서 경로 구분자 제거하고 안전한 파일명 생성
                # 파일명이 너무 길거나 특수문자가 많을 경우를 대비해 해시값 사용
                import hashlib
                import re
                
                # 경로 구분자를 언더스코어로 변경하고 안전하지 않은 문자들을 제거
                # 먼저 경로 구분자를 언더스코어로 변경
                normalized_name = blob_name.replace('/', '_').replace('\\', '_')
                
                # 연속된 언더스코어를 하나로 줄이기
                normalized_name = re.sub(r'_+', '_', normalized_name)
                
                # 안전하지 않은 문자들을 제거하되, 파일 확장자는 보존
                base_name, extension = os.path.splitext(normalized_name)
                safe_base_name = re.sub(r'[^\w\-_.]', '_', base_name)
                
                # 연속된 언더스코어를 다시 하나로 줄이기
                safe_base_name = re.sub(r'_+', '_', safe_base_name)
                
                # 앞뒤 언더스코어 제거
                safe_base_name = safe_base_name.strip('_')
                
                # 빈 파일명이면 기본값 사용
                if not safe_base_name:
                    safe_base_name = "billing_data"
                
                safe_filename = safe_base_name + extension
                
                # 파일명이 너무 길거나 특수문자가 많은 경우 해시값 사용
                if len(safe_filename) > 100 or safe_filename.count('_') > len(safe_filename) * 0.3:
                    filename_hash = hashlib.md5(blob_name.encode()).hexdigest()
                    file_extension = os.path.splitext(blob_name)[1] if '.' in blob_name else ''
                    safe_filename = f"billing_data_{filename_hash}{file_extension}"
                
                # 최종 파일명이 여전히 너무 길면 더 짧게 만들기
                if len(safe_filename) > 150:
                    filename_hash = hashlib.md5(blob_name.encode()).hexdigest()[:8]
                    file_extension = os.path.splitext(blob_name)[1] if '.' in blob_name else ''
                    safe_filename = f"billing_{filename_hash}{file_extension}"
                
                # 최종 파일명 로깅
                _LOGGER.debug(f"[get_cost_data] Original blob name: {blob_name}")
                _LOGGER.debug(f"[get_cost_data] Safe filename: {safe_filename}")
                _LOGGER.debug(f"[get_cost_data] Temp directory: {tmpdir}")
                
                csv_file_path = os.path.join(tmpdir, safe_filename)
                _LOGGER.debug(f"[get_cost_data] Full temp path: {csv_file_path}")
                _LOGGER.debug(f"[get_cost_data] Path length: {len(csv_file_path)}")
                _LOGGER.debug(f"[get_cost_data] Downloading {blob_name} to {csv_file_path}")
                
                # 안전한 다운로드 시도
                try:
                    blob.download_to_filename(csv_file_path)
                    _LOGGER.debug(f"[get_cost_data] Download completed successfully")
                except Exception as e:
                    _LOGGER.error(f"[get_cost_data] Download failed: {e}")
                    _LOGGER.error(f"[get_cost_data] Blob name: {blob_name}")
                    _LOGGER.error(f"[get_cost_data] Target path: {csv_file_path}")
                    _LOGGER.error(f"[get_cost_data] Blob size: {blob.size if blob else 'Unknown'}")
                    _LOGGER.error(f"[get_cost_data] Blob content type: {blob.content_type if blob else 'Unknown'}")
                    _LOGGER.error(f"[get_cost_data] Exception type: {type(e).__name__}")
                    raise ERROR_FILE_DOWNLOAD_FAILED(file_path=blob_name)
                
                # 파일이 실제로 다운로드되었는지 확인
                if not os.path.exists(csv_file_path):
                    _LOGGER.error(f"[get_cost_data] File download failed: {csv_file_path}")
                    _LOGGER.error(f"[get_cost_data] Original blob name: {blob_name}")
                    _LOGGER.error(f"[get_cost_data] Blob size: {blob.size if blob else 'Unknown'}")
                    _LOGGER.error(f"[get_cost_data] Safe filename: {safe_filename}")
                    _LOGGER.error(f"[get_cost_data] Temp directory exists: {os.path.exists(tmpdir)}")
                    _LOGGER.error(f"[get_cost_data] Temp directory contents: {os.listdir(tmpdir) if os.path.exists(tmpdir) else 'N/A'}")
                    raise ERROR_UNKNOWN(message=f"Failed to download file: {blob_name} to {csv_file_path}")
                
                # 파일 크기 확인
                file_size = os.path.getsize(csv_file_path)
                _LOGGER.debug(f"[get_cost_data] Downloaded file size: {file_size} bytes")
                
                if file_size == 0:
                    _LOGGER.error(f"[get_cost_data] Downloaded file is empty: {csv_file_path}")
                    _LOGGER.error(f"[get_cost_data] Original blob name: {blob_name}")
                    _LOGGER.error(f"[get_cost_data] Blob size: {blob.size if blob else 'Unknown'}")
                    _LOGGER.error(f"[get_cost_data] Safe filename: {safe_filename}")
                    _LOGGER.error(f"[get_cost_data] Temp directory: {tmpdir}")
                    _LOGGER.error(f"[get_cost_data] File exists: {os.path.exists(csv_file_path)}")
                    _LOGGER.error(f"[get_cost_data] File permissions: {oct(os.stat(csv_file_path).st_mode)[-3:] if os.path.exists(csv_file_path) else 'N/A'}")
                    
                    # 파일 내용 미리보기 시도
                    try:
                        with open(csv_file_path, 'rb') as f:
                            content_preview = f.read(200)
                            _LOGGER.error(f"[get_cost_data] File content preview (hex): {content_preview.hex()}")
                            _LOGGER.error(f"[get_cost_data] File content preview (repr): {repr(content_preview)}")
                    except Exception as e:
                        _LOGGER.error(f"[get_cost_data] Failed to read file content: {e}")
                    
                    raise ERROR_EMPTY_FILE(file_path=blob_name)
                
                costs_data = self._get_csv(csv_file_path)
                _LOGGER.debug(
                    f"[get_cost_data] costs count of {blob_name} : {len(costs_data)}"
                )

                # Paginate
                page_count = int(len(costs_data) / _PAGE_SIZE) + 1

                for page_num in range(page_count):
                    offset = _PAGE_SIZE * page_num
                    yield costs_data[offset : offset + _PAGE_SIZE]
                
                # 임시 파일 정리
                try:
                    if os.path.exists(csv_file_path):
                        os.remove(csv_file_path)
                        _LOGGER.debug(f"[get_cost_data] Cleaned up temporary file: {csv_file_path}")
                except Exception as e:
                    _LOGGER.warning(f"[get_cost_data] Failed to clean up temporary file {csv_file_path}: {e}")

    @staticmethod
    def _check_options(options: dict) -> None:
        if "bucket_name" not in options:
            raise ERROR_REQUIRED_PARAMETER(key="options.bucket_name")

    @staticmethod
    def _get_csv(csv_file: str) -> List[dict]:
        try:
            # 먼저 파일 내용을 확인하여 JSON인지 CSV인지 판단
            with open(csv_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
            
            # JSON 형태인지 확인 (Google Cloud Billing Export는 JSON 형태일 수 있음)
            if first_line.startswith('{') or '"billing_account_id"' in first_line:
                _LOGGER.debug(f"[_get_csv] Detected JSON format, reading as JSON")
                return GoogleStorageConnector._get_json(csv_file)
            else:
                _LOGGER.debug(f"[_get_csv] Detected CSV format, reading as CSV")
                return GoogleStorageConnector._read_csv_file(csv_file)

        except Exception as e:
            _LOGGER.error(f"[_get_csv] download error: {e}", exc_info=True)
            raise e

    @staticmethod
    def _read_csv_file(csv_file: str) -> List[dict]:
        """CSV 파일을 읽는 함수"""
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
            
            _LOGGER.debug(f"[_read_csv_file] Detected separator: '{detected_sep}' for {csv_file}")
            
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
            _LOGGER.debug(f"[_read_csv_file] Successfully read {len(costs_data)} records from {csv_file}")
            
            if costs_data:
                _LOGGER.debug(f"[_read_csv_file] First record keys: {list(costs_data[0].keys())}")
                _LOGGER.debug(f"[_read_csv_file] First record sample: {dict(list(costs_data[0].items())[:5])}")
            
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
        """JSON 파일을 읽는 함수 (Google Cloud Billing Export용)"""
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
                
                _LOGGER.debug(f"[_get_json] Successfully read {len(costs_data)} records from {json_file}")
                
                if costs_data:
                    _LOGGER.debug(f"[_get_json] First record keys: {list(costs_data[0].keys())}")
                    _LOGGER.debug(f"[_get_json] First record sample: {dict(list(costs_data[0].items())[:5])}")
                
                return costs_data

        except Exception as e:
            _LOGGER.error(f"[_get_json] JSON read error: {e}", exc_info=True)
            raise e
