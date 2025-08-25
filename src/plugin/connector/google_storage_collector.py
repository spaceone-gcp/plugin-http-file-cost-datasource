import logging
import os
import tempfile
from typing import Any, Dict, Generator, List

import google.oauth2.service_account
from google.cloud import storage
from spaceone.core.error import ERROR_UNKNOWN  # 알 수 없는 오류

# 베이스 클래스 import
from plugin.connector.base_file_connector import (  # 베이스 클래스 import
    MIN_FILE_SIZE,
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

        # 버킷 객체 가져오기
        bucket = self.client.get_bucket(bucket_name)  # 버킷 객체 가져오기

        # 버킷 내 모든 blob 이름 리스트업
        blob_names = [blob.name for blob in bucket.list_blobs()]  # blob 이름 리스트업

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
                # 파일 확장자 검증
                file_extension = os.path.splitext(blob_name)[
                    1
                ].lower()  # 파일 확장자 검증
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

                # blob 파일을 임시 파일로 안전하게 다운로드
                try:
                    blob.download_to_filename(
                        temp_file_path
                    )  # blob 파일을 임시 파일로 다운로드
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

                # 파일에서 비용 데이터 읽기 (CSV/JSON/Parquet 자동 판별)
                costs_data = self.parse_cost_file(
                    temp_file_path
                )  # 파일에서 비용 데이터 읽기

                # 페이지네이션 처리 (1000개씩 분할)
                yield from self.get_cost_data_paginated(costs_data)  # 페이지네이션 처리

                # 임시 파일 정리(삭제)
                self.cleanup_temp_file(temp_file_path)  # 임시 파일 정리(삭제)

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
