import logging

from spaceone.core.manager import BaseManager

from plugin.connector.google_storage_collector import (
    GoogleStorageConnector,
)
from plugin.connector.http_file_connector import HTTPFileConnector
from plugin.model.data_source_model import PluginMetadata

_LOGGER = logging.getLogger(__name__)


class DataSourceManager(BaseManager):
    """
    데이터 소스 관리를 담당하는 매니저 클래스

    이 클래스는 플러그인의 데이터 소스 초기화 및 검증을 처리합니다.
    HTTP 파일 연결과 Google Storage 연결을 지원합니다.
    """

    @staticmethod
    def init_response(options):
        """
        데이터 소스 초기화 응답을 생성합니다.

        Args:
            options (dict): 플러그인 옵션 설정
                - currency: 통화 설정 (기본값: USD)
                - bucket_name: Google Storage 버킷 이름 (선택사항)
                - provider: 클라우드 제공자 (google_cloud, aws, azure)
                - base_url: HTTP 파일 URL (선택사항)

        Returns:
            dict: 초기화된 메타데이터 정보
                - Google Storage 사용 시: 데이터 소스 규칙과 통화 정보 포함
                - HTTP 파일 사용 시: 기본 플러그인 메타데이터만 포함
        """
        # 플러그인 메타데이터 객체 생성 및 검증
        plugin_metadata = PluginMetadata()
        plugin_metadata.validate()

        # 통화 설정 (기본값: USD)
        currency = options.get("currency", "USD")

        # Google Storage 버킷이 설정된 경우 (Google Storage 연결)
        if "bucket_name" in options:
            # 클라우드 제공자 설정 (기본값: google_cloud)
            provider = options.get("provider", "google_cloud")

            # Google Cloud의 경우 프로젝트 ID 매핑
            source = "additional_info.Project ID"
            target = "data.project_id"

            # AWS의 경우 계정 ID 매핑
            if provider == "aws":
                source = "additional_info.Account ID"
                target = "data.account_id"
            # Azure의 경우 구독 ID 매핑
            elif provider == "azure":
                source = "additional_info.Subscription Id"
                target = "data.subscription_id"

            # Google Storage용 데이터 소스 규칙 반환
            return {
                "metadata": {
                    "data_source_rules": [
                        {
                            "name": "match_service_account",
                            "conditions_policy": "ALWAYS",
                            "actions": {
                                "match_service_account": {
                                    "source": source,
                                    "target": target,
                                }
                            },
                            "options": {"stop_processing": True},
                        }
                    ],
                    "currency": currency,
                }
            }

        # HTTP 파일 연결 또는 기본 설정의 경우 기본 메타데이터 반환
        return {"metadata": plugin_metadata.to_primitive()}

    def verify_plugin(self, options, secret_data, schema, domain_id=None):
        """
        플러그인 연결을 검증합니다.

        Args:
            options (dict): 플러그인 옵션 설정
            secret_data (dict): 인증 정보 (API 키, 비밀번호 등)
            schema (dict): 데이터 스키마 정보
            domain_id (str): 도메인 ID (선택사항)

        Raises:
            Exception: 연결 검증 실패 시 예외 발생
        """
        # HTTP 파일 연결 검증 (base_url이 설정된 경우)
        if "base_url" in options:
            # HTTP 파일 커넥터를 통해 세션 생성 및 검증
            http_file_connector: HTTPFileConnector = self.locator.get_connector(
                HTTPFileConnector
            )
            http_file_connector.create_session(options, secret_data, schema)
        # Google Storage 연결 검증 (bucket_name이 설정된 경우)
        elif "bucket_name" in options:
            # Google Storage 커넥터를 통해 연결 검증
            self.locator.get_connector(GoogleStorageConnector, secret_data=secret_data)
