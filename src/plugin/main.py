from typing import Generator
from spaceone.cost_analysis.plugin.data_source.lib.server import DataSourcePluginServer
from .manager.data_source_manager import DataSourceManager
from .manager.job_manager import JobManager
from .manager.cost_manager import CostManager
import logging

app = DataSourcePluginServer()


@app.route("DataSource.init")
def data_source_init(params: dict) -> dict:
    """init plugin by options

    Args:
        params (DataSourceInitRequest): {
            'options': 'dict',    # Required
            'domain_id': 'str'    # Required
        }

    Returns:
        PluginResponse: {
            'metadata': 'dict'
        }
    """
    options = params["options"]

    data_source_mgr = DataSourceManager()
    return data_source_mgr.init_response(options)


@app.route("DataSource.verify")
def data_source_verify(params: dict) -> None:
    """Verifying data source plugin

    Args:
        params (CollectorVerifyRequest): {
            'options': 'dict',      # Required
            'secret_data': 'dict',  # Required
            'schema': 'str',
            'domain_id': 'str'      # Required
        }

    Returns:
        None
    """

    options = params["options"]
    secret_data = params["secret_data"]
    secret_data['private_key'] = _clean_pem(secret_data['private_key'])
    domain_id = params.get("domain_id")
    schema = params.get("schema")

    data_source_mgr = DataSourceManager()
    data_source_mgr.verify_plugin(options, secret_data, domain_id, schema)


@app.route("Job.get_tasks")
def job_get_tasks(params: dict) -> dict:
    """Get job tasks

    Args:
        params (JobGetTaskRequest): {
            'options': 'dict',      # Required
            'secret_data': 'dict',  # Required
            'schema': 'str',
            'start': 'str',
            'last_synchronized_at': 'datetime',
            'domain_id': 'str'      # Required
        }

    Returns:
        TasksResponse: {
            'tasks': 'list',
            'changed': 'list'
        }

    """

    domain_id = params["domain_id"]
    options = params["options"]
    secret_data = params["secret_data"]
    secret_data['private_key'] = _clean_pem(secret_data['private_key'])

    schema = params.get("schema")
    start = params.get("start")
    last_synchronized_at = params.get("last_synchronized_at")

    job_mgr = JobManager()
    return job_mgr.get_tasks(
        domain_id, options, secret_data, schema, start, last_synchronized_at
    )


@app.route("Cost.get_data")
def cost_get_data(params: dict) -> Generator[dict, None, None]:
    """외부 비용 데이터를 수집하는 메인 함수

    이 함수는 HTTP 파일이나 Google Cloud Storage에서 비용 데이터를 수집하여
    SpaceONE의 비용 분석 시스템에서 사용할 수 있는 형태로 변환합니다.

    데이터 소스는 task_options에 따라 결정됩니다:
    - task_options.base_url이 있으면 HTTP 파일에서 데이터 수집
    - task_options.bucket_name이 있으면 Google Cloud Storage에서 데이터 수집
    - 둘 다 없으면 options.base_url을 fallback으로 사용

    Args:
        params (CostGetDataRequest): {
            'options': 'dict',      # Required - 플러그인 설정 옵션 (base_url, field_mapper, default_vars, type_mapper 등)
            'secret_data': 'dict',  # Required - 인증 정보 (private_key 등)
            'schema': 'str',        # Optional - 스키마 정보
            'task_options': 'dict', # Optional - 작업별 옵션 (base_url 또는 bucket_name)
            'domain_id': 'str'      # Required - 도메인 ID
        }

    Returns:
        Generator[ResourceResponse, None, None]: 비용 데이터 스트림
        각 yield되는 데이터는 다음과 같은 구조를 가집니다:
        {
            'cost': 'float',           # 비용 금액 (필수)
            'usage_quantity': 'float', # 사용량 (선택)
            'usage_unit': 'str',       # 사용량 단위 (선택)
            'provider': 'str',         # 클라우드 제공자 (선택)
            'region_code': 'str',      # 리전 코드 (선택)
            'product': 'str',          # 제품명 (선택)
            'usage_type': 'str',       # 사용 유형 (선택)
            'resource': 'str',         # 리소스명 (선택)
            'tags': 'dict',            # 태그 정보 (선택)
            'additional_info': 'dict', # 추가 정보 (선택)
            'data': 'dict',            # 원본 데이터 (선택)
            'billed_date': 'str'       # 청구 날짜 (필수)
        }

    Raises:
        ValueError: PEM 형식이 올바르지 않을 때
        Exception: 데이터 수집 중 오류가 발생할 때
    """

    # 1. 필수 파라미터 추출
    options = params["options"]  # 플러그인 옵션 정보 추출
    secret_data = params["secret_data"]  # 인증 정보 추출

    # 2. PEM 키 정리 (다양한 줄바꿈 문자 처리)
    if 'private_key' in secret_data:
        secret_data['private_key'] = _clean_pem(secret_data['private_key'])  # Google Cloud 인증을 위해 PEM 포맷의 private_key를 정리

    # 3. 선택적 파라미터 추출 (기본값 설정)
    task_options = params.get("task_options", {})  # task_options가 없으면 빈 dict로 대체
    schema = params.get("schema")  # 스키마 정보 추출 (선택)

    try:
        # 4. CostManager를 통해 데이터 수집 시작
        result_generator = CostManager().get_data(options, secret_data, schema, task_options)  # get_data는 Generator를 반환하므로 메모리 효율적으로 대용량 데이터 처리 가능

        # 5. 수집된 데이터를 하나씩 yield하여 스트리밍 방식으로 반환
        for result in result_generator:
            # 5-1. 각 result는 {"results": [비용 데이터 리스트]} 형태
            yield result

    except Exception as e:
        # 6. 오류 발생 시 로깅 및 예외 재발생
        _LOGGER = logging.getLogger("spaceone")
        _LOGGER.error(f"[cost_get_data] Error in get_data: {e}", exc_info=True)
        raise e


