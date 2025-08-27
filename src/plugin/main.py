import logging
from typing import Any, Dict, Generator, Optional

from spaceone.cost_analysis.plugin.data_source.lib.server import DataSourcePluginServer

from .manager.cost_manager import CostManager
from .manager.data_source_manager import DataSourceManager
from .manager.job_manager import JobManager

app = DataSourcePluginServer()

# 모듈 레벨에서 로거 선언
_LOGGER = logging.getLogger("spaceone")


# 타입 정의
class CostGetDataParams:
    """Cost.get_data 요청 파라미터 구조"""

    def __init__(self, params: Dict[str, Any]):  # 파라미터 초기화
        try:
            if not params:  # params가 빈 딕셔너리인지 확인
                raise ValueError("'params' cannot be empty")
            if not hasattr(params, "get"):  # params가 get 메서드를 가지고 있는지 확인
                raise ValueError("'params' must support dictionary operations")
        except Exception as e:
            raise ValueError(f"Invalid params: {e}")

        self.options: Dict[str, Any] = params.get("options", {})  # 플러그인 옵션
        self.secret_data: Dict[str, Any] = params.get(
            "secret_data", {}
        )  # 시크릿 데이터
        self.schema: Optional[str] = params.get("schema")  # 스키마 정보
        self.task_options: Dict[str, Any] = params.get(
            "task_options", {}
        )  # 작업별 옵션
        self.domain_id: str = params.get("domain_id", "")  # 도메인 ID

    def validate(self) -> None:
        """필수 파라미터 검증"""
        if not self.secret_data:  # 시크릿 데이터 검증
            raise ValueError("'secret_data' is required")
        if not self.domain_id:  # 도메인 ID 검증
            raise ValueError("'domain_id' is required")


def _validate_and_clean_secret_data(secret_data: Dict[str, Any]) -> Dict[str, Any]:
    """시크릿 데이터 검증 및 정리

    Args:
        secret_data: 검증할 시크릿 데이터

    Returns:
        정리된 시크릿 데이터

    Raises:
        ValueError: 필수 필드가 없거나 PEM 형식이 잘못된 경우
    """
    try:
        if not secret_data:  # secret_data가 빈 딕셔너리인지 확인
            raise ValueError("'secret_data' cannot be empty")
        if not hasattr(
            secret_data, "get"
        ):  # secret_data가 get 메서드를 가지고 있는지 확인
            raise ValueError("'secret_data' must support dictionary operations")
    except Exception as e:
        raise ValueError(f"Invalid secret_data: {e}")

    # PEM 키 정리 (다양한 줄바꿈 문자 처리)
    if "private_key" in secret_data:  # PEM 키 존재 시 정리
        secret_data["private_key"] = _clean_pem(
            secret_data["private_key"]
        )  # PEM 키 정리 함수 호출

    return secret_data


def _create_cost_manager() -> CostManager:
    """CostManager 인스턴스 생성 (싱글톤 패턴 고려)

    Returns:
        CostManager 인스턴스
    """
    # BaseManager를 올바르게 초기화하기 위해 빈 딕셔너리로 전달
    return CostManager({})


