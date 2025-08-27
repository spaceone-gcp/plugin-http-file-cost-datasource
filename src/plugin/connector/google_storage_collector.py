import logging
import os
import tempfile
import time
from typing import Any, Dict, Generator, List

import google.oauth2.service_account
from google.cloud import storage
from spaceone.core.error import ERROR_UNKNOWN  # 알 수 없는 오류

# 베이스 클래스 import
from plugin.connector.base_file_connector import (  # 베이스 클래스 import
    MIN_FILE_SIZE,
    PARQUET_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    BaseFileConnector,
)
from plugin.error.cost import (
    ERROR_EMPTY_FILE,  # 파일이 비어있는 경우
    ERROR_FILE_DOWNLOAD_FAILED,  # 파일 다운로드 실패 시
    ERROR_REQUIRED_PARAMETER,  # 필수 파라미터 없는 경우
)

_LOGGER = logging.getLogger("spaceone")  # 로거 설정


class GoogleStorageConnector(BaseFileConnector):
    """
    Google Cloud Storage에서 비용 데이터를 수집하는 커넥터

    Google Cloud Storage 버킷에 저장된 CSV/JSON/Parquet 형태의 비용 데이터를
    다운로드하고 파싱하여 비용 정보를 추출합니다.
    """

    google_client_service = "storage"  # 구글 클라이언트 서비스
    version = "v1"  # 버전

    def __init__(self, *args, **kwargs):
        """
        Google Storage Connector 초기화

        Args:
            *args: 기본 인자들
            **kwargs: 키워드 인자들 (secret_data 포함)
        """
        super().__init__(*args, **kwargs)  # 베이스 클래스 초기화

        self.secret_data = kwargs.get("secret_data")  # 시크릿 데이터 설정
        self.project_id = self.secret_data.get("project_id")  # 프로젝트 ID 설정
        self.credentials = (
            google.oauth2.service_account.Credentials.from_service_account_info(
                self.secret_data  # 시크릿 데이터 설정
            )
        )
        self.client = storage.Client(
            project=self.secret_data["project_id"],
            credentials=self.credentials,  # 프로젝트 ID 설정
        )
        # Client timeout 설정 제거 (무제한)
        self.client._connection.timeout = None

    def create_session(
        self, options: dict, secret_data: dict, schema: str = None
    ) -> None:
        """
        세션 생성 및 설정

        Args:
            options: 설정 옵션 (현재 사용되지 않음)
            secret_data: 인증 정보
            schema: 스키마 정보 (현재 사용되지 않음)
        """
        # secret_data가 제공된 경우 자격 증명 업데이트
        if secret_data:
            self.secret_data = secret_data  # 시크릿 데이터 설정
            self.project_id = secret_data.get("project_id")  # 프로젝트 ID 설정
            self.credentials = (
                google.oauth2.service_account.Credentials.from_service_account_info(
                    secret_data  # 시크릿 데이터 설정
                )
            )
            self.client = storage.Client(
                project=secret_data["project_id"],
                credentials=self.credentials,  # 프로젝트 ID 설정
            )
            # Client timeout 설정 제거 (무제한)
            self.client._connection.timeout = None

    def get_cost_data(
        self, task_options: dict
    ) -> Generator[List[Dict[str, Any]], None, None]:
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
        # bucket_name 추출
        bucket_name = task_options.get("bucket_name")
        if not bucket_name:
            raise ERROR_REQUIRED_PARAMETER(
                key="task_options.bucket_name"
            )  # 파라미터 없는 경우 오류 발생

        # 버킷 객체 가져오기 (timeout 제거)
        bucket = self.client.get_bucket(bucket_name)  # 버킷 객체 가져오기

        # 버킷 내 모든 blob 이름 리스트업 (timeout 제거)
        blob_names = [
            blob.name for blob in bucket.list_blobs(timeout=None)
        ]  # blob 이름 리스트업 (timeout 제거)

        # 각 blob(파일) 순회
        for blob_name in blob_names:
            # 디렉토리 또는 빈 blob 이름은 건너뜀
            if not blob_name.strip() or blob_name.endswith(
                "/"
            ):  # 디렉토리 또는 빈 blob 이름은 건너뜀
                continue  # 건너뜀

            # blob 객체 가져오기
            blob = bucket.get_blob(blob_name)  # blob 객체 가져오기
            if blob:
                # 파일 확장자 검증 (개선된 방식)
                file_extension = self._extract_file_extension(blob_name)
                if file_extension not in SUPPORTED_EXTENSIONS:
                    _LOGGER.warning(
                        f"Skipping unsupported file type: {blob_name} (extension: {file_extension})"
                    )
                    continue

                # Blob이 비어있는지 미리 확인
                if blob.size == 0:
                    raise ERROR_EMPTY_FILE(
                        file_path=blob_name
                    )  # 파일이 비어있는 경우 오류 발생

                # Blob 크기가 너무 작은 경우 경고 (헤더만 있을 수 있음)
                if blob.size < MIN_FILE_SIZE:
                    _LOGGER.warning(
                        f"Blob size is very small: {blob.size} bytes for {blob_name}"
                    )  # 파일 크기가 너무 작은 경우 경고
                    _LOGGER.warning(
                        "This might indicate an empty or header-only file"
                    )  # 파일이 비어있거나 헤더만 있을 수 있음

                # 임시 디렉토리 경로 확보
                tmpdir = tempfile.gettempdir()  # 임시 디렉토리 경로 확보

                # 안전한 임시 파일명 생성
                safe_filename = self.generate_safe_filename(
                    blob_name
                )  # 안전한 임시 파일명 생성

                # 임시 파일 전체 경로 생성
                temp_file_path = os.path.join(tmpdir, safe_filename)

                # blob 파일을 임시 파일로 안전하게 다운로드 (timeout 제거)
                try:
                    blob.download_to_filename(
                        temp_file_path, timeout=None
                    )  # blob 파일을 임시 파일로 다운로드 (timeout 제거)
                except Exception as e:
                    raise ERROR_FILE_DOWNLOAD_FAILED(
                        file_path=blob_name
                    ) from e  # 파일 다운로드 실패 시 오류 발생

                # 파일이 실제로 다운로드되었는지 확인
                if not os.path.exists(temp_file_path):
                    raise ERROR_UNKNOWN(
                        message=f"Failed to download file: {blob_name} to {temp_file_path}"
                    )

                # 파일 크기 확인
                file_size = os.path.getsize(temp_file_path)

                # 파일이 비어있으면 예외 발생
                if file_size == 0:
                    # 파일 내용 미리보기 시도(디버깅용)
                    try:
                        with open(temp_file_path, "rb") as f:  # 파일 읽기
                            f.read(200)
                    except Exception as e:
                        _LOGGER.error(
                            f"Failed to read file content: {e}"
                        )  # 파일 읽기 실패 시 로깅
                    raise ERROR_EMPTY_FILE(
                        file_path=blob_name
                    )  # 파일이 비어있는 경우 오류 발생

                # 파일에서 비용 데이터 읽기 (개선된 타입 판별 사용)
                try:
                    costs_data = self._parse_cost_file_with_extension_detection(
                        temp_file_path, blob_name
                    )  # 파일에서 비용 데이터 읽기

                    # 데이터가 있는 경우에만 페이지네이션 처리
                    if costs_data:
                        # 🔥 혁신적 해결책: 데이터 소스에서 완전 정제
                        costs_data = self._ensure_only_dict_records(
                            costs_data, blob_name
                        )

                        if costs_data:  # 정제 후에도 데이터가 있는 경우에만
                            # 페이지네이션 처리 (1000개씩 분할)
                            yield from self.get_cost_data_paginated(
                                costs_data
                            )  # 페이지네이션 처리
                        _LOGGER.info(
                            f"Successfully processed {len(costs_data)} records from {blob_name}"
                        )
                    else:
                        _LOGGER.warning(f"No data found in file: {blob_name}")

                except Exception as parsing_error:
                    _LOGGER.error(f"Failed to parse file {blob_name}: {parsing_error}")
                    _LOGGER.warning("Continuing with next file...")
                    # 개별 파일 오류는 전체 처리를 중단하지 않음
                    continue
                finally:
                    # 임시 파일 정리(삭제) - 항상 실행
                    self.cleanup_temp_file(temp_file_path)  # 임시 파일 정리(삭제)

    def _extract_file_extension(self, filename: str) -> str:
        """
        파일명에서 확장자를 추출합니다.

        Google Cloud Storage의 파일명 패턴을 고려하여 확장자를 추출합니다.
        예: gcp_billing_export_v1_01FD8E_B4DDC1_EAB69F_JSON -> .json

        Args:
            filename: 파일명

        Returns:
            str: 추출된 확장자 (소문자, . 포함)
        """
        filename_lower = filename.lower()

        # 복합 확장자 먼저 확인 (.json.gz, .parquet.gz 등)
        for compound_ext in [
            ".json.gz",
            ".parquet.gz",
            ".parquet.snappy",
            ".parquet.zst",
            ".parquet.zstd",
        ]:
            if filename_lower.endswith(compound_ext):
                return compound_ext

        # 기본 확장자 추출 시도
        _, ext = os.path.splitext(filename)
        if ext:
            return ext.lower()

        # 확장자가 없는 경우, 파일명 끝에서 타입을 추출 시도
        filename_upper = filename.upper()

        # Google Cloud Billing Export 파일 패턴 확인
        if filename_upper.endswith("_JSON"):
            return ".json"
        elif filename_upper.endswith("_PARQUET"):
            return ".parquet"
        elif filename_upper.endswith("_CSV"):
            return ".csv"
        elif filename_upper.endswith("_AVRO"):
            return ".avro"

        # 다른 패턴들 확인
        if "_JSON_" in filename_upper or filename_upper.endswith(".JSON"):
            return ".json"
        elif "_PARQUET_" in filename_upper or filename_upper.endswith(".PARQUET"):
            return ".parquet"
        elif "_CSV_" in filename_upper or filename_upper.endswith(".CSV"):
            return ".csv"

        # 확장자를 찾을 수 없는 경우 빈 문자열 반환
        return ""

    def _parse_cost_file_with_extension_detection(
        self, file_path: str, blob_name: str
    ) -> List[Dict[str, Any]]:
        """
        파일 형식을 개선된 확장자 판별로 파싱합니다.

        Google Cloud Storage의 특수한 파일명 패턴을 고려하여 파일 타입을 판별합니다.

        Args:
            file_path: 로컬 임시 파일 경로
            blob_name: 원본 blob 파일명

        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트

        Raises:
            Exception: 파일 읽기 실패 시
        """
        try:
            # 원본 blob 이름에서 확장자 추출
            detected_extension = self._extract_file_extension(blob_name)

            _LOGGER.info(
                f"Parsing file: {blob_name} -> detected extension: {detected_extension}"
            )

            # Parquet 파일 처리
            if detected_extension in PARQUET_EXTENSIONS:
                _LOGGER.debug(f"Processing as Parquet file: {blob_name}")
                return self.read_parquet_file(file_path)

            # JSON 파일 처리
            elif detected_extension in [".json", ".json.gz"]:
                _LOGGER.debug(f"Processing as JSON file: {blob_name}")
                start_time = time.time()
                result = self.read_json_file(file_path)
                elapsed = time.time() - start_time
                _LOGGER.info(
                    f"JSON file processing completed: {blob_name} ({elapsed:.2f}s, {len(result)} records)"
                )
                return result

            # CSV 파일 처리
            elif detected_extension == ".csv":
                _LOGGER.debug(f"Processing as CSV file: {blob_name}")
                return self.read_csv_file(file_path)

            # 확장자를 감지할 수 없는 경우, 파일 내용을 확인
            else:
                _LOGGER.debug(f"Unknown extension, detecting file content: {blob_name}")
                return self._detect_and_parse_file_content(file_path, blob_name)

        except Exception as e:
            _LOGGER.error(
                f"Enhanced file parsing error for {blob_name}: {e}", exc_info=True
            )
            # 개별 파일 오류는 전체 처리를 중단하지 않도록 빈 리스트 반환
            _LOGGER.warning(f"Skipping file due to parsing error: {blob_name}")
            return []

    def _detect_and_parse_file_content(
        self, file_path: str, blob_name: str
    ) -> List[Dict[str, Any]]:
        """
        파일 내용을 확인하여 적절한 파서를 선택합니다.

        Args:
            file_path: 로컬 임시 파일 경로
            blob_name: 원본 blob 파일명

        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
        """
        try:
            # 파일이 바이너리인지 먼저 확인
            with open(file_path, "rb") as f:
                header = f.read(16)  # 더 많은 바이트를 읽어서 정확한 판별

            _LOGGER.debug(f"File header for {blob_name}: {header[:8].hex()}")

            # Parquet 매직 넘버 확인 (PAR1)
            if header.startswith(b"PAR1") or b"PAR1" in header[:8]:
                _LOGGER.info(f"Detected Parquet by magic number: {blob_name}")
                return self._safe_parse_parquet(file_path, blob_name)

            # gzip 매직 넘버 확인 (1f 8b)
            if header.startswith(b"\x1f\x8b"):
                _LOGGER.info(f"Detected gzip file: {blob_name}")
                return self._handle_gzip_file(file_path, blob_name)

            # JSON 또는 CSV로 텍스트 파일 처리 시도
            return self._handle_text_file(file_path, blob_name)

        except Exception as e:
            _LOGGER.error(f"Content detection error for {blob_name}: {e}")
            # 모든 방법이 실패한 경우 빈 리스트 반환 (오류 전파 방지)
            _LOGGER.warning(f"Skipping problematic file: {blob_name}")
            return []

    def _safe_parse_parquet(
        self, file_path: str, blob_name: str
    ) -> List[Dict[str, Any]]:
        """
        안전한 Parquet 파일 파싱

        Args:
            file_path: 로컬 임시 파일 경로
            blob_name: 원본 blob 파일명

        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
        """
        try:
            result = self.read_parquet_file(file_path)
            _LOGGER.info(
                f"Successfully parsed Parquet file: {blob_name} ({len(result)} records)"
            )
            return result
        except Exception as e:
            _LOGGER.error(f"Failed to parse Parquet file {blob_name}: {e}")
            return []

    def _handle_gzip_file(self, file_path: str, blob_name: str) -> List[Dict[str, Any]]:
        """
        gzip 압축 파일 처리

        Args:
            file_path: 로컬 임시 파일 경로
            blob_name: 원본 blob 파일명

        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
        """
        import gzip
        import tempfile

        try:
            with gzip.open(file_path, "rb") as gz_file:
                decompressed_data = gz_file.read()

            # 압축 해제된 데이터를 임시 파일에 저장
            with tempfile.NamedTemporaryFile(mode="wb", delete=False) as temp_file:
                temp_file.write(decompressed_data)
                unzipped_path = temp_file.name

            try:
                # 압축 해제된 파일의 내용 확인
                with open(unzipped_path, "rb") as f:
                    unzipped_header = f.read(8)

                _LOGGER.debug(
                    f"Unzipped header for {blob_name}: {unzipped_header.hex()}"
                )

                # Parquet 형식인지 확인
                if unzipped_header.startswith(b"PAR1") or b"PAR1" in unzipped_header:
                    _LOGGER.info(f"Detected compressed Parquet file: {blob_name}")
                    return self._safe_parse_parquet(unzipped_path, blob_name)
                else:
                    # JSON 또는 CSV로 처리
                    _LOGGER.info(f"Detected compressed text file: {blob_name}")
                    return self._handle_text_file(unzipped_path, blob_name)

            finally:
                # 임시 파일 정리
                self.cleanup_temp_file(unzipped_path)

        except Exception as e:
            _LOGGER.error(f"Failed to handle gzip file {blob_name}: {e}")
            return []

    def _handle_text_file(self, file_path: str, blob_name: str) -> List[Dict[str, Any]]:
        """
        텍스트 파일 처리 (JSON 또는 CSV)

        Args:
            file_path: 로컬 임시 파일 경로
            blob_name: 원본 blob 파일명

        Returns:
            List[Dict[str, Any]]: 파싱된 데이터 리스트
        """
        try:
            # 먼저 인코딩을 감지해보자
            import chardet

            with open(file_path, "rb") as f:
                raw_data = f.read(1024)  # 첫 1KB만 읽어서 인코딩 감지

            detected_encoding = chardet.detect(raw_data)
            encoding = detected_encoding.get("encoding", "utf-8")

            _LOGGER.debug(f"Detected encoding for {blob_name}: {encoding}")

            # 감지된 인코딩으로 파일 읽기 시도
            try:
                with open(file_path, encoding=encoding) as f:
                    first_line = f.readline().strip()

                # JSON 형식 확인
                if first_line.startswith("{") or '"billing_account_id"' in first_line:
                    _LOGGER.info(f"Detected JSON text file: {blob_name}")
                    result = self.read_json_file(file_path)
                    _LOGGER.info(
                        f"Successfully parsed JSON file: {blob_name} ({len(result)} records)"
                    )
                    return result
                else:
                    _LOGGER.info(f"Detected CSV text file: {blob_name}")
                    result = self.read_csv_file(file_path)
                    _LOGGER.info(
                        f"Successfully parsed CSV file: {blob_name} ({len(result)} records)"
                    )
                    return result

            except UnicodeDecodeError as e:
                _LOGGER.warning(
                    f"UTF-8 decode error for {blob_name} with encoding {encoding}: {e}"
                )
                # 다른 인코딩들 시도
                for fallback_encoding in ["latin-1", "cp1252", "iso-8859-1"]:
                    try:
                        with open(file_path, encoding=fallback_encoding) as f:
                            first_line = f.readline().strip()

                        _LOGGER.info(
                            f"Successfully read {blob_name} with {fallback_encoding} encoding"
                        )

                        if (
                            first_line.startswith("{")
                            or '"billing_account_id"' in first_line
                        ):
                            result = self.read_json_file(file_path)
                            return result
                        else:
                            result = self.read_csv_file(file_path)
                            return result

                    except Exception:
                        continue

                # 모든 텍스트 인코딩이 실패한 경우 Parquet으로 시도
                _LOGGER.warning(
                    f"All text encodings failed for {blob_name}, trying Parquet"
                )
                return self._safe_parse_parquet(file_path, blob_name)

        except Exception as e:
            _LOGGER.error(f"Failed to handle text file {blob_name}: {e}")
            return []

    @staticmethod
    def _check_options(options: dict) -> None:
        """
        필수 옵션 파라미터 검증

        Args:
            options (dict): 검증할 옵션 딕셔너리

        Raises:
            ERROR_REQUIRED_PARAMETER: bucket_name이 없는 경우
        """
        if "bucket_name" not in options:  # bucket_name이 없는 경우
            raise ERROR_REQUIRED_PARAMETER(
                key="options.bucket_name"
            )  # 파라미터 없는 경우 오류 발생

    def _ensure_only_dict_records(self, costs_data: list, source_file: str) -> list:
        """
        🔥 혁신적 해결책: 데이터 소스에서 딕셔너리 아닌 모든 데이터를 완전 제거

        이 함수는 처리 파이프라인에 들어가기 전에 모든 비딕셔너리 데이터를
        완전히 차단하여 'int' object has no attribute 'keys' 오류를 원천 봉쇄합니다.

        Args:
            costs_data (list): 원본 데이터 리스트
            source_file (str): 소스 파일명 (로깅용)

        Returns:
            list: 딕셔너리만 포함된 정제된 데이터 리스트
        """
        if not costs_data:
            return []

        original_count = len(costs_data)
        filtered_data = []
        non_dict_count = 0
        non_dict_types = {}

        for idx, record in enumerate(costs_data):
            if isinstance(record, dict):
                # 딕셔너리인 경우에만 추가
                if record:  # 빈 딕셔너리는 제외
                    filtered_data.append(record)
                else:
                    non_dict_count += 1
                    non_dict_types["empty_dict"] = (
                        non_dict_types.get("empty_dict", 0) + 1
                    )
            else:
                # 비딕셔너리 데이터는 완전 차단
                non_dict_count += 1
                type_name = type(record).__name__
                non_dict_types[type_name] = non_dict_types.get(type_name, 0) + 1

                # 상세 로깅 (처음 5개만)
                if non_dict_count <= 5:
                    _LOGGER.error(
                        f"🚫 BLOCKED non-dict data in {source_file} at index {idx}: "
                        f"{type_name} = {repr(record)[:100]}"
                    )

        # 정제 결과 로깅
        if non_dict_count > 0:
            _LOGGER.warning(
                f"🔥 DATA FILTER APPLIED to {source_file}: "
                f"Removed {non_dict_count}/{original_count} non-dict records. "
                f"Types removed: {non_dict_types}"
            )

        filtered_count = len(filtered_data)
        _LOGGER.info(
            f"✅ Data filtering complete for {source_file}: "
            f"{filtered_count}/{original_count} valid dict records passed through"
        )

        return filtered_data
