"""
비용 데이터 모델 정의

이 모듈은 클라우드 비용 데이터를 표현하기 위한 Cost 모델을 정의합니다.
각 필드는 클라우드 서비스의 비용 정보를 구조화된 형태로 저장합니다.
"""

from schematics.models import Model
from schematics.types import DictType, FloatType, ListType, StringType

__all__ = ["Cost", "GoogleCloudBillingCost"]


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
    cost = FloatType(required=True, min_value=0.0, serialized_name="cost")

    # 필수 필드: 사용량 수치 (소수점 포함)
    usage_quantity = FloatType(
        required=True, min_value=0.0, serialized_name="usage_quantity"
    )

    # 사용 유형 (예: Compute, Storage, Network, Database 등)
    usage_type = StringType(serialized_name="usage_type")

    # 사용량 단위 (예: GB, hours, requests, API calls 등)
    usage_unit = StringType(default=None, serialized_name="usage_unit")

    # 필수 필드: 클라우드 서비스 제공업체 (예: aws, gcp, azure)
    provider = StringType(required=True, serialized_name="provider")

    # 리소스가 위치한 지역 코드 (예: us-east-1, asia-northeast1)
    region_code = StringType(serialized_name="region_code")

    # 사용된 제품/서비스명 (예: EC2, Cloud Storage, Virtual Machine)
    product = StringType(serialized_name="product")

    # 리소스 식별자 또는 이름 (예: i-1234567890abcdef0)
    resource = StringType(serialized_name="resource")

    # 필수 필드: 청구 날짜 (YYYY-MM-DD 형식으로 제한)
    billed_date = StringType(
        required=True,
        max_length=10,  # YYYY-MM-DD 형식
        serialized_name="billed_date",
    )

    # 추가 정보를 저장하는 딕셔너리 (기본값: 빈 딕셔너리)
    additional_info = DictType(
        StringType, default={}, serialized_name="additional_info"
    )

    # 리소스 태그 정보를 저장하는 딕셔너리 (기본값: 빈 딕셔너리)
    tags = DictType(StringType, default={}, serialized_name="tags")

    def __str__(self):
        """Cost 객체의 문자열 표현을 반환합니다."""
        return f"Cost(provider={self.provider}, cost={self.cost}, billed_date={self.billed_date})"

    def __repr__(self):
        """Cost 객체의 공식 문자열 표현을 반환합니다."""
        return self.__str__()


class GoogleCloudBillingCost(Cost):
    """
    Google Cloud Billing 전용 비용 데이터 모델 클래스

    Google Cloud Billing Export 스키마에 맞춰 모든 필드를 지원하는 모델입니다.
    Google Cloud Billing 문서에 명시된 모든 필드를 포함합니다.

    Attributes:
        billing_account_id (str): Cloud Billing 계정 ID
        invoice_month (str): 인보이스 월 (YYYYMM 형식)
        invoice_publisher_type (str): 게시자 유형 (GOOGLE, PARTNER)
        cost_type (str): 비용 유형 (regular, tax, adjustment 등)
        service_id (str): 서비스 ID
        service_description (str): 서비스 설명
        sku_id (str): SKU ID
        sku_description (str): SKU 설명
        usage_start_time (str): 사용 시작 시간
        usage_end_time (str): 사용 종료 시간
        project_id (str): 프로젝트 ID
        project_number (str): 프로젝트 번호
        project_name (str): 프로젝트 이름
        project_ancestry_numbers (str): 프로젝트 계층 구조 번호
        location_location (str): 위치 (멀티 리전, 국가, 리전, 영역)
        location_country (str): 국가 코드
        location_region (str): 리전 코드
        location_zone (str): 영역 코드
        currency (str): 통화 코드
        currency_conversion_rate (float): 환율
        usage_amount (float): 사용량
        usage_unit (str): 사용량 단위
        usage_amount_in_pricing_units (float): 가격 책정 단위 사용량
        usage_pricing_unit (str): 가격 책정 단위
        credits (list): 크레딧 정보 리스트
        adjustment_info (dict): 조정 정보
        export_time (str): 내보내기 시간
        cost_at_list (float): 정가 비용
        transaction_type (str): 거래 유형
        seller_name (str): 판매자 이름
    """

    # Google Cloud Billing 전용 필드들
    billing_account_id = StringType(serialized_name="billing_account_id")
    invoice_month = StringType(serialized_name="invoice.month")
    invoice_publisher_type = StringType(serialized_name="invoice.publisher_type")
    cost_type = StringType(serialized_name="cost_type")

    # 서비스 정보
    service_id = StringType(serialized_name="service.id")
    service_description = StringType(serialized_name="service.description")
    sku_id = StringType(serialized_name="sku.id")
    sku_description = StringType(serialized_name="sku.description")

    # 사용 시간 정보
    usage_start_time = StringType(serialized_name="usage_start_time")
    usage_end_time = StringType(serialized_name="usage_end_time")

    # 프로젝트 정보
    project_id = StringType(serialized_name="project.id")
    project_number = StringType(serialized_name="project.number")
    project_name = StringType(serialized_name="project.name")
    project_ancestry_numbers = StringType(serialized_name="project.ancestry_numbers")

    # 위치 정보
    location_location = StringType(serialized_name="location.location")
    location_country = StringType(serialized_name="location.country")
    location_region = StringType(serialized_name="location.region")
    location_zone = StringType(serialized_name="location.zone")

    # 비용 및 통화 정보
    currency = StringType(serialized_name="currency")
    currency_conversion_rate = FloatType(serialized_name="currency_conversion_rate")

    # 사용량 정보
    usage_amount = FloatType(serialized_name="usage.amount")
    usage_amount_in_pricing_units = FloatType(
        serialized_name="usage.amount_in_pricing_units"
    )
    usage_pricing_unit = StringType(serialized_name="usage.pricing_unit")

    # 크레딧 정보
    credits = ListType(DictType(StringType), default=[], serialized_name="credits")

    # 조정 정보
    adjustment_info = DictType(
        StringType, default={}, serialized_name="adjustment_info"
    )

    # 기타 정보
    export_time = StringType(serialized_name="export_time")
    cost_at_list = FloatType(serialized_name="cost_at_list")
    transaction_type = StringType(serialized_name="transaction_type")
    seller_name = StringType(serialized_name="seller_name")

    # 라벨 및 태그 정보 (기존 Cost 모델에서 확장)
    project_labels = DictType(StringType, default={}, serialized_name="project.labels")
    labels = DictType(StringType, default={}, serialized_name="labels")
    system_labels = DictType(StringType, default={}, serialized_name="system_labels")
    tags = DictType(StringType, default={}, serialized_name="tags")

    def __str__(self):
        """GoogleCloudBillingCost 객체의 문자열 표현을 반환합니다."""
        return f"GoogleCloudBillingCost(billing_account_id={self.billing_account_id}, project_id={self.project_id}, cost={self.cost})"

    def __repr__(self):
        """GoogleCloudBillingCost 객체의 공식 문자열 표현을 반환합니다."""
        return self.__str__()
