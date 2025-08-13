"""
비용 정보를 처리하는 모듈

이 모듈은 비용 데이터를 SpaceONE의 protobuf 형식으로 변환하는 기능을 제공합니다.
HTTP 파일에서 읽어온 비용 데이터를 SpaceONE API에서 사용할 수 있는 형태로 변환합니다.
"""

import functools
import logging
from decimal import Decimal
from spaceone.api.cost_analysis.plugin import cost_pb2
from spaceone.core.pygrpc.message_type import change_struct_type

__all__ = ["CostInfo", "CostsInfo"]

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
        # Decimal 타입을 float로 변환하여 출력 (과학적 표기법 방지)
        cost_value = cost_data["cost"]
        if isinstance(cost_value, Decimal):
            # 과학적 표기법을 완전히 방지하기 위해 format 함수 사용
            cost_value_str = format(cost_value, 'f')
            # 불필요한 0 제거
            cost_value_str = cost_value_str.rstrip('0').rstrip('.')
            # 문자열을 float로 변환하되, 매우 작은 값은 문자열로 유지
            if cost_value_str and float(cost_value_str) < 0.0001:
                # 매우 작은 값은 문자열로 유지하여 과학적 표기법 방지
                cost_value = cost_value_str
            else:
                cost_value = float(cost_value_str) if cost_value_str else 0.0
            
        usage_quantity_value = cost_data.get("usage_quantity")
        if isinstance(usage_quantity_value, Decimal):
            # 과학적 표기법을 완전히 방지하기 위해 format 함수 사용
            usage_quantity_value_str = format(usage_quantity_value, 'f')
            # 불필요한 0 제거
            usage_quantity_value_str = usage_quantity_value_str.rstrip('0').rstrip('.')
            # 문자열을 float로 변환하되, 매우 작은 값은 문자열로 유지
            if usage_quantity_value_str and float(usage_quantity_value_str) < 0.0001:
                # 매우 작은 값은 문자열로 유지하여 과학적 표기법 방지
                usage_quantity_value = usage_quantity_value_str
            else:
                usage_quantity_value = float(usage_quantity_value_str) if usage_quantity_value_str else 0.0
        
        # 비용 데이터를 SpaceONE API 형식에 맞게 매핑
        info = {
            "cost": cost_value,  # 비용 금액 (필수 필드)
            "usage_quantity": usage_quantity_value,  # 사용량 (선택 필드)
            "usage_type": cost_data.get("usage_type"),  # 사용 유형 (선택 필드)
            "usage_unit": cost_data.get("usage_unit"),  # 사용 단위 (선택 필드)
            "provider": cost_data["provider"],  # 클라우드 제공자 (필수 필드)
            "region_code": cost_data["region_code"],  # 리전 코드 (필수 필드)
            "product": cost_data["product"],  # 제품명 (필수 필드)
            "resource": cost_data.get("resource"),  # 리소스명 (선택 필드)
            # 태그 정보가 있으면 protobuf 구조체 타입으로 변환
            "tags": change_struct_type(cost_data["tags"])
            if "tags" in cost_data
            else None,
            # 추가 정보가 있으면 protobuf 구조체 타입으로 변환
            "additional_info": change_struct_type(cost_data["additional_info"])
            if "additional_info" in cost_data
            else None,
            "billed_date": cost_data["billed_date"],  # 청구 날짜 (필수 필드)
        }

        # protobuf 객체 생성 및 반환
        return cost_pb2.CostInfo(**info)

    except Exception as e:
        # 디버깅을 위한 로그 출력
        _LOGGER.debug(f"[CostInfo] cost data: {cost_data}")
        _LOGGER.debug(f"[CostInfo] error reason: {e}", exc_info=True)
        raise e


def CostsInfo(costs_data, **kwargs):
    """
    여러 비용 데이터를 SpaceONE CostsInfo protobuf 객체로 변환합니다.
    
    Args:
        costs_data (list): 변환할 비용 데이터 리스트
        **kwargs: CostInfo 함수에 전달할 추가 매개변수
    
    Returns:
        cost_pb2.CostsInfo: 변환된 protobuf 객체 (여러 비용 정보 포함)
    """
    # 각 비용 데이터를 CostInfo로 변환하여 리스트로 만든 후 CostsInfo 객체 생성
    return cost_pb2.CostsInfo(
        results=list(map(functools.partial(CostInfo, **kwargs), costs_data))
    )