@app.route("DataSource.init")
def data_source_init(params: Dict[str, Any]) -> Dict[str, Any]:
    """데이터 소스 플러그인 초기화

    Args:
        params: 초기화 파라미터
            - options (dict): 플러그인 옵션 (필수)
            - domain_id (str): 도메인 ID (필수)

    Returns:
        Dict[str, Any]: 플러그인 응답
            {
                'metadata': dict  # 메타데이터 정보
            }

    Raises:
        ValueError: 필수 파라미터가 없을 때
        Exception: 초기화 중 오류 발생 시
    """
    try:
        # 1. 파라미터 검증
        try:
            if not params:  # params가 빈 딕셔너리인지 확인
                raise ValueError("'params' cannot be empty")
            if not hasattr(params, "get"):  # params가 get 메서드를 가지고 있는지 확인
                raise ValueError("'params' must support dictionary operations")
        except Exception as e:
            raise ValueError(f"Invalid params: {e}")

        options = params.get("options")  # 플러그인 옵션
        domain_id = params.get("domain_id")  # 도메인 ID

        # 2. 필수 파라미터 검증
        if not options:  # 플러그인 옵션 검증
            raise ValueError("'options' is required")
        if not domain_id:  # 도메인 ID 검증
            raise ValueError("'domain_id' is required")

        # 3. 데이터 소스 매니저를 통해 초기화
        _LOGGER.info(
            f"[data_source_init] 데이터 소스 초기화 시작 - domain_id: {domain_id}"
        )

        data_source_mgr = DataSourceManager()  # DataSourceManager 인스턴스 생성
        result = data_source_mgr.init_response(options)  # 데이터 소스 초기화 응답 생성

        _LOGGER.info(
            f"[data_source_init] 데이터 소스 초기화 완료 - domain_id: {domain_id}"
        )

        return result

    except ValueError as e:
        _LOGGER.error(f"[data_source_init] 파라미터 오류: {e}")
        raise
    except Exception as e:
        _LOGGER.error(f"[data_source_init] 초기화 오류: {e}", exc_info=True)
        raise


@app.route("DataSource.verify")
def data_source_verify(params: Dict[str, Any]) -> None:
    """데이터 소스 플러그인 검증

    Args:
        params: 검증 파라미터
            - options (dict): 플러그인 옵션 (필수)
            - secret_data (dict): 인증 정보 (필수)
            - schema (str, optional): 스키마 정보
            - domain_id (str): 도메인 ID (필수)

    Returns:
        None

    Raises:
        ValueError: 필수 파라미터가 없거나 PEM 형식이 올바르지 않을 때
        Exception: 검증 중 오류 발생 시
    """
    try:
        # 1. 파라미터 검증
        try:
            if not params:  # params가 빈 딕셔너리인지 확인
                raise ValueError("'params' cannot be empty")
            if not hasattr(params, "get"):  # params가 get 메서드를 가지고 있는지 확인
                raise ValueError("'params' must support dictionary operations")
        except Exception as e:
            raise ValueError(f"Invalid params: {e}")

        options = params.get("options")  # 플러그인 옵션
        secret_data = params.get("secret_data")  # 시크릿 데이터
        domain_id = params.get("domain_id")  # 도메인 ID
        schema = params.get("schema")  # 스키마 정보

        # 2. 필수 파라미터 검증
        if not options:  # 플러그인 옵션 검증
            raise ValueError("'options' is required")
        if not secret_data:  # 시크릿 데이터 검증
            raise ValueError("'secret_data' is required")
        if not domain_id:  # 도메인 ID 검증
            raise ValueError("'domain_id' is required")

        # 3. 시크릿 데이터 검증 및 정리
        cleaned_secret_data = _validate_and_clean_secret_data(secret_data)

        # 4. 데이터 소스 매니저를 통해 검증
        _LOGGER.info(
            f"[data_source_verify] 데이터 소스 검증 시작 - domain_id: {domain_id}"
        )

        data_source_mgr = DataSourceManager()  # DataSourceManager 인스턴스 생성
        data_source_mgr.verify_plugin(
            options, cleaned_secret_data, domain_id, schema
        )  # 데이터 소스 검증

        _LOGGER.info(
            f"[data_source_verify] 데이터 소스 검증 완료 - domain_id: {domain_id}"
        )

    except ValueError as e:
        _LOGGER.error(f"[data_source_verify] 파라미터 오류: {e}")
        raise
    except Exception as e:
        _LOGGER.error(f"[data_source_verify] 검증 오류: {e}", exc_info=True)
        raise


