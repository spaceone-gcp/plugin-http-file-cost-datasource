import logging
import time
from decimal import Decimal
from typing import Any, Dict, Generator, List, Optional

from dateutil.parser import parse
from spaceone.core.manager import BaseManager

from plugin.connector.google_storage_collector import (
    GoogleStorageConnector,
)
from plugin.connector.http_file_connector import HTTPFileConnector
from plugin.error.cost import ERROR_EMPTY_BILLED_DATE

# 로거 설정
_LOGGER = logging.getLogger("spaceone")


class CostDataProcessingError(Exception):
    """비용 데이터 처리 중 발생하는 예외"""

    pass


class CostManagerConfig:
    """CostManager 설정 상수 클래스"""

    REQUIRED_FIELDS = []  # 필수 필드 목록
    DEFAULT_DAY = "01"  # 기본 날짜
    INVOICE_MONTH_LENGTH = 6  # 청구 월 길이
    YEAR_START_INDEX = 0  # 연도 시작 인덱스
    YEAR_END_INDEX = 4  # 연도 종료 인덱스
    MONTH_START_INDEX = 4  # 월 시작 인덱스
    MONTH_END_INDEX = 6  # 월 종료 인덱스
    CSV_PROVIDER = "csv"  # CSV 파일 제공자
    DATE_FORMAT = "%Y-%m-%d"  # 날짜 형식
    ACCOUNT_ID_PADDING_LENGTH = 12  # 계정 ID 패딩 길이


