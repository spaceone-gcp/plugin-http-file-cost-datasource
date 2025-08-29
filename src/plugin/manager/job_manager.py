import logging

from spaceone.core.error import ERROR_REQUIRED_PARAMETER
from spaceone.core.manager import BaseManager

from plugin.connector.http_file_connector import HTTPFileConnector
from plugin.model.job_model import Tasks

_LOGGER = logging.getLogger(__name__)


class JobManager(BaseManager):
    """
    작업 관리자 클래스

    HTTP 파일 또는 Google Storage에서 데이터를 수집하기 위한 작업을 생성하고 관리합니다.
    SpaceOne의 BaseManager를 상속받아 기본 관리자 기능을 제공합니다.
    """

    def __init__(self, *args, **kwargs):
        """
        JobManager 초기화

        Args:
            *args: 위치 인자들
            **kwargs: 키워드 인자들
        """
        super().__init__(*args, **kwargs)

    def get_tasks(self, options, secret_data, schema, start, last_synchronized_at):
        """
        데이터 수집을 위한 작업 목록을 생성합니다.

        HTTP 파일 또는 Google Storage 버킷에서 데이터를 수집하기 위한
        작업(task)들을 생성하고 반환합니다.

        Args:
            options (dict): 설정 옵션
                - base_url: HTTP 파일의 기본 URL 목록 (HTTP 파일 수집 시)
                - bucket_name: Google Storage 버킷 이름 목록 (GCS 수집 시)
            secret_data (dict): 인증 정보 (API 키, 토큰 등)
            schema (dict): 데이터 스키마 정의
            start (str): 데이터 수집 시작 시간
            last_synchronized_at (str): 마지막 동기화 시간

        Returns:
            dict: 생성된 작업 목록과 변경 정보를 포함한 딕셔너리

        Raises:
            ERROR_REQUIRED_PARAMETER: 필수 옵션이 누락된 경우
        """
        tasks = []  # 생성될 작업 목록
        changed = []  # 변경 정보 목록

        # HTTP 파일 수집 옵션이 있는 경우
        if "base_url" in options:
            # HTTP 파일 커넥터 생성 및 세션 설정
            http_file_connector = self.locator.get_connector(HTTPFileConnector)
            http_file_connector.create_session(options, secret_data, schema)

            # 각 base_url에 대해 개별 작업 생성
            for base_url in http_file_connector.base_url:
                task_options = {"base_url": base_url}

                tasks.append({"task_options": task_options})
                changed.append({"start": "1900-01"})  # 기본 시작 시간 설정

        # Google Storage 버킷 수집 옵션이 있는 경우
        elif "bucket_name" in options:
            # 각 버킷에 대해 개별 작업 생성
            bucket_names = options.get("bucket_name", [])
            if not bucket_names:
                raise ERROR_REQUIRED_PARAMETER(key="options.bucket_name")
            for bucket_name in bucket_names:
                task_options = {"bucket_name": bucket_name}

                tasks.append({"task_options": task_options})
                changed.append({"start": "1900-01"})  # 기본 시작 시간 설정
        else:
            # 필수 옵션이 없는 경우 에러 발생
            raise ERROR_REQUIRED_PARAMETER(key="options")

        # 디버그 로그 출력
        _LOGGER.debug(f"[get_tasks] tasks: {tasks}")
        _LOGGER.debug(f"[get_tasks] changed: {changed}")

        # Tasks 모델을 사용하여 데이터 검증 및 변환
        tasks = Tasks({"tasks": tasks, "changed": changed})

        # 데이터 유효성 검증
        tasks.validate()

        # 원시 데이터 형태로 반환
        return tasks.to_primitive()
