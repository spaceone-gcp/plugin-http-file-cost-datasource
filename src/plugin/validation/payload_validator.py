"""
Request Payload 검증 모듈

모든 HTTP 요청 페이로드에 대한 종합적인 검증을 제공하여
보안과 안정성을 강화하는 모듈입니다.
"""

import logging
import re
from typing import Any, Dict, List, Union
from urllib.parse import urlparse

# 로거 설정
_LOGGER = logging.getLogger("spaceone")


class PayloadValidationError(Exception):
    """페이로드 검증 실패 시 발생하는 예외"""

    pass


class PayloadValidator:
    """
    Request Payload 검증을 담당하는 클래스

    다양한 입력 데이터에 대한 타입 검증, 범위 검증, 형식 검증 등을 수행합니다.
    """

    # 검증 상수
    MAX_STRING_LENGTH = 10000  # 최대 문자열 길이
    MAX_LIST_SIZE = 1000  # 최대 리스트 크기
    MAX_DICT_SIZE = 100  # 최대 딕셔너리 크기
    MAX_NESTED_DEPTH = 10  # 최대 중첩 깊이
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

    # 허용되는 URL 스키마
    ALLOWED_URL_SCHEMES = {"http", "https"}

    # 허용되는 도메인 패턴 (기본적으로 모든 도메인 허용, 필요 시 제한 가능)
    # 개발 환경에서는 localhost 접근을 허용하기 위해 localhost 관련 도메인 제거
    BLOCKED_DOMAINS = {
        # "localhost",      # 개발 환경에서 테스트를 위해 주석 처리
        # "127.0.0.1",      # 개발 환경에서 테스트를 위해 주석 처리
        # "0.0.0.0",        # 개발 환경에서 테스트를 위해 주석 처리
        # "::1",            # 개발 환경에서 테스트를 위해 주석 처리
        "169.254.169.254",  # AWS 메타데이터 서비스 (보안상 유지)
    }

    # 필드명 검증 패턴 (영숫자, 언더스코어, 하이픈, 점, 공백 허용)
    FIELD_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\s]+$")

    @staticmethod
    def validate_params(params: Any) -> Dict[str, Any]:
        """
        메인 파라미터 딕셔너리를 검증합니다.

        Args:
            params: 검증할 파라미터

        Returns:
            검증된 파라미터 딕셔너리

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        # 기본 타입 검증
        if params is None:
            raise PayloadValidationError("'params'는 None일 수 없습니다")

        if not isinstance(params, dict):
            raise PayloadValidationError(
                f"'params'는 딕셔너리여야 합니다. 현재 타입: {type(params).__name__}"
            )

        if not params:
            raise PayloadValidationError("'params'는 빈 딕셔너리일 수 없습니다")

        # 딕셔너리 크기 제한
        if len(params) > PayloadValidator.MAX_DICT_SIZE:
            raise PayloadValidationError(
                f"'params' 딕셔너리 크기가 최대값({PayloadValidator.MAX_DICT_SIZE})을 초과했습니다: {len(params)}"
            )

        # 중첩 깊이 검증
        PayloadValidator._validate_nested_depth(params, "params")

        # 딕셔너리 키 검증
        PayloadValidator._validate_dict_keys(params, "params")

        return params

    @staticmethod
    def validate_options(options: Any) -> Dict[str, Any]:
        """
        옵션 딕셔너리를 검증합니다.

        Args:
            options: 검증할 옵션

        Returns:
            검증된 옵션 딕셔너리

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if options is None:
            return {}  # options는 선택적이므로 빈 딕셔너리 반환

        if not isinstance(options, dict):
            raise PayloadValidationError(
                f"'options'는 딕셔너리여야 합니다. 현재 타입: {type(options).__name__}"
            )

        # 빈 딕셔너리도 허용 (options는 선택적 필드)

        # base_url 검증
        if "base_url" in options:
            PayloadValidator.validate_base_url(options["base_url"])

        # field_mapper 검증
        if "field_mapper" in options:
            PayloadValidator.validate_field_mapper(options["field_mapper"])

        # default_vars 검증
        if "default_vars" in options:
            PayloadValidator.validate_default_vars(options["default_vars"])

        # type_mapper 검증
        if "type_mapper" in options:
            PayloadValidator.validate_type_mapper(options["type_mapper"])

        return options

    @staticmethod
    def validate_secret_data(secret_data: Any) -> Dict[str, Any]:
        """
        시크릿 데이터를 검증합니다.

        Args:
            secret_data: 검증할 시크릿 데이터

        Returns:
            검증된 시크릿 데이터

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if secret_data is None:
            raise PayloadValidationError("'secret_data'는 None일 수 없습니다")

        if not isinstance(secret_data, dict):
            raise PayloadValidationError(
                f"'secret_data'는 딕셔너리여야 합니다. 현재 타입: {type(secret_data).__name__}"
            )

        if not secret_data:
            raise PayloadValidationError("'secret_data'는 빈 딕셔너리일 수 없습니다")

        # private_key 검증 (Google Cloud 인증용)
        if "private_key" in secret_data:
            PayloadValidator.validate_private_key(secret_data["private_key"])

        return secret_data

    @staticmethod
    def validate_task_options(task_options: Any) -> Dict[str, Any]:
        """
        작업 옵션을 검증합니다.

        Args:
            task_options: 검증할 작업 옵션

        Returns:
            검증된 작업 옵션

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if task_options is None:
            return {}  # task_options는 선택적이므로 빈 딕셔너리 반환

        if not isinstance(task_options, dict):
            raise PayloadValidationError(
                f"'task_options'는 딕셔너리여야 합니다. 현재 타입: {type(task_options).__name__}"
            )

        # base_url 검증
        if "base_url" in task_options:
            PayloadValidator.validate_base_url(task_options["base_url"])

        # bucket_name 검증
        if "bucket_name" in task_options:
            PayloadValidator.validate_bucket_name(task_options["bucket_name"])

        return task_options

    @staticmethod
    def validate_domain_id(domain_id: Any) -> str:
        """
        도메인 ID를 검증합니다.

        Args:
            domain_id: 검증할 도메인 ID

        Returns:
            검증된 도메인 ID

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if domain_id is None:
            raise PayloadValidationError("'domain_id'는 None일 수 없습니다")

        if not isinstance(domain_id, str):
            raise PayloadValidationError(
                f"'domain_id'는 문자열이어야 합니다. 현재 타입: {type(domain_id).__name__}"
            )

        if not domain_id.strip():
            raise PayloadValidationError("'domain_id'는 빈 문자열일 수 없습니다")

        if len(domain_id) > 100:
            raise PayloadValidationError(
                f"'domain_id' 길이가 최대값(100)을 초과했습니다: {len(domain_id)}"
            )

        return domain_id.strip()

    @staticmethod
    def validate_base_url(base_url: Any) -> Union[str, List[str]]:
        """
        Base URL을 검증합니다.

        Args:
            base_url: 검증할 base URL (문자열 또는 문자열 리스트)

        Returns:
            검증된 base URL

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if base_url is None:
            raise PayloadValidationError("'base_url'은 None일 수 없습니다")

        # 단일 URL인 경우
        if isinstance(base_url, str):
            return PayloadValidator._validate_single_url(base_url)

        # URL 리스트인 경우
        if isinstance(base_url, list):
            if not base_url:
                raise PayloadValidationError("'base_url' 리스트는 비어있을 수 없습니다")

            if len(base_url) > 10:  # 최대 10개 URL 허용
                raise PayloadValidationError(
                    f"'base_url' 리스트 크기가 최대값(10)을 초과했습니다: {len(base_url)}"
                )

            validated_urls = []
            for i, url in enumerate(base_url):
                try:
                    validated_url = PayloadValidator._validate_single_url(url)
                    validated_urls.append(validated_url)
                except PayloadValidationError as e:
                    raise PayloadValidationError(f"base_url[{i}] 검증 실패: {e}") from e

            return validated_urls

        raise PayloadValidationError(
            f"'base_url'은 문자열 또는 문자열 리스트여야 합니다. 현재 타입: {type(base_url).__name__}"
        )

    @staticmethod
    def _validate_single_url(url: str) -> str:
        """단일 URL을 검증합니다."""
        if not isinstance(url, str):
            raise PayloadValidationError(
                f"URL은 문자열이어야 합니다. 현재 타입: {type(url).__name__}"
            )

        url = url.strip()
        if not url:
            raise PayloadValidationError("URL은 빈 문자열일 수 없습니다")

        if len(url) > 2000:  # URL 길이 제한
            raise PayloadValidationError(
                f"URL 길이가 최대값(2000)을 초과했습니다: {len(url)}"
            )

        try:
            parsed = urlparse(url)
        except Exception as e:
            raise PayloadValidationError(f"유효하지 않은 URL 형식입니다: {e}") from e

        # 스키마 검증
        if parsed.scheme not in PayloadValidator.ALLOWED_URL_SCHEMES:
            raise PayloadValidationError(
                f"허용되지 않는 URL 스키마입니다: {parsed.scheme}. "
                f"허용되는 스키마: {', '.join(PayloadValidator.ALLOWED_URL_SCHEMES)}"
            )

        # 호스트 검증
        if not parsed.netloc:
            raise PayloadValidationError("URL에 호스트 정보가 없습니다")

        # 차단된 도메인 검증
        hostname = parsed.hostname
        if hostname and hostname.lower() in PayloadValidator.BLOCKED_DOMAINS:
            raise PayloadValidationError(f"차단된 도메인입니다: {hostname}")

        return url

    @staticmethod
    def validate_bucket_name(bucket_name: Any) -> str:
        """
        Google Cloud Storage 버킷명을 검증합니다.

        Args:
            bucket_name: 검증할 버킷명

        Returns:
            검증된 버킷명

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if bucket_name is None:
            raise PayloadValidationError("'bucket_name'은 None일 수 없습니다")

        if not isinstance(bucket_name, str):
            raise PayloadValidationError(
                f"'bucket_name'은 문자열이어야 합니다. 현재 타입: {type(bucket_name).__name__}"
            )

        bucket_name = bucket_name.strip()
        if not bucket_name:
            raise PayloadValidationError("'bucket_name'은 빈 문자열일 수 없습니다")

        # Google Cloud Storage 버킷명 규칙 검증
        if len(bucket_name) < 3 or len(bucket_name) > 63:
            raise PayloadValidationError(
                f"'bucket_name' 길이는 3-63자여야 합니다: {len(bucket_name)}"
            )

        # 소문자, 숫자, 하이픈만 허용
        if not re.match(r"^[a-z0-9\-]+$", bucket_name):
            raise PayloadValidationError(
                "'bucket_name'은 소문자, 숫자, 하이픈만 포함할 수 있습니다"
            )

        # 하이픈으로 시작하거나 끝날 수 없음
        if bucket_name.startswith("-") or bucket_name.endswith("-"):
            raise PayloadValidationError(
                "'bucket_name'은 하이픈으로 시작하거나 끝날 수 없습니다"
            )

        return bucket_name

    @staticmethod
    def validate_private_key(private_key: Any) -> str:
        """
        PEM 형식의 private key를 검증합니다.

        Args:
            private_key: 검증할 private key

        Returns:
            검증된 private key

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if private_key is None:
            raise PayloadValidationError("'private_key'는 None일 수 없습니다")

        if not isinstance(private_key, str):
            raise PayloadValidationError(
                f"'private_key'는 문자열이어야 합니다. 현재 타입: {type(private_key).__name__}"
            )

        private_key = private_key.strip()
        if not private_key:
            raise PayloadValidationError("'private_key'는 빈 문자열일 수 없습니다")

            # PEM 형식 기본 검증
        if not private_key.startswith("-----BEGIN PRIVATE KEY-----"):
            raise PayloadValidationError(
                "유효하지 않은 PEM 형식입니다: '-----BEGIN PRIVATE KEY-----'로 시작해야 합니다"
            )

        if not private_key.endswith("-----END PRIVATE KEY-----"):
            raise PayloadValidationError(
                "유효하지 않은 PEM 형식입니다: '-----END PRIVATE KEY-----'로 끝나야 합니다"
            )

        # 길이 제한 (일반적인 RSA 키 기준)
        if len(private_key) > 10000:
            raise PayloadValidationError(
                f"'private_key' 길이가 최대값(10000)을 초과했습니다: {len(private_key)}"
            )

        return private_key

    @staticmethod
    def validate_field_mapper(field_mapper: Any) -> Dict[str, Any]:
        """
        필드 매퍼를 검증합니다.

        Args:
            field_mapper: 검증할 필드 매퍼

        Returns:
            검증된 필드 매퍼

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if field_mapper is None:
            return {}

        if not isinstance(field_mapper, dict):
            raise PayloadValidationError(
                f"'field_mapper'는 딕셔너리여야 합니다. 현재 타입: {type(field_mapper).__name__}"
            )

        # 딕셔너리 크기 제한
        if len(field_mapper) > 50:
            raise PayloadValidationError(
                f"'field_mapper' 크기가 최대값(50)을 초과했습니다: {len(field_mapper)}"
            )

        # 키와 값 검증
        for key, value in field_mapper.items():
            if not isinstance(key, str):
                raise PayloadValidationError(
                    f"field_mapper 키는 문자열이어야 합니다: {type(key).__name__}"
                )

            if not PayloadValidator.FIELD_NAME_PATTERN.match(key):
                raise PayloadValidationError(f"유효하지 않은 필드명입니다: {key}")

            if isinstance(value, str):
                if not PayloadValidator.FIELD_NAME_PATTERN.match(value):
                    raise PayloadValidationError(f"유효하지 않은 필드명입니다: {value}")
            elif isinstance(value, dict):
                # additional_info 등의 중첩 매핑
                PayloadValidator.validate_field_mapper(value)
            else:
                raise PayloadValidationError(
                    f"field_mapper 값은 문자열 또는 딕셔너리여야 합니다: {type(value).__name__}"
                )

        return field_mapper

    @staticmethod
    def validate_default_vars(default_vars: Any) -> Dict[str, Any]:
        """
        기본 변수를 검증합니다.

        Args:
            default_vars: 검증할 기본 변수

        Returns:
            검증된 기본 변수

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if default_vars is None:
            return {}

        if not isinstance(default_vars, dict):
            raise PayloadValidationError(
                f"'default_vars'는 딕셔너리여야 합니다. 현재 타입: {type(default_vars).__name__}"
            )

        # 딕셔너리 크기 제한
        if len(default_vars) > 20:
            raise PayloadValidationError(
                f"'default_vars' 크기가 최대값(20)을 초과했습니다: {len(default_vars)}"
            )

        # 키 검증
        for key in default_vars.keys():
            if not isinstance(key, str):
                raise PayloadValidationError(
                    f"default_vars 키는 문자열이어야 합니다: {type(key).__name__}"
                )

        return default_vars

    @staticmethod
    def validate_type_mapper(type_mapper: Any) -> Dict[str, Any]:
        """
        타입 매퍼를 검증합니다.

        Args:
            type_mapper: 검증할 타입 매퍼

        Returns:
            검증된 타입 매퍼

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if type_mapper is None:
            return {}

        if not isinstance(type_mapper, dict):
            raise PayloadValidationError(
                f"'type_mapper'는 딕셔너리여야 합니다. 현재 타입: {type(type_mapper).__name__}"
            )

        return type_mapper

    @staticmethod
    def _validate_nested_depth(obj: Any, path: str, current_depth: int = 0) -> None:
        """중첩된 구조의 깊이를 검증합니다."""
        if current_depth > PayloadValidator.MAX_NESTED_DEPTH:
            raise PayloadValidationError(
                f"중첩 깊이가 최대값({PayloadValidator.MAX_NESTED_DEPTH})을 초과했습니다: {path}"
            )

        if isinstance(obj, dict):
            for key, value in obj.items():
                PayloadValidator._validate_nested_depth(
                    value, f"{path}.{key}", current_depth + 1
                )
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                PayloadValidator._validate_nested_depth(
                    item, f"{path}[{i}]", current_depth + 1
                )

    @staticmethod
    def _validate_dict_keys(obj: Dict[str, Any], path: str) -> None:
        """딕셔너리 키의 유효성을 검증합니다."""
        for key in obj.keys():
            if not isinstance(key, str):
                raise PayloadValidationError(
                    f"딕셔너리 키는 문자열이어야 합니다: {path}.{key} (타입: {type(key).__name__})"
                )

            if len(key) > 100:
                raise PayloadValidationError(
                    f"딕셔너리 키 길이가 최대값(100)을 초과했습니다: {path}.{key}"
                )

    @staticmethod
    def validate_string_field(
        value: Any, field_name: str, max_length: int = None
    ) -> str:
        """
        문자열 필드를 검증합니다.

        Args:
            value: 검증할 값
            field_name: 필드명
            max_length: 최대 길이 (기본값: MAX_STRING_LENGTH)

        Returns:
            검증된 문자열

        Raises:
            PayloadValidationError: 검증 실패 시
        """
        if value is None:
            raise PayloadValidationError(f"'{field_name}'은 None일 수 없습니다")

        if not isinstance(value, str):
            raise PayloadValidationError(
                f"'{field_name}'은 문자열이어야 합니다. 현재 타입: {type(value).__name__}"
            )

        value = value.strip()
        if not value:
            raise PayloadValidationError(f"'{field_name}'은 빈 문자열일 수 없습니다")

        max_len = max_length or PayloadValidator.MAX_STRING_LENGTH
        if len(value) > max_len:
            raise PayloadValidationError(
                f"'{field_name}' 길이가 최대값({max_len})을 초과했습니다: {len(value)}"
            )

        return value
