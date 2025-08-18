import logging
import time
from decimal import Decimal, InvalidOperation
from dateutil.parser import parse
from spaceone.core.manager import BaseManager
from plugin.error.cost import ERROR_EMPTY_BILLED_DATE, ERROR_REQUIRED_PARAMETER
from plugin.connector.http_file_connector import HTTPFileConnector
from plugin.connector.google_storage_collector import (
    GoogleStorageConnector,
)

# 로거 설정 
_LOGGER = logging.getLogger("spaceone")
# 필수 필드 목록    
_REQUIRED_FIELDS = ["cost", "currency", "billed_date"]

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
        self.default_vars = None  # 기본 변수 설정
        self.field_mapper = None  # 필드 매핑 설정
        self.type_mapper = None   # 타입 매핑 설정

    def get_data(self, options, secret_data, schema, task_options):
        """
        외부 비용 데이터를 수집하여 SpaceONE 비용 데이터 포맷으로 변환하는 메인 함수

        이 함수는 HTTP 파일 또는 Google Cloud Storage에서 비용 데이터를 읽어와
        SpaceONE에서 요구하는 포맷으로 변환하여 제너레이터로 반환합니다.

        데이터 소스는 task_options 또는 options의 base_url, bucket_name에 따라 결정됩니다.

        Args:
            options (dict): 플러그인 옵션 (base_url, field_mapper, default_vars, type_mapper 등)
            secret_data (dict): 인증 정보
            schema (str): 스키마 정보 (선택)
            task_options (dict): 작업별 옵션 (base_url 또는 bucket_name)

        Yields:
            dict: {"results": [비용 데이터 리스트]}
        Raises:
            ValueError: 데이터 소스 정보가 없을 때
        """
        # 1. 함수 시작 시점의 시간 기록 (성능 측정용)
        start_time = time.time()
        
        # 2. 처리 카운트 초기화 (성능 측정용)
        total_processed_count = 0

        # 3. 옵션에서 default_vars가 있으면 적용 (선택)
        if "default_vars" in options:
            self.default_vars = options["default_vars"]

        # 4. 옵션에서 field_mapper가 있으면 적용
        if "field_mapper" in options:
            self.field_mapper = options["field_mapper"]

        # 5. 옵션에서 type_mapper가 있으면 적용
        if "type_mapper" in options:
            self.type_mapper = options["type_mapper"]

        # 6. task_options가 None이면 빈 dict로 대체
        if task_options is None:
            task_options = {}

        # 7. 데이터 소스 분기 처리: task_options에 base_url이 있으면 HTTP 파일에서 수집
        if "base_url" in task_options:
            base_url = task_options["base_url"]
            # 7-1. HTTPFileConnector 인스턴스 생성
            http_file_connector = self.locator.get_connector(HTTPFileConnector)
            # 7-2. HTTPFileConnector 인스턴스 세션 생성
            http_file_connector.create_session(options, secret_data, schema)
            # 7-3. 비용 데이터 스트림 생성
            response_stream = http_file_connector.get_cost_data(base_url)
        # 8. task_options에 bucket_name이 있으면 Google Cloud Storage에서 수집
        elif "bucket_name" in task_options:
            # 8-1. Google Cloud Storage용 처리
            # 8-2. GoogleStorageConnector 인스턴스 생성
            storage_connector = self.locator.get_connector(GoogleStorageConnector, secret_data=secret_data)
            # 8-3. GoogleStorageConnector 인스턴스 세션 생성
            storage_connector.create_session(options, secret_data, schema)
            # 8-4. 비용 데이터 스트림 생성
            response_stream = storage_connector.get_cost_data(task_options)
        # 9. 위 조건이 모두 없으면 options.base_url로 fallback (선택)
        else:
            # 9-1. options에 base_url이 있으면 HTTP 파일에서 수집
            if "base_url" in options:
                base_url = options["base_url"]
                # 9-2. HTTPFileConnector 인스턴스 생성  
                http_file_connector = self.locator.get_connector(HTTPFileConnector) 
                # 9-3. HTTPFileConnector 인스턴스 세션 생성
                http_file_connector.create_session(options, secret_data, schema)
                # 9-4. 비용 데이터 스트림 생성
                response_stream = http_file_connector.get_cost_data(base_url)
            else:
                # 10. 모든 경로가 없으면 예외 발생
                raise ValueError("Either task_options.base_url, task_options.bucket_name, or options.base_url must be provided")

        # 11. 데이터 스트림에서 결과를 하나씩 받아서 가공 후 yield
        for results in response_stream:
            # 11-1. 원본 데이터를 SpaceONE 비용 데이터 포맷으로 변환
            costs_data = self._make_cost_data(results)
            # 11-2. 처리된 데이터 개수 카운트 (성능 측정용)
            total_processed_count += len(costs_data)
            # 11-3. 변환된 데이터를 제너레이터로 반환
            yield {"results": costs_data}

        # 12. 전체 처리 시간 및 처리 카운트 로깅 (성능 측정용)
        _LOGGER.debug(f"count: {total_processed_count}, duration: {time.time() - start_time:.2f}s")

    def _make_cost_data(self, results):
        """
        입력된 원본 비용 데이터(results)를 SpaceONE 비용 데이터 포맷에 맞게 변환하는 함수

        이 함수는 원본 데이터를 받아서 다음과 같은 단계로 처리합니다:
        1. 키와 값에 strip 적용
        2. field_mapper를 통한 필드 변환
        3. default_vars 적용
        4. type_mapper 적용
        5. billed_date 생성 및 포맷 변환
        6. cost, usage_quantity 타입 변환
        7. 필수 필드 검증
        8. SpaceONE 포맷으로 최종 변환

        Args:
            results (list[dict]): 원본 비용 데이터 리스트

        Returns:
            list[dict]: SpaceONE 비용 데이터 포맷으로 변환된 리스트
        """
        costs_data = []
        # 1. results 리스트 순회
        for result in results:
            # 2. 딕셔너리의 모든 키에 strip() 적용 (공백 제거)
            result = self._apply_strip_to_dict_keys(result)
            
            # 3. 딕셔너리의 모든 값에 strip() 적용 (공백 제거)
            result = self._apply_strip_to_dict_values(result)

            # 4. field_mapper가 있으면 필드명 매핑 적용
            if self.field_mapper:
                result = self._change_result_by_field_mapper(result)

            # 5. default_vars가 있으면 기본값 적용
            if self.default_vars:
                self._set_default_vars(result)

            # 6. type_mapper가 있으면 타입 변환 적용
            if self.type_mapper:
                self._set_type_mapper(result)

            # 7. billed_date 생성 및 포맷 변환
            self._create_billed_date(result)

            # 8. cost, usage_quantity 타입 변환 실패 시 또는 필수값 없으면 건너뜀
            if not self._convert_cost_and_usage_quantity_types(result) or not self._exist_cost_and_usage_quantity(result):
                continue

            # 9. 필수 필드 체크
            self._check_required_fields(result)

            try:
                # 10. SpaceONE 비용 데이터 포맷에 맞게 딕셔너리 생성
                # (1) cost 값 가져오기 (없으면 0으로 처리)
                cost_value = result.get("cost") or Decimal('0')
                
                # (2) credits.amount를 Decimal로 안전하게 변환
                credits_amount_raw = result.get("credits.amount", 0)
                if isinstance(credits_amount_raw, (int, float)):
                    credits_amount = Decimal(str(credits_amount_raw))
                elif isinstance(credits_amount_raw, str):
                    credits_amount = Decimal(credits_amount_raw.strip())
                else:
                    credits_amount = Decimal('0')
                
                # (3) cost + credits.amount 합산
                total_cost_decimal = cost_value + credits_amount
                
                # (4) 과학적 표기법 방지 및 불필요한 0 제거
                total_cost_str = format(total_cost_decimal, 'f')
                total_cost_str = total_cost_str.rstrip('0').rstrip('.')
                # (5) 매우 작은 값은 문자열로 유지, 아니면 float 변환
                if total_cost_str and float(total_cost_str) < 0.0001:
                    total_cost = total_cost_str
                else:
                    total_cost = float(total_cost_str) if total_cost_str else 0.0
                
                # (6) usage.amount_in_pricing_units를 Decimal로 안전하게 변환
                usage_quantity_raw = result.get("usage.amount_in_pricing_units", 0)
                if isinstance(usage_quantity_raw, (int, float)):
                    usage_quantity_decimal = Decimal(str(usage_quantity_raw))
                elif isinstance(usage_quantity_raw, str):
                    usage_quantity_decimal = Decimal(usage_quantity_raw.strip())
                else:
                    usage_quantity_decimal = Decimal('0')
                
                # (7) usage_quantity도 과학적 표기법 방지 및 불필요한 0 제거
                usage_quantity_str = format(usage_quantity_decimal, 'f')
                usage_quantity_str = usage_quantity_str.rstrip('0').rstrip('.')
                if usage_quantity_str and float(usage_quantity_str) < 0.0001:
                    usage_quantity = usage_quantity_str
                else:
                    usage_quantity = float(usage_quantity_str) if usage_quantity_str else 0.0
                
                # (8) 최종 데이터 딕셔너리 생성 (SpaceONE 포맷)
                data = {
                    "cost": total_cost,  # 최종 비용(Decimal을 float로 변환하여 출력)
                    "usage_quantity": usage_quantity,  # 사용량(Decimal을 float로 변환하여 출력)
                    "usage_type": result.get("sku.description") or "",  # SKU 설명(사용 유형, 없으면 빈 문자열)
                    "usage_unit": result.get("usage.pricing_unit") or "",  # 사용 단위(없으면 빈 문자열)
                    "provider": result.get("provider") or "",  # 클라우드 제공자(없으면 빈 문자열)
                    "region_code": result.get("region_code") or "",  # 리전 코드(없으면 빈 문자열)
                    "product": result.get("service.description") or "",  # 서비스/제품명(없으면 빈 문자열)
                    "resource": result.get("resource", ""),  # 리소스명(없으면 빈 문자열)
                    "billed_date": self._format_date_only(result.get("usage_start_time", "")),  # 청구 날짜(필수, usage_start_time 기준)
                    "additional_info": result.get("additional_info") or {},  # 추가 정보(없으면 빈 dict)
                    "tags": result.get("tags.value") or {},  # 태그 정보(없으면 빈 dict)
                }

            except Exception as e:
                # 11. 데이터 생성 중 오류 발생 시 로깅 후 예외 재발생
                _LOGGER.error(f"[_make_cost_data] make data error: {e}", exc_info=True)
                raise e

            # 12. 변환된 데이터 리스트에 추가
            costs_data.append(data)
        # 13. 최종 변환된 데이터 리스트 반환
        return costs_data

    @staticmethod
    def _apply_strip_to_dict_keys(result):
        """
        딕셔너리의 모든 키에 strip()을 적용하여 앞뒤 공백을 제거하는 함수
        
        Args:
            result (dict): 처리할 딕셔너리
            
        Returns:
            dict: 키가 strip된 딕셔너리
        """
        for key in list(result.keys()):
            new_key = key.strip()
            if new_key != key:
                result[new_key] = result[key]
                del result[key]
        return result

    @staticmethod
    def _apply_strip_to_dict_values(result):
        """
        딕셔너리의 모든 문자열 값에 strip()을 적용하여 앞뒤 공백을 제거하는 함수
        
        Args:
            result (dict): 처리할 딕셔너리
            
        Returns:
            dict: 값이 strip된 딕셔너리
        """
        for key, value in result.items():
            if isinstance(value, str):
                result[key] = value.strip()
        return result

    def _change_result_by_field_mapper(self, result):
        """
        field_mapper 설정에 따라 딕셔너리의 키를 변환하는 함수
        
        field_mapper는 원본 필드명을 SpaceONE 필드명으로 매핑하는 설정입니다.
        additional_info 필드의 경우 중첩된 딕셔너리로 처리할 수 있습니다.
        
        Args:
            result (dict): 변환할 딕셔너리
            
        Returns:
            dict: 필드가 매핑된 딕셔너리
        """
        for origin_field, actual_field in self.field_mapper.items():
            if isinstance(actual_field, str):
                if actual_field in result:
                    result[origin_field] = result[actual_field]
                    del result[actual_field]

            if origin_field == "additional_info":
                additional_info = {}
                for (
                    origin_additional_field,
                    actual_additional_field,
                ) in actual_field.items():
                    additional_info[origin_additional_field] = result[
                        actual_additional_field
                    ]
                    del result[actual_additional_field]
                result[origin_field] = additional_info

        return result

    def _create_billed_date(self, result):
        """
        billed_date 필드를 생성하거나 포맷을 변환하는 함수
        
        다음과 같은 순서로 billed_date를 처리합니다:
        1. 기존 billed_date가 있으면 포맷 변환
        2. Google Cloud Billing Export의 invoice.month 필드 처리 (평면화된 형태)
        3. Google Cloud Billing Export의 invoice.month 필드 처리 (딕셔너리 형태)
        4. year, month 필드 조합으로 생성
        5. 모든 조건이 만족되지 않으면 예외 발생
        
        Args:
            result (dict): 처리할 딕셔너리
            
        Returns:
            dict: billed_date가 설정된 딕셔너리
            
        Raises:
            ERROR_EMPTY_BILLED_DATE: 유효한 날짜 필드를 찾을 수 없을 때
        """
        if self._exist_billed_date(result):
            billed_date = result["billed_date"]
            billed_date = self._apply_parse_date(billed_date)
            billed_date = str(billed_date.strftime("%Y-%m-%d"))

            result["billed_date"] = billed_date

        # usage_start_time이 있는 경우 처리
        elif "usage_start_time" in result:
            usage_start_time = result["usage_start_time"]
            billed_date = self._format_date_only(usage_start_time)
            result["billed_date"] = billed_date
            return result

        else:
            # Google Cloud Billing Export의 invoice.month 필드 처리 (평면화된 형태)
            if "invoice.month" in result:
                invoice_month = str(result["invoice.month"])
                # invoice.month는 "YYYYMM" 형식 (예: "202508")
                if len(invoice_month) == 6:
                    year = invoice_month[:4]
                    month = invoice_month[4:6]
                    day = "01"  # 기본값으로 1일 사용
                    billed_date = f"{year}-{month}-{day}"
                    result["billed_date"] = billed_date
                    return result
            
            # Google Cloud Billing Export의 invoice.month 필드 처리 (딕셔너리 형태)
            if "invoice" in result and isinstance(result["invoice"], dict) and "month" in result["invoice"]:
                invoice_month = result["invoice"]["month"]
                # invoice.month는 "YYYYMM" 형식 (예: "202508")
                if len(invoice_month) == 6:
                    year = invoice_month[:4]
                    month = invoice_month[4:6]
                    day = "01"  # 기본값으로 1일 사용
                    billed_date = f"{year}-{month}-{day}"
                    result["billed_date"] = billed_date
                    return result
            
            # 기존 year, month 필드 처리
            if "year" in result and "month" in result:
                year = result["year"]
                month = result["month"]
                day = result.get("day", "01")

                if len(month) == 1:
                    month = f"0{month}"
                if len(day) == 1:
                    day = f"0{day}"

                billed_date = f"{year}-{month}-{day}"
                result["billed_date"] = billed_date
            else:
                # billed_date, year/month, invoice.month 모두 없는 경우
                _LOGGER.error(f"[_create_billed_date] No valid date field found: {result}")
                raise ERROR_EMPTY_BILLED_DATE(result=result)

        return result

    @staticmethod
    def _exist_billed_date(result):
        """
        billed_date 필드가 존재하는지 확인하는 함수
        
        billed_date, usage_start_time, year/month, invoice.month 중 하나라도 있으면 True를 반환합니다.
        모든 날짜 필드가 없으면 예외를 발생시킵니다.
        
        Args:
            result (dict): 확인할 딕셔너리
            
        Returns:
            bool: billed_date가 존재하면 True, 다른 날짜 필드가 있으면 False
            
        Raises:
            ERROR_EMPTY_BILLED_DATE: 모든 날짜 필드가 없을 때
        """
        if result.get("billed_date"):
            return True
        elif result.get("usage_start_time"):
            return False
        elif result.get("year") and result.get("month"):
            return False
        elif "invoice.month" in result:
            return False
        elif "invoice" in result and isinstance(result["invoice"], dict) and "month" in result["invoice"]:
            return False
        else:
            _LOGGER.error(f"[_exist_billed_date] billed_date is empty: {result}")
            raise ERROR_EMPTY_BILLED_DATE(result=result)

    @staticmethod
    def _apply_parse_date(date):
        """
        날짜 문자열을 파싱하여 datetime 객체로 변환하는 함수
        
        Args:
            date (str): 파싱할 날짜 문자열
            
        Returns:
            datetime: 파싱된 날짜 객체
            
        Raises:
            TypeError: 날짜 파싱에 실패했을 때
        """
        try:
            parsed_date = parse(date)
            return parsed_date
        except TypeError as e:
            _LOGGER.error(f"[_apply_parse_date] parse date error: {e}", exc_info=True)
            raise e

    @staticmethod
    def _format_date_only(date_str):
        """
        날짜 문자열에서 시간 부분을 제거하고 YYYY-MM-DD 형태로 변환하는 함수
        
        Args:
            date_str (str): 변환할 날짜 문자열 (예: "2025-07-10 01:00:00 UTC")
            
        Returns:
            str: YYYY-MM-DD 형태의 날짜 문자열 (예: "2025-07-10")
        """
        if not date_str or not isinstance(date_str, str):
            return ""
        
        try:
            # 날짜 파싱 시도
            parsed_date = parse(date_str)
            return parsed_date.strftime("%Y-%m-%d")
        except Exception:
            # 파싱 실패 시 문자열에서 날짜 부분만 추출
            if len(date_str) >= 10 and date_str[4] == '-' and date_str[7] == '-':
                return date_str[:10]  # "YYYY-MM-DD" 부분만 추출
            return date_str  # 변환할 수 없으면 원본 반환

    def _set_default_vars(self, result):
        """
        default_vars 설정에 따라 딕셔너리에 기본값을 설정하는 함수
        
        Args:
            result (dict): 기본값을 설정할 딕셔너리
        """
        for key, value in self.default_vars.items():
            result[key] = value

    @staticmethod
    def _convert_cost_and_usage_quantity_types(result):
        """
        cost와 usage_quantity 필드를 Decimal 타입으로 변환하는 함수
        
        정밀한 소수점 계산을 위해 Decimal 타입을 사용합니다.
        변환에 실패하면 False를 반환하고, 성공하면 True를 반환합니다.
        
        Args:
            result (dict): 변환할 딕셔너리
            
        Returns:
            bool: 변환 성공 시 True, 실패 시 False
        """
        try:
            # cost 필드를 Decimal로 변환 (정밀한 소수점 계산)
            cost_value = result["cost"]
            if isinstance(cost_value, str):
                # 문자열인 경우 공백 제거 후 변환
                cost_value = cost_value.strip()
            result["cost"] = Decimal(str(cost_value))
            
            # usage_quantity 필드를 Decimal로 변환
            usage_value = result.get("usage_quantity", 0)
            if isinstance(usage_value, str):
                # 문자열인 경우 공백 제거 후 변환
                usage_value = usage_value.strip()
            result["usage_quantity"] = Decimal(str(usage_value))
            
        except (InvalidOperation, ValueError, TypeError) as e:
            _LOGGER.error(
                f"[_convert_cost_and_usage_quantity_types] convert cost and usage quantity types error: {e} (data={result})",
                exc_info=True,
            )
            return False
        return True

    @staticmethod
    def _exist_cost_and_usage_quantity(result):
        """
        cost 또는 usage_quantity 필드가 존재하는지 확인하는 함수
        
        cost나 usage_quantity 중 하나라도 0이 아닌 값이 있으면 True를 반환합니다.
        둘 다 0이거나 없으면 False를 반환합니다.
        
        Args:
            result (dict): 확인할 딕셔너리
            
        Returns:
            bool: cost 또는 usage_quantity가 존재하면 True, 아니면 False
        """
        if result["cost"] or result["cost"] == Decimal('0'):
            return True
        elif result["usage_quantity"] or result["usage_quantity"] == Decimal('0'):
            return True
        else:
            _LOGGER.error(
                f"[_exist_cost_and_usage_quantity] cost or usage quantity are empty: {result}"
            )
            return False

    @staticmethod
    def _check_required_fields(result):
        """
        필수 필드가 존재하는지 확인하는 함수
        
        _REQUIRED_FIELDS에 정의된 모든 필드가 딕셔너리에 존재하는지 확인합니다.
        
        Args:
            result (dict): 확인할 딕셔너리
            
        Raises:
            ERROR_REQUIRED_PARAMETER: 필수 필드가 없을 때
        """
        for field in _REQUIRED_FIELDS:
            if field not in result:
                raise ERROR_REQUIRED_PARAMETER(key=field)

    def _set_type_mapper(self, result):
        """
        type_mapper 설정에 따라 데이터 타입을 변환하는 함수
        
        현재는 additional_info의 "Account ID" 필드를 문자열로 변환하고
        12자리로 패딩하는 기능만 구현되어 있습니다.
        
        Args:
            result (dict): 변환할 딕셔너리
            
        Returns:
            dict: 타입이 변환된 딕셔너리
        """
        # Not Implemented
        if "additional_info" in self.type_mapper:
            if (
                "Account ID" in self.type_mapper["additional_info"]
                and "additional_info" in result
                and "Account ID" in result.get("additional_info", {})
            ):
                account_id = result["additional_info"]["Account ID"]
                if isinstance(account_id, int) or isinstance(account_id, float):
                    result["additional_info"]["Account ID"] = str(account_id).zfill(12)
        return result

    def get_linked_accounts(self, options, secret_data, schema):
        """연결된 계정(Linked Accounts) 정보를 조회하는 메서드
        
        HTTP 파일이나 Google Cloud Storage에서 비용 데이터를 수집할 때
        연결된 계정들의 목록을 반환합니다. 현재는 기본적인 구조만 제공하며,
        실제 구현은 데이터 소스에 따라 달라질 수 있습니다.
        
        Args:
            options (dict): 플러그인 옵션 정보 (base_url, field_mapper, default_vars 등)
            secret_data (dict): 인증 정보 (private_key 포함)
            schema (str): 스키마 정보 (선택적)
            
        Returns:
            dict: 연결된 계정 정보 리스트
                - account_id (str): 계정 ID
                - name (str): 계정명
                
        Raises:
            Exception: 계정 정보 조회 중 오류 발생 시
        """
        try:
            _LOGGER.info("[get_linked_accounts] 시작: 연결된 계정 정보 조회")
            
            # 1. 데이터 소스 타입 확인
            # options에서 base_url이 있으면 HTTP 파일, bucket_name이 있으면 Google Cloud Storage
            data_source_type = "unknown"
            if "base_url" in options:
                data_source_type = "http_file"
            elif "bucket_name" in options:
                data_source_type = "google_storage"
            
            _LOGGER.debug(f"[get_linked_accounts] 데이터 소스 타입: {data_source_type}")
            
            # 2. 데이터 소스별 연결된 계정 조회 로직
            # TODO: 실제 구현에서는 각 데이터 소스에서 계정 정보를 추출해야 함
            # 현재는 기본 구조만 제공
            
            linked_accounts = []
            
            if data_source_type == "http_file":
                # HTTP 파일에서 계정 정보 추출 로직
                # TODO: HTTP 파일에서 계정 정보를 파싱하는 로직 구현 필요
                _LOGGER.warning("[get_linked_accounts] HTTP 파일에서 계정 정보 추출 로직이 구현되지 않음")
                
            elif data_source_type == "google_storage":
                # Google Cloud Storage에서 계정 정보 추출 로직
                # TODO: Google Cloud Storage에서 계정 정보를 추출하는 로직 구현 필요
                _LOGGER.warning("[get_linked_accounts] Google Cloud Storage에서 계정 정보 추출 로직이 구현되지 않음")
                
            else:
                # 알 수 없는 데이터 소스 타입
                _LOGGER.warning(f"[get_linked_accounts] 알 수 없는 데이터 소스 타입: {data_source_type}")
            
            # 3. 기본 계정 정보 반환 (구현 전 임시)
            # 실제로는 위에서 추출한 계정 정보를 반환해야 함
            default_account = {
                "account_id": "default",
                "name": "default"
            }
            linked_accounts.append(default_account)
            
            _LOGGER.info(f"[get_linked_accounts] 완료: {len(linked_accounts)}개 계정 정보 조회")
            
            return linked_accounts
            
        except Exception as e:
            _LOGGER.error(f"[get_linked_accounts] 오류 발생: {e}", exc_info=True)
            raise e