@app.route("Job.get_tasks")
def job_get_tasks(params: Dict[str, Any]) -> Dict[str, Any]:
    """작업 태스크 조회

    Args:
        params: 작업 태스크 조회 파라미터
            - options (dict): 플러그인 옵션 (필수)
            - secret_data (dict): 인증 정보 (필수)
            - schema (str, optional): 스키마 정보
            - start (str, optional): 시작 시간
            - last_synchronized_at (datetime, optional): 마지막 동기화 시간
            - domain_id (str): 도메인 ID (필수)

    Returns:
        Dict[str, Any]: 작업 태스크 응답
            {
                'tasks': list,    # 작업 태스크 리스트
                'changed': list   # 변경된 태스크 리스트
            }

    Raises:
        ValueError: 필수 파라미터가 없거나 PEM 형식이 올바르지 않을 때
        Exception: 태스크 조회 중 오류 발생 시
    """
    try:
        # 1. 파라미터 검증
        try:
            if not params:  # params가 빈 딕셔너리인지 확인
                raise ValueError("'params' cannot be empty")
            if not hasattr(params, "get"):  # params가 get 메서드를 가지고 있는지 확인
                raise ValueError("'params' must support dictionary operations")
        except Exception as e:
            raise ValueError(f"Invalid params: {e}")

        domain_id = params.get("domain_id")  # 도메인 ID
        options = params.get("options")  # 플러그인 옵션
        secret_data = params.get("secret_data")  # 시크릿 데이터
        schema = params.get("schema")  # 스키마 정보
        start = params.get("start")  # 시작 시간
        last_synchronized_at = params.get("last_synchronized_at")  # 마지막 동기화 시간

        # 2. 필수 파라미터 검증
        if not domain_id:  # 도메인 ID 검증
            raise ValueError("'domain_id' is required")
        if not options:  # 플러그인 옵션 검증
            raise ValueError("'options' is required")
        if not secret_data:  # 시크릿 데이터 검증
            raise ValueError("'secret_data' is required")

        # 3. 시크릿 데이터 검증 및 정리
        cleaned_secret_data = _validate_and_clean_secret_data(secret_data)

        # 4. 작업 매니저를 통해 태스크 조회
        _LOGGER.info(f"[job_get_tasks] 작업 태스크 조회 시작 - domain_id: {domain_id}")

        job_mgr = JobManager()  # JobManager 인스턴스 생성
        result = job_mgr.get_tasks(
            domain_id,
            options,
            cleaned_secret_data,
            schema,
            start,
            last_synchronized_at,  # 작업 태스크 조회
        )

        _LOGGER.info(f"[job_get_tasks] 작업 태스크 조회 완료 - domain_id: {domain_id}")

        return result

    except ValueError as e:
        _LOGGER.error(f"[job_get_tasks] 파라미터 오류: {e}")
        raise
    except Exception as e:
        _LOGGER.error(f"[job_get_tasks] 태스크 조회 오류: {e}", exc_info=True)
        raise


