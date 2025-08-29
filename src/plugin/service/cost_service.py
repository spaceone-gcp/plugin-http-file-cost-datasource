import logging

from spaceone.core.service import (
    BaseService,
    authentication_handler,
    authorization_handler,
    check_required,
    event_handler,
    transaction,
)

from plugin.manager.cost_manager import CostManager

_LOGGER = logging.getLogger(__name__)


@authentication_handler
@authorization_handler
@event_handler
class CostService(BaseService):
    """
    비용 데이터 수집 서비스 클래스

    HTTP 파일이나 Google Cloud Storage에서 비용 데이터를 수집하고 처리하는 서비스입니다.
    SpaceONE의 BaseService를 상속받아 표준화된 서비스 구조를 따릅니다.

    주요 기능:
    - get_data: 비용 데이터 수집 및 스트리밍
    - get_linked_accounts: 연결된 계정 정보 조회
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cost_mgr: CostManager = self.locator.get_manager(CostManager)

    @transaction
    @check_required(["options", "secret_data", "task_options"])
    def get_data(self, params):
        """비용 데이터를 수집하고 반환하는 메서드

        HTTP 파일이나 Google Cloud Storage에서 비용 데이터를 수집하여
        SpaceONE에서 요구하는 포맷으로 변환하여 제너레이터로 반환합니다.

        Args:
            params (dict): 비용 데이터 수집 파라미터
                - options (dict): 플러그인 옵션 정보 (base_url, field_mapper, default_vars 등)
                - secret_data (dict): 인증 정보 (private_key 포함)
                - schema (str): 스키마 정보 (선택적)
                - task_options (dict): 작업별 옵션 (base_url 또는 bucket_name)
                - domain_id (str): SpaceONE 도메인 ID

        Returns:
            Generator: 비용 데이터 스트림 (메모리 효율적인 대용량 데이터 처리)
        """
        options = params["options"]
        secret_data = params["secret_data"]
        schema = params.get("schema")
        task_options = params["task_options"]

        # 데이터 소스 정보 검증
        has_base_url = (
            "base_url" in task_options or "base_url" in options
        )  # base_url 존재 여부 확인
        has_bucket_name = "bucket_name" in task_options  # bucket_name 존재 여부 확인

        # 빈 options와 task_options가 올 때는 빈 제너레이터 반환
        if not (has_base_url or has_bucket_name):
            _LOGGER.warning(
                "[CostService.get_data] 데이터 소스 정보가 없습니다. 빈 응답을 반환합니다."
            )

            # 빈 결과를 가진 제너레이터 반환
            def empty_generator():
                yield {"results": []}

            return empty_generator()

        return self.cost_mgr.get_data(options, secret_data, schema, task_options)

    @transaction
    @check_required(["options", "secret_data"])
    def get_linked_accounts(self, params):
        """연결된 계정(Linked Accounts) 정보를 조회하는 메서드

        HTTP 파일이나 Google Cloud Storage에서 비용 데이터를 수집할 때
        연결된 계정들의 목록을 반환합니다. 이 정보는 SpaceONE에서
        계정별 비용 분석을 위해 사용됩니다.

        Args:
            params (dict): 연결된 계정 조회 파라미터
                - options (dict): 플러그인 옵션 정보 (base_url, field_mapper, default_vars 등)
                - secret_data (dict): 인증 정보 (private_key 포함)
                - schema (str): 스키마 정보 (선택적)
                - domain_id (str): SpaceONE 도메인 ID

        Returns:
            list: 연결된 계정 정보 리스트
                - account_id (str): 계정 ID
                - name (str): 계정명
        """
        options = params["options"]
        secret_data = params["secret_data"]
        schema = params.get("schema")

        return self.cost_mgr.get_linked_accounts(options, secret_data, schema)
