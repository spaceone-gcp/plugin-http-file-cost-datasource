"""
비용 정보를 처리하는 모듈

이 모듈은 비용 데이터를 SpaceONE의 protobuf 형식으로 변환하는 기능을 제공합니다.
HTTP 파일이나 Google Cloud Storage에서 읽어온 비용 데이터를 SpaceONE API에서 사용할 수 있는 형태로 변환합니다.
주요 기능:
- CostInfo: 단일 비용 데이터 변환
- CostsInfo: 여러 비용 데이터 변환
- LinkedAccountsInfo: 연결된 계정 정보 변환
"""

import logging
from spaceone.api.cost_analysis.plugin import cost_pb2
from spaceone.core.pygrpc.message_type import change_struct_type
# 비용 데이터 변환 함수 
__all__ = ["CostInfo", "CostsInfo", "LinkedAccountsInfo"]
# 로깅 설정
_LOGGER = logging.getLogger(__name__)

def CostInfo(cost_data):
    """
    단일 비용 데이터를 SpaceONE CostInfo protobuf 객체로 변환합니다.
    
    Args:
        cost_data (dict): 변환할 비용 데이터 딕셔너리
            - cost: 비용 금액 (필수)
            - usage_quantity: 사용량 (선택)
            - usage_type: 사용 유형 (선택)
            - usage_unit: 사용 단위 (선택)
            - provider: 클라우드 제공자 (필수)
            - region_code: 리전 코드 (필수)
            - product: 제품명 (필수)
            - resource: 리소스명 (선택)
            - tags: 태그 정보 (선택)
            - additional_info: 추가 정보 (선택)
            - billed_date: 청구 날짜 (필수)
    
    Returns:
        cost_pb2.CostInfo: 변환된 protobuf 객체
    
    Raises:
        Exception: 데이터 변환 중 오류 발생 시
    """
    try:
        # 비용 데이터를 SpaceONE API 형식에 맞게 매핑
        # cost와 usage_quantity는 숫자 타입으로 변환
        cost_value = cost_data["cost"]
        if isinstance(cost_value, str):
            cost_value = float(cost_value)
        
        usage_quantity_value = cost_data["usage_quantity"]
        if isinstance(usage_quantity_value, str):
            usage_quantity_value = float(usage_quantity_value)
        
        info = {
            "cost": cost_value,  # 비용 금액 (필수 필드) - 숫자 타입으로 변환
            "usage_quantity": usage_quantity_value,  # 사용량 (선택 필드) - 숫자 타입으로 변환
            "usage_type": cost_data.get("usage_type"),  # 사용 유형 (선택 필드)
            "usage_unit": cost_data.get("usage_unit"),  # 사용 단위 (선택 필드)
            "provider": cost_data["provider"],  # 클라우드 제공자 (필수 필드)
            "region_code": cost_data["region_code"],  # 리전 코드 (필수 필드)
            "product": cost_data["product"],  # 제품명 (필수 필드)
            "resource": cost_data.get("resource"),  # 리소스명 (선택 필드)
            "tags": change_struct_type(cost_data["tags"]),  # 태그 정보가 있으면 protobuf 구조체 타입으로 변환
            "additional_info": change_struct_type(cost_data["additional_info"]),  # 추가 정보가 있으면 protobuf 구조체 타입으로 변환
            "billed_date": cost_data["billed_date"],  # 청구 날짜 (필수 필드)
        }

        # protobuf 객체 생성 및 반환
        return cost_pb2.CostInfo(**info)

    except Exception as e:
        # 디버깅을 위한 로그 출력
        _LOGGER.debug(f"[CostInfo] error reason: {e}", exc_info=True)
        raise e


def CostsInfo(costs_data, **kwargs):
    """
    여러 건의 비용 데이터를 SpaceONE CostsInfo 프로토버퍼 객체로 변환합니다.

    동작 방식:
        - 입력 데이터가 리스트이거나, 딕셔너리 내 "results" 키에 리스트로 포함된 경우 모두 지원합니다.
        - 각 비용 데이터는 CostInfo 함수로 개별 변환됩니다.
        - 변환된 결과 리스트를 results 필드에 담아 CostsInfo 객체로 반환합니다.

    Args:
        costs_data (list 또는 dict): 변환할 비용 데이터 리스트 또는 {"results": [...]} 형태의 딕셔너리
        **kwargs: CostInfo 함수에 전달할 추가 매개변수

    Returns:
        cost_pb2.CostsInfo: 변환된 CostsInfo 프로토버퍼 객체 (여러 비용 정보 포함)

    Raises:
        Exception: 변환 과정에서 오류 발생 시 예외 발생
    """
    try:
        # costs_data가 딕셔너리이고 "results" 키가 있는 경우 처리
        if isinstance(costs_data, dict) and "results" in costs_data:
            costs_data = costs_data["results"]
        
        # 각 비용 데이터를 CostInfo로 변환하여 리스트로 만든 후 CostsInfo 객체 생성
        results = []  # 변환된 비용 데이터 리스트
        for cost_data in costs_data:
            if isinstance(cost_data, dict):  # 비용 데이터가 딕셔너리인 경우
                results.append(CostInfo(cost_data))
            else:
                _LOGGER.warning(f"[CostsInfo] Invalid cost_data type: {type(cost_data)}, value: {cost_data}")  # 비용 데이터가 딕셔너리가 아닌 경우 경고 메시지 출력
        
        return cost_pb2.CostsInfo(results=results)
    except Exception as e:
        _LOGGER.error(f"[CostsInfo] error reason: {e}", exc_info=True)
        raise e


def LinkedAccountsInfo(linked_accounts_data, **kwargs):
    """
    연결된 계정 정보를 SpaceONE AccountsInfo protobuf 객체로 변환합니다.
    
    Args:
        linked_accounts_data (list): 변환할 연결된 계정 데이터 리스트
            - account_id (str): 계정 ID
            - name (str): 계정명
        **kwargs: 추가 매개변수
    
    Returns:
        cost_pb2.AccountsInfo: 변환된 protobuf 객체 (연결된 계정 정보 포함)
    """
    try:
        # 각 연결된 계정 데이터를 protobuf 형식으로 변환
        linked_accounts = []
        for account_data in linked_accounts_data:
            account_info = {
                "account_id": account_data.get("account_id", ""),
                "name": account_data.get("name", "")
            }
            linked_accounts.append(cost_pb2.AccountInfo(**account_info))
        
        # AccountsInfo 객체 생성 및 반환  
        return cost_pb2.AccountsInfo(results=linked_accounts)
        
    except Exception as e:
        # 디버깅을 위한 로그 출력
        _LOGGER.debug(f"[LinkedAccountsInfo] error reason: {e}", exc_info=True)
        raise e
