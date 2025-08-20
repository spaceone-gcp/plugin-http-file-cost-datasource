"""
데이터 소스 모델 정의

이 모듈은 HTTP 파일 비용 데이터 소스 플러그인의 데이터 모델을 정의합니다.
주로 데이터 소스 규칙, 조건, 액션 등을 관리하는 스키마를 포함합니다.
"""

from schematics.models import Model
from schematics.types import ListType, DictType, StringType, BooleanType
from schematics.types.compound import ModelType

# 모델 클래스 정의
__all__ = ["PluginMetadata"]

class MatchServiceAccount(Model):
    """
    서비스 계정 매칭 정보를 정의하는 모델
    
    데이터 소스에서 특정 서비스 계정을 매칭할 때 사용되는
    소스와 타겟 정보를 포함합니다.
    """
    # 매칭할 서비스 계정의 소스 식별자
    source = StringType(required=True)
    # 매칭될 서비스 계정의 타겟 식별자
    target = StringType(required=True)


class Actions(Model):
    """
    데이터 소스 규칙에서 수행할 액션들을 정의하는 모델
    
    규칙이 조건을 만족할 때 실행될 다양한 액션들을 포함합니다.
    """
    # 서비스 계정 매칭 액션
    match_service_account = ModelType(MatchServiceAccount)


class Options(Model):
    """
    데이터 소스 규칙의 옵션 설정을 정의하는 모델
    
    규칙 처리 시의 추가적인 동작 옵션들을 포함합니다.
    """
    # 조건 만족 시 처리 중단 여부 (기본값: False)
    stop_processing = BooleanType(default=False)


class Condition(Model):
    """
    데이터 소스 규칙의 조건을 정의하는 모델
    
    규칙이 적용될지 결정하는 조건들을 정의합니다.
    """
    # 조건을 확인할 키 (필드명)
    key = StringType(required=True)
    # 비교할 값
    value = StringType(required=True)
    # 비교 연산자 (eq: 같음, contain: 포함, not: 같지 않음, not_contain: 포함되지 않음)
    operator = StringType(
        required=True, choices=["eq", "contain", "not", "not_contain"]
    )


class DataSourceRule(Model):
    """
    데이터 소스 규칙을 정의하는 모델
    
    비용 데이터를 처리할 때 적용될 규칙을 정의합니다.
    조건, 액션, 옵션 등을 포함하여 복잡한 데이터 처리 로직을 표현할 수 있습니다.
    """
    # 규칙의 고유 이름
    name = StringType(required=True)
    # 규칙 적용을 위한 조건들 (기본값: 빈 리스트)
    conditions = ListType(ModelType(Condition), default=[])
    # 조건 평가 정책 (ALL: 모든 조건 만족, ANY: 하나라도 만족, ALWAYS: 항상 적용)
    conditions_policy = StringType(required=True, choices=["ALL", "ANY", "ALWAYS"])
    # 조건 만족 시 실행할 액션들
    actions = ModelType(Actions, required=True)
    # 규칙 처리 옵션 (기본값: 빈 딕셔너리)
    options = ModelType(Options, default={})
    # 규칙에 추가할 태그들 (기본값: 빈 딕셔너리)
    tags = DictType(StringType, default={})


class PluginMetadata(Model):
    """
    플러그인 메타데이터를 정의하는 모델
    
    HTTP 파일 비용 데이터 소스 플러그인의 전체 설정 정보를 포함합니다.
    데이터 소스 규칙들과 기본 통화 설정을 관리합니다.
    """
    # 데이터 소스 처리 규칙들 (기본값: 빈 리스트)
    data_source_rules = ListType(ModelType(DataSourceRule), default=[])
    # 비용 데이터의 기본 통화 (기본값: USD)
    currency = StringType(required=True, default="USD")
