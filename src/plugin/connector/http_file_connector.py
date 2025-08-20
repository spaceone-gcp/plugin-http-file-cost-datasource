# HTTP 파일에서 비용 데이터를 수집하는 커넥터
# CSV, JSON, Parquet 형식의 파일을 지원하며, HTTP/HTTPS URL을 통해 파일을 다운로드하여 처리
import logging
import tempfile
from typing import List, Dict, Any, Generator

from spaceone.core.error import ERROR_REQUIRED_PARAMETER

# 베이스 클래스 import
from plugin.connector.base_file_connector import BaseFileConnector

# 모듈 내보내기 
__all__ = ["HTTPFileConnector"]

# 로거 설정     
_LOGGER = logging.getLogger(__name__)


class HTTPFileConnector(BaseFileConnector):
    """
    HTTP/HTTPS URL을 통해 파일을 다운로드하고 비용 데이터를 추출하는 커넥터
    
    지원하는 파일 형식:
    - CSV (쉼표, 세미콜론, 탭, 파이프로 구분)
    - JSON (일반 JSON, JSON Lines 형식)
    - Parquet (압축된 Parquet 파일 포함)
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # 베이스 클래스 초기화
        self.base_url = None  # 기본 URL
        self.field_mapper = None  # 필드 매핑
        self.default_vars = None  # 기본 변수

    def create_session(
        self, options: dict, secret_data: dict, schema: str = None
    ) -> None:
        """
        세션 생성 및 설정
        
        Args:
            options: 설정 옵션 (base_url, field_mapper, default_vars 포함)
            secret_data: 인증 정보 (현재 사용되지 않음)
            schema: 스키마 정보 (현재 사용되지 않음)
        """
        self._check_options(options)  # 옵션 검증
        self.base_url = options["base_url"]  # 기본 URL 설정
        
        if "field_mapper" in options:  # 필드 매핑 설정
            self.field_mapper = options["field_mapper"]  # 필드 매핑 설정
        if "default_vars" in options:  # 기본 변수 설정
            self.default_vars = options["default_vars"]  # 기본 변수 설정

    def get_cost_data(self, base_url: str) -> Generator[List[Dict[str, Any]], None, None]:
        """
        비용 데이터를 가져오는 메인 메서드
        
        파일 형식을 자동 감지하여 적절한 파서를 사용하고,
        결과를 페이지 단위로 반환합니다.
        
        Args:
            base_url: 파일 URL
            
        Yields:
            List[Dict[str, Any]]: 페이지 단위의 비용 데이터
        """
        # 파일 형식에 따른 파싱 메서드 호출
        if self.is_json_file(base_url):  # JSON 파일 처리
            costs_data = self._get_json(base_url)  # JSON 파일 파싱
        elif self.is_parquet_file(base_url):  # Parquet 파일 처리
            costs_data = self._get_parquet(base_url)  # Parquet 파일 파싱
        else:
            costs_data = self._get_csv(base_url)  # CSV 파일 파싱

        # 페이지네이션 처리
        yield from self.get_cost_data_paginated(costs_data)  # 페이지네이션 처리

    @staticmethod
    def _check_options(options: dict) -> None:
        """
        필수 옵션 검증
        
        Args:
            options: 검증할 옵션 딕셔너리
            
        Raises:
            ERROR_REQUIRED_PARAMETER: base_url이 없는 경우
        """
        if "base_url" not in options:
            raise ERROR_REQUIRED_PARAMETER(key="options.base_url")

    def _get_csv(self, base_url: str) -> List[Dict[str, Any]]:
        """
        CSV 파일에서 비용 데이터를 읽어오는 메서드
        
        Args:
            base_url: CSV 파일 URL
            
        Returns:
            List[Dict[str, Any]]: 파싱된 비용 데이터 리스트
        """
        try:
            # 파일 다운로드
            content = self.download_file_from_url(base_url)
            
            # 임시 파일에 저장
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv') as temp_file:
                temp_file.write(content)  # 파일 내용 저장
                temp_file_path = temp_file.name  # 임시 파일 경로 설정
            
            try:
                # 베이스 클래스의 CSV 파싱 메서드 사용
                return self.read_csv_file(temp_file_path)
            finally:
                # 임시 파일 정리
                self.cleanup_temp_file(temp_file_path)
                
        except Exception as e:
            _LOGGER.error(f"CSV processing error: {e}", exc_info=True)
            raise e

    def _get_json(self, base_url: str) -> List[Dict[str, Any]]:
        """
        JSON 파일에서 비용 데이터를 읽어오는 메서드
        
        Args:
            base_url: JSON 파일 URL
            
        Returns:
            List[Dict[str, Any]]: 파싱된 비용 데이터 리스트
        """
        try:
            # 파일 다운로드
            content = self.download_file_from_url(base_url)
            
            # 임시 파일에 저장
            file_extension = '.json.gz' if base_url.lower().endswith('.json.gz') else '.json'
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix=file_extension) as temp_file:
                temp_file.write(content)  # 파일 내용 저장
                temp_file_path = temp_file.name  # 임시 파일 경로 설정
            
            try:
                # 베이스 클래스의 JSON 파싱 메서드 사용
                return self.read_json_file(temp_file_path)
            finally:
                # 임시 파일 정리
                self.cleanup_temp_file(temp_file_path)
                
        except Exception as e:
            _LOGGER.error(f"JSON processing error: {e}", exc_info=True)
            raise e

    def _get_parquet(self, base_url: str) -> List[Dict[str, Any]]:
        """
        Parquet 파일을 다운로드하고 파싱하여 비용 데이터를 반환하는 메서드
        
        Args:
            base_url: Parquet 파일의 URL
            
        Returns:
            List[Dict[str, Any]]: 파싱된 비용 데이터 리스트
        """
        try:
            # 파일 다운로드
            content = self.download_file_from_url(base_url)
            
            # 임시 파일에 저장
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.parquet') as temp_file:
                temp_file.write(content)  # 파일 내용 저장
                temp_file_path = temp_file.name  # 임시 파일 경로 설정
            
            try:
                # 베이스 클래스의 Parquet 파싱 메서드 사용
                return self.read_parquet_file(temp_file_path)
            finally:
                # 임시 파일 정리
                self.cleanup_temp_file(temp_file_path)
                
        except Exception as e:
            _LOGGER.error(f"Parquet processing error: {e}", exc_info=True)
            raise e