@app.route("Cost.get_linked_accounts")
def cost_get_linked_accounts(params: dict) -> dict:
    """ 연결된 계정(Linked Accounts) 정보를 조회하는 함수
    
    이 함수는 SpaceONE 플러그인의 gRPC 엔드포인트로, HTTP 파일이나 Google Cloud Storage에서
    비용 데이터를 수집할 때 연결된 계정들의 목록을 반환합니다.
    
    현재 구현 상태: CostManager.get_linked_accounts() 메서드가 구현되지 않아 AttributeError 발생 가능
    
    Args:
        params (dict): CostGetLinkedAccountsRequest 형태의 파라미터
            - options (dict): 플러그인 옵션 정보 (base_url, field_mapper, default_vars 등)
            - schema (str): 스키마 정보 (선택적)
            - secret_data (dict): 인증 정보 (private_key 포함)
            - domain_id (str): SpaceONE 도메인 ID

    Returns:
        dict: 연결된 계정 정보 리스트
            - account_id (str): 계정 ID
            - name (str): 계정명
            
    Raises:
        ValueError: PEM 형식이 올바르지 않을 때
        AttributeError: CostManager.get_linked_accounts() 메서드가 구현되지 않았을 때
        Exception: 기타 오류 발생 시
    """
    # 1. 필수 파라미터 추출
    options = params["options"]  # 플러그인 옵션 정보 추출
    secret_data = params["secret_data"]  # 인증 정보 추출
    
    # 2. PEM 키 정리 (다양한 줄바꿈 문자 처리)
    # Google Cloud 인증을 위해 PEM 포맷의 private_key를 정리
    if 'private_key' in secret_data:
        secret_data['private_key'] = _clean_pem(secret_data['private_key'])

    # 3. 선택적 파라미터 추출
    schema = params.get("schema")  # 스키마 정보 추출 (없으면 None)

    # 4. CostManager 인스턴스 생성 및 연결된 계정 조회
    try:
        _LOGGER = logging.getLogger("spaceone")
        _LOGGER.info("[cost_get_linked_accounts] CostManager.get_linked_accounts 호출 시작")
        result = CostManager().get_linked_accounts(options, secret_data, schema)
        _LOGGER.info(f"[cost_get_linked_accounts] CostManager.get_linked_accounts 완료: {result}")
        _LOGGER.info(f"[cost_get_linked_accounts] Result type: {type(result)}")
        _LOGGER.info(f"[cost_get_linked_accounts] Result length: {len(result) if isinstance(result, list) else 'N/A'}")
        return result
    except Exception as e:
        _LOGGER = logging.getLogger("spaceone")
        _LOGGER.error(f"[cost_get_linked_accounts] Error in get_linked_accounts: {e}", exc_info=True)
        raise e


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
    cleaned = pem_key.replace('\\n', '\n')
    cleaned = cleaned.replace('\\r\\n', '\n')
    cleaned = cleaned.replace('\\r', '\n')
    
    # 2. 앞뒤 공백 제거
    cleaned = cleaned.strip()
    
    # 3. PEM 형식 검증
    # Google Cloud 인증을 위한 표준 PEM 형식 검증
    if not cleaned.startswith('-----BEGIN PRIVATE KEY-----'):
        raise ValueError("Invalid PEM format: must start with '-----BEGIN PRIVATE KEY-----'")
    if not cleaned.endswith('-----END PRIVATE KEY-----'):
        raise ValueError("Invalid PEM format: must end with '-----END PRIVATE KEY-----'")
    
    return cleaned