@app.route("Cost.get_data")
def cost_get_data(params: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
    """외부 비용 데이터를 수집하는 메인 함수

    HTTP 파일이나 Google Cloud Storage에서 비용 데이터를 수집하여
    SpaceONE의 비용 분석 시스템에서 사용할 수 있는 형태로 변환합니다.

    데이터 소스 우선순위:
    1. task_options.base_url → HTTP 파일
    2. task_options.bucket_name → Google Cloud Storage
    3. options.base_url → HTTP 파일 (fallback)

    Args:
        params: 비용 데이터 수집 파라미터
            - options (dict): 플러그인 설정 옵션 (base_url, field_mapper, default_vars, type_mapper 등)
            - secret_data (dict): 인증 정보 (private_key 등)
            - schema (str, optional): 스키마 정보
            - task_options (dict, optional): 작업별 옵션 (base_url 또는 bucket_name)
            - domain_id (str): 도메인 ID

    Yields:
        Dict[str, Any]: 비용 데이터 스트림
            {
                'results': [
                    {
                        'cost': float,           # 비용 금액 (필수)
                        'usage_quantity': str,   # 사용량 (선택)
                        'usage_unit': str,       # 사용량 단위 (선택)
                        'provider': str,         # 클라우드 제공자 (선택)
                        'region_code': str,      # 리전 코드 (선택)
                        'product': str,          # 제품명 (선택)
                        'usage_type': str,       # 사용 유형 (선택)
                        'resource': str,         # 리소스명 (선택)
                        'tags': dict,            # 태그 정보 (선택)
                        'additional_info': dict, # 추가 정보 (선택)
                        'data': dict,            # 원본 데이터 (선택)
                        'billed_date': str       # 청구 날짜 (필수)
                    }
                ]
            }

    Raises:
        ValueError: 필수 파라미터가 없거나 PEM 형식이 올바르지 않을 때
        ConnectionError: 데이터 소스 연결 실패 시
        Exception: 데이터 수집 중 기타 오류 발생 시
    """
    try:
        # 1. 파라미터 검증 및 정리
        cost_params = CostGetDataParams(params)  # CostGetDataParams 인스턴스 생성
        cost_params.validate()  # 파라미터 검증

        # 2. 시크릿 데이터 검증 및 정리
        cleaned_secret_data = _validate_and_clean_secret_data(cost_params.secret_data)

        # 3. 데이터 소스 검증
        _validate_data_source(cost_params.options, cost_params.task_options)

        # 4. CostManager를 통해 데이터 수집 시작
        _LOGGER.info(
            f"[cost_get_data] 데이터 수집 시작 - domain_id: {cost_params.domain_id}"
        )

        cost_manager = _create_cost_manager()  # CostManager 인스턴스 생성
        result_generator = cost_manager.get_data(
            cost_params.options,  # 플러그인 옵션
            cleaned_secret_data,  # 시크릿 데이터
            cost_params.schema,  # 스키마 정보
            cost_params.task_options,  # 작업별 옵션
        )

        # 5. 수집된 데이터를 스트리밍 방식으로 반환
        for result in result_generator:
            yield result

        _LOGGER.info(
            f"[cost_get_data] 데이터 수집 완료 - domain_id: {cost_params.domain_id}"
        )

    except ValueError as e:
        _LOGGER.error(f"[cost_get_data] 파라미터 오류: {e}")
        raise
    except ConnectionError as e:
        _LOGGER.error(f"[cost_get_data] 연결 오류: {e}")
        raise
    except Exception as e:
        _LOGGER.error(f"[cost_get_data] 예상치 못한 오류: {e}", exc_info=True)
        raise


def _validate_data_source(
    options: Dict[str, Any], task_options: Dict[str, Any]
) -> None:
    """데이터 소스 설정 검증

    Args:
        options: 플러그인 옵션
        task_options: 작업별 옵션

    Raises:
        ValueError: 데이터 소스 정보가 없을 때
    """
    has_base_url = (
        "base_url" in task_options or "base_url" in options
    )  # base_url 존재 여부 확인
    has_bucket_name = "bucket_name" in task_options  # bucket_name 존재 여부 확인

    if not (
        has_base_url or has_bucket_name
    ):  # base_url 또는 bucket_name 존재 여부 확인
        raise ValueError(
            "데이터 소스 정보가 필요합니다. "
            "task_options.base_url, task_options.bucket_name, 또는 options.base_url 중 하나를 제공해주세요."
        )


@app.route("Cost.get_linked_accounts")
def cost_get_linked_accounts(params: Dict[str, Any]) -> Dict[str, Any]:
    """연결된 계정(Linked Accounts) 정보를 조회하는 함수

    HTTP 파일이나 Google Cloud Storage에서 비용 데이터를 수집할 때
    연결된 계정들의 목록을 반환합니다.

    Args:
        params: 연결된 계정 조회 파라미터
            - options (dict): 플러그인 옵션 정보 (base_url, field_mapper, default_vars 등)
            - secret_data (dict): 인증 정보 (private_key 포함)
            - schema (str, optional): 스키마 정보
            - domain_id (str): SpaceONE 도메인 ID

    Returns:
        Dict[str, Any]: 연결된 계정 정보 리스트
            [
                {
                    'account_id': str,  # 계정 ID
                    'name': str         # 계정명
                }
            ]

    Raises:
        ValueError: 필수 파라미터가 없거나 PEM 형식이 올바르지 않을 때
        AttributeError: CostManager.get_linked_accounts() 메서드가 구현되지 않았을 때
        Exception: 기타 오류 발생 시
    """
    try:
        # 1. 파라미터 검증 및 정리
        try:
            if not params:  # params가 빈 딕셔너리인지 확인
                raise ValueError("'params' cannot be empty")
            if not hasattr(params, "get"):  # params가 get 메서드를 가지고 있는지 확인
                raise ValueError("'params' must support dictionary operations")
        except Exception as e:
            raise ValueError(f"Invalid params: {e}")

        options = params.get("options")  # 플러그인 옵션
        secret_data = params.get("secret_data")  # 시크릿 데이터
        schema = params.get("schema")  # 스키마 정보
        domain_id = params.get("domain_id")  # 도메인 ID

        # 2. 필수 파라미터 검증
        if not options:  # 플러그인 옵션 검증
            raise ValueError("'options' is required")
        if not secret_data:  # 시크릿 데이터 검증
            raise ValueError("'secret_data' is required")
        if not domain_id:  # 도메인 ID 검증
            raise ValueError("'domain_id' is required")

        # 3. 시크릿 데이터 검증 및 정리
        cleaned_secret_data = _validate_and_clean_secret_data(secret_data)

        # 4. CostManager를 통해 연결된 계정 조회
        _LOGGER.info(
            f"[cost_get_linked_accounts] 연결된 계정 조회 시작 - domain_id: {domain_id}"
        )

        cost_manager = _create_cost_manager()  # CostManager 인스턴스 생성
        result = cost_manager.get_linked_accounts(
            options, cleaned_secret_data, schema
        )  # 연결된 계정 조회

        _LOGGER.info(
            f"[cost_get_linked_accounts] 연결된 계정 조회 완료 - domain_id: {domain_id}"
        )
        _LOGGER.debug(f"[cost_get_linked_accounts] Result type: {type(result)}")
        _LOGGER.debug(
            f"[cost_get_linked_accounts] Result length: {len(result) if isinstance(result, list) else 'N/A'}"
        )

        return result

    except ValueError as e:
        _LOGGER.error(f"[cost_get_linked_accounts] 파라미터 오류: {e}")
        raise
    except AttributeError as e:
        _LOGGER.error(f"[cost_get_linked_accounts] 메서드 구현 오류: {e}")
        raise
    except Exception as e:
        _LOGGER.error(
            f"[cost_get_linked_accounts] 예상치 못한 오류: {e}", exc_info=True
        )
        raise


def _clean_pem(pem_key: str) -> str:
    """PEM 형식의 private key를 정리하고 검증하는 함수

    Google Cloud 인증을 위해 PEM 포맷의 private key에서 다양한 줄바꿈 문자를
    표준 형식으로 변환하고, PEM 형식의 유효성을 검증합니다.

    Args:
        pem_key (str): 정리할 PEM 형식의 private key 문자열

    Returns:
        str: 정리된 PEM 형식의 private key 문자열

    Raises:
        ValueError: PEM 형식이 올바르지 않을 때
            - '-----BEGIN PRIVATE KEY-----'로 시작하지 않을 때
            - '-----END PRIVATE KEY-----'로 끝나지 않을 때
    """
    # 1. 여러 형태의 줄바꿈 문자를 표준 형식으로 정리
    # \n, \r\n, \r 등 다양한 줄바꿈 문자를 \n으로 통일
    cleaned = pem_key.replace("\\n", "\n")  # \n 줄바꿈 문자를 \n으로 통일
    cleaned = cleaned.replace("\\r\\n", "\n")  # \r\n 줄바꿈 문자를 \n으로 통일
    cleaned = cleaned.replace("\\r", "\n")  # \r 줄바꿈 문자를 \n으로 통일

    # 2. 앞뒤 공백 제거
    cleaned = cleaned.strip()  # 앞뒤 공백 제거

    # 3. PEM 형식 검증
    # Google Cloud 인증을 위한 표준 PEM 형식 검증
    if not cleaned.startswith("-----BEGIN PRIVATE KEY-----"):  # PEM 형식 검증
        raise ValueError(
            "Invalid PEM format: must start with '-----BEGIN PRIVATE KEY-----'"
        )
    if not cleaned.endswith("-----END PRIVATE KEY-----"):  # PEM 형식 검증
        raise ValueError(
            "Invalid PEM format: must end with '-----END PRIVATE KEY-----'"
        )

    return cleaned
