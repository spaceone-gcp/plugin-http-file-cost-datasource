"""
비용 데이터 모델 정의

이 모듈은 클라우드 비용 데이터를 표현하기 위한 Cost 모델을 정의합니다.
각 필드는 클라우드 서비스의 비용 정보를 구조화된 형태로 저장합니다.
"""

from schematics.models import Model
from schematics.types import DictType, StringType, FloatType

__all__ = ["Cost"]


class Cost(Model):
    """
    클라우드 비용 데이터를 표현하는 모델 클래스
    
    이 클래스는 다양한 클라우드 서비스(AWS, GCP, Azure 등)의 
    비용 데이터를 표준화된 형태로 저장하기 위한 스키마를 정의합니다.
    
    Attributes:
        cost (float): 실제 비용 금액 (필수)
        usage_quantity (float): 사용량 수치 (필수)
        usage_type (str): 사용 유형 (예: Compute, Storage, Network)
        usage_unit (str): 사용량 단위 (예: GB, hours, requests)
        provider (str): 클라우드 서비스 제공업체 (필수)
        region_code (str): 리소스가 위치한 지역 코드
        product (str): 사용된 제품/서비스명
        resource (str): 리소스 식별자 또는 이름
        billed_date (str): 청구 날짜 (YYYY-MM 형식, 필수)
        additional_info (dict): 추가 정보를 저장하는 딕셔너리
        tags (dict): 리소스 태그 정보를 저장하는 딕셔너리
    """
    
    # 필수 필드: 비용 금액 (소수점 포함)
    cost = FloatType(
        required=True,
        min_value=0.0,
        serialized_name="cost"
    )
    
    # 필수 필드: 사용량 수치 (소수점 포함)
    usage_quantity = FloatType(
        required=True,
        min_value=0.0,
        serialized_name="usage_quantity"
    )
    
    # 사용 유형 (예: Compute, Storage, Network, Database 등)
    usage_type = StringType(
        serialized_name="usage_type"
    )
    
    # 사용량 단위 (예: GB, hours, requests, API calls 등)
    usage_unit = StringType(
        default=None,
        serialized_name="usage_unit"
    )
    
    # 필수 필드: 클라우드 서비스 제공업체 (예: aws, gcp, azure)
    provider = StringType(
        required=True,
        serialized_name="provider"
    )
    
    # 리소스가 위치한 지역 코드 (예: us-east-1, asia-northeast1)
    region_code = StringType(
        serialized_name="region_code"
    )
    
    # 사용된 제품/서비스명 (예: EC2, Cloud Storage, Virtual Machine)
    product = StringType(
        serialized_name="product"
    )
    
    # 리소스 식별자 또는 이름 (예: i-1234567890abcdef0)
    resource = StringType(
        serialized_name="resource"
    )
    
    # 필수 필드: 청구 날짜 (YYYY-MM 형식으로 제한)
    billed_date = StringType(
        required=True,
        max_length=7,  # YYYY-MM 형식
        serialized_name="billed_date"
    )
    
    # 추가 정보를 저장하는 딕셔너리 (기본값: 빈 딕셔너리)
    additional_info = DictType(
        StringType,
        default={},
        serialized_name="additional_info"
    )
    
    # 리소스 태그 정보를 저장하는 딕셔너리 (기본값: 빈 딕셔너리)
    tags = DictType(
        StringType,
        default={},
        serialized_name="tags"
    )
    
    def __str__(self):
        """Cost 객체의 문자열 표현을 반환합니다."""
        return f"Cost(provider={self.provider}, cost={self.cost}, billed_date={self.billed_date})"
    
    def __repr__(self):
        """Cost 객체의 공식 문자열 표현을 반환합니다."""
        return self.__str__()