class CostManager(BaseManager):
    """
    비용 데이터를 관리하는 매니저 클래스

    HTTP 파일이나 Google Cloud Storage에서 비용 데이터를 수집하고,
    SpaceONE에서 요구하는 포맷으로 변환하는 역할을 담당합니다.
    """

    def __init__(self, *args, **kwargs):
        """
        CostManager 초기화

        Args:
            *args: 부모 클래스 인자
            **kwargs: 부모 클래스 키워드 인자
        """
        super().__init__(*args, **kwargs)
        self.default_vars: Optional[Dict[str, Any]] = None  # 기본 변수 설정
        self.field_mapper: Optional[Dict[str, Any]] = None  # 필드 매핑 설정
        self.type_mapper: Optional[Dict[str, Any]] = None  # 타입 매핑 설정

    def get_data(
        self,
        options: Dict[
            str, Any
        ],  # 플러그인 옵션 (base_url, field_mapper, default_vars, type_mapper 등)
        secret_data: Dict[str, Any],  # 인증 정보
        schema: Optional[str],  # 스키마 정보 (선택)
        task_options: Optional[
            Dict[str, Any]
        ],  # 작업별 옵션 (base_url 또는 bucket_name)
    ) -> Generator[Dict[str, List[Dict[str, Any]]], None, None]:  # 비용 데이터 리스트
        """
        외부 비용 데이터를 수집하여 SpaceONE 비용 데이터 포맷으로 변환하는 메인 함수

        이 함수는 HTTP 파일 또는 Google Cloud Storage에서 비용 데이터를 읽어와
        SpaceONE에서 요구하는 포맷으로 변환하여 제너레이터로 반환합니다.

        Args:
            options: 플러그인 옵션 (base_url, field_mapper, default_vars, type_mapper 등)
            secret_data: 인증 정보
            schema: 스키마 정보 (선택)
            task_options: 작업별 옵션 (base_url 또는 bucket_name)

        Yields:
            {"results": [비용 데이터 리스트]}

        Raises:
            ValueError: 데이터 소스 정보가 없을 때
            CostDataProcessingError: 데이터 처리 중 오류 발생 시
        """
        _LOGGER.info("비용 데이터 수집 시작")
        start_time = time.time()  # 시작 시간 기록

        try:
            self._setup_mappers(options)  # 매퍼 설정
            task_options = task_options or {}  # 작업별 옵션 설정

            response_stream = self._get_data_stream(
                options, secret_data, schema, task_options
            )  # 데이터 스트림 생성

            total_processed_count = 0  # 처리된 데이터 개수 초기화
            for results in response_stream:  # 데이터 스트림 순회
                costs_data = self._make_cost_data(results, options)  # 비용 데이터 생성
                total_processed_count += len(costs_data)  # 처리된 데이터 개수 업데이트
                yield {"results": costs_data}  # 비용 데이터 반환

            duration = time.time() - start_time  # 소요 시간 계산
            _LOGGER.info(
                f"비용 데이터 수집 완료: {total_processed_count}개 처리, {duration:.2f}초 소요"
            )

        except Exception as e:  # 예외 처리
            _LOGGER.error(f"비용 데이터 수집 중 오류 발생: {e}", exc_info=True)
            raise CostDataProcessingError(f"데이터 수집 실패: {e}") from e

    def _setup_mappers(self, options: Dict[str, Any]) -> None:
        """매퍼 설정을 초기화합니다."""
        if "default_vars" in options:  # default_vars 옵션이 있으면 설정
            self.default_vars = options["default_vars"]
        if "field_mapper" in options:  # field_mapper 옵션이 있으면 설정
            self.field_mapper = options["field_mapper"]
            self._validate_field_mapper_completeness()  # 필수 필드 매핑 검증
        if "type_mapper" in options:  # type_mapper 옵션이 있으면 설정
            self.type_mapper = options["type_mapper"]

    def _validate_field_mapper_completeness(self) -> None:
        """field_mapper 설정에서 필수 필드 매핑이 모두 포함되어 있는지 검증합니다."""
        if not self.field_mapper:
            _LOGGER.warning(
                "field_mapper가 설정되지 않았습니다. 원본 데이터에 필수 필드가 직접 포함되어 있어야 합니다."
            )
            return

        missing_fields = []  # 누락된 필드 목록
        for required_field in CostManagerConfig.REQUIRED_FIELDS:  # 필수 필드 순회
            if (
                required_field not in self.field_mapper
            ):  # 필수 필드가 매핑되지 않은 경우
                missing_fields.append(required_field)  # 누락된 필드 추가

        if missing_fields:  # 누락된 필드가 있는 경우
            _LOGGER.warning(
                f"field_mapper에 다음 필수 필드 매핑이 누락되었습니다: {missing_fields}. "
                f"원본 데이터에 해당 필드가 직접 포함되어 있거나 default_vars로 설정되어 있는지 확인하세요."
            )

    def _get_data_stream(
        self,
        options: Dict[
            str, Any
        ],  # 플러그인 옵션 (base_url, field_mapper, default_vars, type_mapper 등)
        secret_data: Dict[str, Any],  # 인증 정보
        schema: Optional[str],  # 스키마 정보 (선택)
        task_options: Dict[str, Any],  # 작업별 옵션 (base_url 또는 bucket_name)
    ) -> Generator[List[Dict[str, Any]], None, None]:
        """데이터 소스에 따른 스트림 생성 로직을 분리합니다."""
        if "base_url" in task_options:  # base_url 옵션이 있으면 HTTP 스트림 생성
            return self._get_http_stream(
                options, secret_data, schema, task_options["base_url"]
            )
        elif (
            "bucket_name" in task_options
        ):  # bucket_name 옵션이 있으면 Google Cloud Storage 스트림 생성
            return self._get_storage_stream(options, secret_data, schema, task_options)
        elif "base_url" in options:  # base_url 옵션이 있으면 HTTP 스트림 생성
            return self._get_http_stream(
                options, secret_data, schema, options["base_url"]
            )
        else:  # 데이터 소스 정보가 없으면 오류 발생
            raise ValueError(
                "데이터 소스 정보가 필요합니다 (base_url 또는 bucket_name)"
            )

    def _get_http_stream(
        self,
        options: Dict[
            str, Any
        ],  # 플러그인 옵션 (base_url, field_mapper, default_vars, type_mapper 등)
        secret_data: Dict[str, Any],  # 인증 정보
        schema: Optional[str],  # 스키마 정보 (선택)
        base_url: str,  # 기본 URL
    ) -> Generator[List[Dict[str, Any]], None, None]:
        """HTTP 파일에서 데이터 스트림을 생성합니다.

        Args:
            options: 플러그인 옵션 (base_url, field_mapper, default_vars, type_mapper 등)
            secret_data: 인증 정보
            schema: 스키마 정보 (선택)
            base_url: 기본 URL
        """
        http_file_connector = self.locator.get_connector(
            HTTPFileConnector
        )  # HTTPFileConnector 인스턴스 생성
        http_file_connector.create_session(options, secret_data, schema)  # 세션 생성
        return http_file_connector.get_cost_data(base_url)  # 데이터 스트림 반환

    def _get_storage_stream(
        self,
        options: Dict[
            str, Any
        ],  # 플러그인 옵션 (base_url, field_mapper, default_vars, type_mapper 등)
        secret_data: Dict[str, Any],  # 인증 정보
        schema: Optional[str],  # 스키마 정보 (선택)
        task_options: Dict[str, Any],  # 작업별 옵션 (base_url 또는 bucket_name)
    ) -> Generator[List[Dict[str, Any]], None, None]:
        """Google Cloud Storage에서 데이터 스트림을 생성합니다."""
        storage_connector = self.locator.get_connector(
            GoogleStorageConnector, secret_data=secret_data
        )  # GoogleStorageConnector 인스턴스 생성
        storage_connector.create_session(options, secret_data, schema)  # 세션 생성
        return storage_connector.get_cost_data(task_options)  # 데이터 스트림 반환

    def _make_cost_data(
        self, results: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        입력된 원본 비용 데이터를 SpaceONE 비용 데이터 포맷에 맞게 변환합니다.

        Args:
            results: 원본 비용 데이터 리스트
            options: 플러그인 옵션 (cost_metric 등)

        Returns:
            SpaceONE 비용 데이터 포맷으로 변환된 리스트

        Raises:
            CostDataProcessingError: 데이터 변환 중 오류 발생 시
        """
        costs_data = []

        for result in results:  # 결과 순회
            try:
                processed_result = self._process_single_result(
                    result, options
                )  # 단일 결과 처리
                costs_data.append(processed_result)  # 처리된 결과 추가
            except Exception as e:  # 예외 처리
                _LOGGER.error(f"개별 결과 처리 중 오류: {e}", exc_info=True)
                raise CostDataProcessingError(f"결과 처리 실패: {e}") from e

        return costs_data

    def _process_single_result(
        self, result: Dict[str, Any], options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """단일 결과를 처리합니다."""
        # 데이터 정제
        result = self._clean_data(result)

        # 매퍼 적용
        if self.field_mapper:  # field_mapper 설정이 있으면 적용
            result = self._apply_field_mapper(result)
        if self.default_vars:  # default_vars 설정이 있으면 적용
            self._apply_default_vars(result)
        if self.type_mapper:  # type_mapper 설정이 있으면 적용
            self._apply_type_mapper(result)

        # 날짜 처리
        self._process_billed_date(result)  # billed_date 처리

        # 필수 필드 검증
        self._validate_required_fields(result)  # 필수 필드 검증

        # 최종 데이터 생성
        return self._create_final_data(result, options)  # 최종 데이터 생성

    def _clean_data(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """데이터를 정제합니다."""
        result = self._apply_strip_to_dict_keys(result)  # 키 정제
        result = self._apply_strip_to_dict_values(result)  # 값 정제
        return result

    @staticmethod
    def _apply_strip_to_dict_keys(result: Dict[str, Any]) -> Dict[str, Any]:
        """딕셔너리의 모든 키에 strip()을 적용합니다."""
        for key in list(result.keys()):  # 키 순회
            new_key = key.strip()  # 키 정제
            if new_key != key:  # 키 변경 시
                result[new_key] = result[key]  # 키 변경
                del result[key]  # 원본 키 삭제
        return result

    @staticmethod
    def _apply_strip_to_dict_values(result: Dict[str, Any]) -> Dict[str, Any]:
        """딕셔너리의 모든 문자열 값에 strip()을 적용합니다."""
        for key, value in result.items():  # 키와 값 순회
            if isinstance(value, str):  # 문자열 타입인 경우
                result[key] = value.strip()  # 값 정제
        return result

    def _apply_field_mapper(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """field_mapper 설정에 따라 필드를 변환합니다."""
        self._validate_field_mapping_consistency(result)  # 매핑 일치성 검증

        for origin_field, actual_field in self.field_mapper.items():  # 필드 매핑 순회
            if isinstance(actual_field, str):  # 필드 타입 확인
                if actual_field in result:  # 필드 존재 확인
                    result[origin_field] = result[actual_field]  # 필드 변경
                    # 원본 필드는 삭제하지 않고 유지 (다른 매핑에서 사용할 수 있음)
            elif origin_field == "additional_info":  # additional_info 필드 매핑 처리
                result = self._process_additional_info_mapping(
                    result, actual_field
                )  # additional_info 필드 매핑 처리
        return result

    def _validate_field_mapping_consistency(self, result: Dict[str, Any]) -> None:
        """field_mapper 설정과 원본 데이터의 일치성을 검증합니다."""
        if not self.field_mapper:  # field_mapper 설정이 없는 경우
            return

        missing_source_fields = []  # 누락된 원본 필드 목록
        available_fields = list(result.keys())  # 사용 가능한 필드 목록

        for target_field, source_field in self.field_mapper.items():  # 필드 매핑 순회
            if isinstance(source_field, str):  # 단순 문자열 매핑인 경우
                if (
                    source_field not in result
                ):  # 원본 필드가 데이터에 존재하지 않는 경우
                    missing_source_fields.append(
                        (target_field, source_field)
                    )  # 누락된 원본 필드 추가

        if missing_source_fields:  # 누락된 원본 필드가 있는 경우
            error_message = (
                "field_mapper에 설정된 원본 필드가 데이터에 존재하지 않습니다: "
            )
            missing_info = [
                f"{target} <- {source}" for target, source in missing_source_fields
            ]  # 누락된 원본 필드 정보
            error_message += f"{missing_info}. "  # 누락된 원본 필드 정보 추가
            error_message += (
                f"사용 가능한 필드: {available_fields}. "  # 사용 가능한 필드 정보 추가
            )
            error_message += (
                "field_mapper 설정을 확인하거나 원본 데이터의 필드명을 확인하세요."
            )

            # _LOGGER.warning(error_message)

    def _process_additional_info_mapping(
        self,
        result: Dict[str, Any],  # 데이터
        additional_mapping: Dict[str, str],  # 추가 매핑 정보
    ) -> Dict[str, Any]:
        """additional_info 필드 매핑을 처리합니다."""
        additional_info = {}  # 추가 매핑 정보 초기화
        for origin_field, actual_field in additional_mapping.items():  # 추가 매핑 순회
            if actual_field in result:  # 필드 존재 확인
                additional_info[origin_field] = result[
                    actual_field
                ]  # 추가 매핑 정보 추가
                del result[actual_field]  # 원본 필드 삭제
        result["additional_info"] = additional_info  # 추가 매핑 정보 적용
        return result

    def _apply_default_vars(self, result: Dict[str, Any]) -> None:
        """default_vars 설정에 따라 기본값을 적용합니다."""
        for key, value in self.default_vars.items():  # default_vars 순회
            result[key] = value  # 기본값 적용

    def _apply_type_mapper(self, result: Dict[str, Any]) -> None:
        """type_mapper 설정에 따라 데이터 타입을 변환합니다."""
        if "additional_info" in self.type_mapper:  # additional_info 필드 매핑 처리
            self._process_account_id_mapping(result)  # Account ID 매핑 처리

    def _process_account_id_mapping(self, result: Dict[str, Any]) -> None:
        """Account ID 매핑을 처리합니다."""
        type_mapper_info = self.type_mapper["additional_info"]  # 타입 매핑 정보
        if (
            "Account ID" in type_mapper_info  # Account ID 확인
            and "additional_info" in result  # additional_info 필드 확인
            and "Account ID" in result.get("additional_info", {})
        ):  # Account ID 확인
            account_id = result["additional_info"]["Account ID"]  # Account ID 추출
            if isinstance(account_id, (int, float)):
                result["additional_info"]["Account ID"] = str(account_id).zfill(
                    CostManagerConfig.ACCOUNT_ID_PADDING_LENGTH
                )  # Account ID 패딩 처리

    def _process_billed_date(self, result: Dict[str, Any]) -> None:
        """billed_date 필드를 처리합니다."""
        date_processors = [
            self._process_existing_billed_date,  # 기존 billed_date 필드 처리
            self._process_usage_start_time,  # usage_start_time 필드 처리
            self._process_invoice_month,  # invoice.month 필드 처리
            self._process_year_month,  # year, month 필드 처리
        ]

        for processor in date_processors:  # 날짜 처리 순회
            if processor(result):  # 날짜 처리 수행
                return  # 날짜 처리 완료

        _LOGGER.error(f"유효한 날짜 필드를 찾을 수 없습니다: {result}")
        raise ERROR_EMPTY_BILLED_DATE(result=result)

    def _process_existing_billed_date(self, result: Dict[str, Any]) -> bool:
        """기존 billed_date 필드를 처리합니다."""
        if result.get("billed_date"):  # billed_date 필드 확인
            billed_date = result["billed_date"]  # billed_date 추출
            if billed_date is not None:  # billed_date 값 확인
                parsed_date = self._parse_date(billed_date)  # 날짜 파싱
                result["billed_date"] = parsed_date.strftime(
                    CostManagerConfig.DATE_FORMAT
                )  # 날짜 형식 변환
            return True
        return False

    def _process_usage_start_time(self, result: Dict[str, Any]) -> bool:
        """usage_start_time 필드를 처리합니다."""
        if "usage_start_time" in result:  # usage_start_time 필드 확인
            usage_start_time = result["usage_start_time"]  # usage_start_time 추출
            result["billed_date"] = self._format_date_only(
                usage_start_time
            )  # 날짜 형식 변환
            return True  # 날짜 처리 완료
        return False

    def _process_invoice_month(self, result: Dict[str, Any]) -> bool:
        """invoice.month 필드를 처리합니다."""
        invoice_month = self._extract_invoice_month(result)  # invoice.month 추출
        if (
            invoice_month
            and len(invoice_month) == CostManagerConfig.INVOICE_MONTH_LENGTH
        ):  # invoice.month 길이 확인
            result["billed_date"] = self._format_invoice_month(
                invoice_month
            )  # 날짜 형식 변환
            return True  # 날짜 처리 완료
        return False

    def _extract_invoice_month(self, result: Dict[str, Any]) -> Optional[str]:
        """invoice.month 값을 추출합니다."""
        # 평면화된 형태
        if (
            "invoice.month" in result and result["invoice.month"] is not None
        ):  # invoice.month 필드 확인
            return str(result["invoice.month"])  # invoice.month 추출

        # 딕셔너리 형태
        if (
            "invoice" in result
            and isinstance(result["invoice"], dict)
            and "month" in result["invoice"]
            and result["invoice"]["month"] is not None
        ):
            return result["invoice"]["month"]  # invoice.month 추출

        return None  # None 반환

    def _format_invoice_month(self, invoice_month: str) -> str:
        """invoice.month를 YYYY-MM-DD 형태로 변환합니다."""
        year = invoice_month[
            CostManagerConfig.YEAR_START_INDEX : CostManagerConfig.YEAR_END_INDEX
        ]  # 연도 추출
        month = invoice_month[
            CostManagerConfig.MONTH_START_INDEX : CostManagerConfig.MONTH_END_INDEX
        ]  # 월 추출
        return f"{year}-{month}-{CostManagerConfig.DEFAULT_DAY}"  # 날짜 형식 변환

    def _process_year_month(self, result: Dict[str, Any]) -> bool:
        """year, month 필드를 처리합니다."""
        if "year" in result and "month" in result:  # year, month 필드 확인
            year = (
                str(result["year"]) if result["year"] is not None else ""
            )  # year 추출
            month = (
                str(result["month"]) if result["month"] is not None else ""
            )  # month 추출
            day = (
                str(result.get("day", CostManagerConfig.DEFAULT_DAY))
                if result.get("day") is not None
                else CostManagerConfig.DEFAULT_DAY
            )  # day 추출

            if year and month:  # year, month 확인
                month = month.zfill(2)  # month 패딩 처리
                day = day.zfill(2)  # day 패딩 처리
                result["billed_date"] = f"{year}-{month}-{day}"  # 날짜 형식 변환
                return True  # 날짜 처리 완료
        return False  # 날짜 처리 실패

    def _parse_date(self, date: Any) -> Any:
        """날짜 문자열을 파싱합니다."""
        if date is None:  # date 값 확인
            raise TypeError("날짜는 None일 수 없습니다")  # 예외 발생

        # 이미 파싱된 Timestamp 객체인 경우
        if hasattr(date, "strftime"):  # datetime 객체인지 확인
            return date

        # 문자열인 경우 파싱
        if isinstance(date, str):
            try:
                return parse(date)  # 날짜 파싱
            except Exception as e:  # 예외 처리
                _LOGGER.error(f"날짜 파싱 오류: {e}", exc_info=True)
                raise e  # 예외 발생
        else:
            # 기타 타입의 경우 문자열로 변환 후 파싱 시도
            try:
                return parse(str(date))  # 문자열로 변환 후 파싱
            except Exception as e:  # 예외 처리
                _LOGGER.error(f"날짜 파싱 오류 (타입 변환 후): {e}", exc_info=True)
                raise e  # 예외 발생

    @staticmethod
    def _format_date_only(date_str: Any) -> str:
        """날짜 문자열에서 시간 부분을 제거하고 YYYY-MM-DD 형태로 변환합니다."""
        if not date_str:
            return ""  # 빈 문자열 반환

        # 이미 datetime 객체인 경우
        if hasattr(date_str, "strftime"):
            return date_str.strftime(CostManagerConfig.DATE_FORMAT)

        # 문자열이 아닌 경우 문자열로 변환
        if not isinstance(date_str, str):
            date_str = str(date_str)

        try:
            parsed_date = parse(date_str)  # 날짜 파싱
            return parsed_date.strftime(CostManagerConfig.DATE_FORMAT)  # 날짜 형식 변환
        except Exception:  # 예외 처리
            if (
                len(date_str) >= 10 and date_str[4] == "-" and date_str[7] == "-"
            ):  # 날짜 형식 확인
                return date_str[:10]  # 날짜 형식 변환
            return date_str

    def _validate_required_fields(self, result: Dict[str, Any]) -> None:
        """필수 필드가 존재하는지 확인합니다."""
        missing_fields = []  # 누락된 필드 목록
        available_fields = list(result.keys())  # 사용 가능한 필드 목록

        for field in CostManagerConfig.REQUIRED_FIELDS:  # 필수 필드 순회
            if field not in result:  # 필드 존재 확인
                missing_fields.append(field)  # 누락된 필드 추가

        if missing_fields:  # 누락된 필드가 있는 경우
            error_message = f"필수 필드가 누락되었습니다: {missing_fields}. "  # 누락된 필드 정보 추가
            error_message += (
                f"사용 가능한 필드: {available_fields}. "  # 사용 가능한 필드 정보 추가
            )

            if self.field_mapper:  # field_mapper 설정이 있는 경우
                error_message += f"현재 field_mapper 설정: {self.field_mapper}. "
                # 매핑 가능한 필드 제안
                suggested_mappings = []  # 제안된 매핑 목록
                for missing_field in missing_fields:  # 누락된 필드 순회
                    if (
                        missing_field == "cost" and "amount" in available_fields
                    ):  # cost 필드 확인
                        suggested_mappings.append(
                            f'"{missing_field}": "amount"'
                        )  # 제안된 매핑 추가
                    elif (
                        missing_field == "billed_date" and "date" in available_fields
                    ):  # billed_date 필드 확인
                        suggested_mappings.append(
                            f'"{missing_field}": "date"'
                        )  # 제안된 매핑 추가
                    elif (
                        missing_field == "currency" and "curr" in available_fields
                    ):  # currency 필드 확인
                        suggested_mappings.append(
                            f'"{missing_field}": "curr"'
                        )  # 제안된 매핑 추가

                if suggested_mappings:  # 제안된 매핑이 있는 경우
                    error_message += f"제안되는 매핑: {{{', '.join(suggested_mappings)}}}. "  # 제안된 매핑 정보 추가
            else:  # field_mapper 설정이 없는 경우
                error_message += "field_mapper가 설정되지 않았습니다. 원본 데이터에 필수 필드가 직접 포함되어 있어야 합니다."  # 필수 필드 정보 추가

            # _LOGGER.error(error_message)
            raise ValueError(
                f"Required field is missing: {missing_fields[0]}"
            )  # 첫 번째 누락 필드로 예외 발생

    def _create_final_data(
        self, result: Dict[str, Any], options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """최종 SpaceONE 포맷 데이터를 생성합니다."""
        cost = Decimal(result.get("cost") or 0)  # cost 추출

        if result.get("provider") == CostManagerConfig.CSV_PROVIDER:  # provider 확인
            credits_amount = Decimal(0)  # credits_amount 초기화
            usage_quantity = Decimal(
                result.get("usage_quantity") or 0
            )  # usage_quantity 추출
            region_code = result.get("region_code") or ""  # region_code 추출
            product = result.get("product") or ""  # product 추출
        else:
            credits_amount = Decimal(
                result.get("credits.amount") or 0
            )  # credits.amount 추출
            usage_quantity = Decimal(
                result.get("usage.amount_in_pricing_units") or 0
            )  # usage.amount_in_pricing_units 추출
            region_code = result.get("location.region") or ""  # location.region 추출
            product = (
                result.get("service.description") or ""
            )  # service.description 추출

        # cost_metric이 AmortizedCost인 경우 credits_amount를 사용
        if options and options.get("cost_metric") == "AmortizedCost":
            total_cost = cost + credits_amount
        else:
            total_cost = cost

        return {
            "cost": str(total_cost),  # 총 비용
            "usage_quantity": str(usage_quantity),  # 사용량
            "usage_type": result.get("sku.description") or "",  # 사용 유형
            "usage_unit": result.get("usage.pricing_unit") or "",  # 사용 단위
            "provider": result.get("provider") or "",  # 제공자
            "region_code": str(region_code),  # 지역 코드
            "product": str(product),  # 제품
            "resource": result.get("resource", ""),  # 리소스
            "billed_date": result.get("billed_date", ""),  # 청구 날짜
            "additional_info": result.get("additional_info") or {},  # 추가 정보
            "tags": result.get("tags.value") or {},  # 태그
        }

    def get_linked_accounts(
        self,
        options: Dict[str, Any],  # 플러그인 옵션 정보
        secret_data: Dict[str, Any],  # 인증 정보
        schema: Optional[str],  # 스키마 정보 (선택적)
    ) -> List[Dict[str, str]]:
        """연결된 계정(Linked Accounts) 정보를 조회합니다.

        Args:
            options: 플러그인 옵션 정보
            secret_data: 인증 정보
            schema: 스키마 정보 (선택적)

        Returns:
            연결된 계정 정보 리스트

        Raises:
            CostDataProcessingError: 계정 정보 조회 중 오류 발생 시
        """
        try:
            _LOGGER.info("연결된 계정 정보 조회 시작")

            data_source_type = self._determine_data_source_type(
                options
            )  # 데이터 소스 타입 결정
            _LOGGER.debug(
                f"데이터 소스 타입: {data_source_type}"
            )  # 데이터 소스 타입 로깅

            linked_accounts = self._extract_linked_accounts(
                data_source_type, options
            )  # 연결된 계정 정보 추출

            _LOGGER.info(f"연결된 계정 정보 조회 완료: {len(linked_accounts)}개 계정")
            return linked_accounts

        except Exception as e:
            _LOGGER.error(f"연결된 계정 정보 조회 중 오류: {e}", exc_info=True)
            raise CostDataProcessingError(f"계정 정보 조회 실패: {e}") from e

    def _determine_data_source_type(self, options: Dict[str, Any]) -> str:
        """데이터 소스 타입을 결정합니다."""
        if "base_url" in options:  # base_url 옵션 확인
            return "http_file"  # HTTP 파일 타입 반환
        elif "bucket_name" in options:  # bucket_name 옵션 확인
            return "google_storage"  # Google Cloud Storage 타입 반환
        else:
            return "unknown"  # 알 수 없는 타입 반환

    def _extract_linked_accounts(
        self, data_source_type: str, options: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """데이터 소스별로 연결된 계정을 추출합니다."""
        linked_accounts = []  # 연결된 계정 정보 초기화

        if data_source_type == "http_file":  # HTTP 파일 타입 확인
            _LOGGER.warning("HTTP 파일에서 계정 정보 추출 로직이 구현되지 않음")
        elif data_source_type == "google_storage":  # Google Cloud Storage 타입 확인
            _LOGGER.warning(
                "Google Cloud Storage에서 계정 정보 추출 로직이 구현되지 않음"
            )
        else:
            _LOGGER.warning(f"알 수 없는 데이터 소스 타입: {data_source_type}")

        # 기본 계정 정보 반환 (구현 전 임시)
        linked_accounts.append(
            {
                "account_id": "default",  # 계정 ID
                "name": "default",  # 계정 이름
            }
        )

        return linked_accounts
