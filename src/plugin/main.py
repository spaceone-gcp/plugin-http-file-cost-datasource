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
    """Get external cost data

    Args:
        params (CostGetDataRequest): {
            'options': 'dict',      # Required
            'secret_data': 'dict',  # Required
            'schema': 'str',
            'task_options': 'dict',
            'domain_id': 'str'      # Required
        }

    Returns:
        Generator[ResourceResponse, None, None]
        {
            'cost': 'float',
            'usage_quantity': 'float',
            'usage_unit': 'str',
            'provider': 'str',
            'region_code': 'str',
            'product': 'str',
            'usage_type': 'str',
            'resource': 'str',
            'tags': 'dict'
            'additional_info': 'dict'
            'data': 'dict'
            'billed_date': 'str'
        }
    """

    options = params["options"]
    secret_data = params["secret_data"]
    secret_data['private_key'] = _clean_pem(secret_data['private_key'])

    task_options = params.get("task_options", {})
    schema = params.get("schema")

    cost_mgr = CostManager()
    
    try:
        result_generator = cost_mgr.get_data(options, secret_data, schema, task_options)
        
        for result in result_generator:
            yield result
            
    except Exception as e:
        _LOGGER = logging.getLogger("spaceone")
        _LOGGER.error(f"[cost_get_data] Error in get_data: {e}", exc_info=True)
        raise e


@app.route("Cost.get_linked_accounts")
def cost_get_linked_accounts(params: dict) -> dict:
    """ get linked accounts

    Args:
        params: (CostGetLinkedAccountsRequest): {
            'options': 'dict'
            'schema': 'str'
            'secret_data': 'dict'
            'domain_id': 'str'
        }

    Returns:
        {
            'account_id': 'str'
            'name': 'str'
        }
    """
    options = params["options"]
    secret_data = params["secret_data"]
    secret_data['private_key'] = _clean_pem(secret_data['private_key'])

    schema = params.get("schema")

    cost_mgr = CostManager()
    return cost_mgr.get_linked_accounts(options, secret_data, schema)


def _clean_pem(pem_key: str) -> str:
    # 여러 형태의 줄바꿈 문자를 정리
    cleaned = pem_key.replace('\\n', '\n')
    cleaned = cleaned.replace('\\r\\n', '\n')
    cleaned = cleaned.replace('\\r', '\n')
    
    # 앞뒤 공백 제거
    cleaned = cleaned.strip()
    
    # PEM 형식 검증
    if not cleaned.startswith('-----BEGIN PRIVATE KEY-----'):
        raise ValueError("Invalid PEM format: must start with '-----BEGIN PRIVATE KEY-----'")
    if not cleaned.endswith('-----END PRIVATE KEY-----'):
        raise ValueError("Invalid PEM format: must end with '-----END PRIVATE KEY-----'")
    
    return cleaned
