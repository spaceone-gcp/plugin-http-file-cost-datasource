"""
Cost Analysis Plugin의 gRPC 인터페이스 모듈

이 모듈은 SpaceONE Cost Analysis 플러그인의 gRPC 서비스를 정의합니다.
HTTP 파일에서 비용 데이터를 수집하고 처리하는 기능을 제공합니다.
"""

from spaceone.api.cost_analysis.plugin import cost_pb2, cost_pb2_grpc
from spaceone.core.pygrpc import BaseAPI
from plugin.service.cost_service import CostService
from plugin.info.cost_info import CostsInfo


class Cost(BaseAPI, cost_pb2_grpc.CostServicer):
    """
    Cost Analysis 플러그인의 gRPC 서비스 클래스
    
    HTTP 파일에서 비용 데이터를 수집하고 처리하는 gRPC 엔드포인트를 제공합니다.
    SpaceONE의 BaseAPI를 상속받아 표준화된 API 구조를 따릅니다.
    """
    
    # gRPC 프로토콜 버퍼 정의
    pb2 = cost_pb2
    pb2_grpc = cost_pb2_grpc

    def get_data(self, request, context):
        """
        비용 데이터를 수집하고 반환하는 gRPC 메서드
        
        Args:
            request: gRPC 요청 객체 (데이터 소스 설정 정보 포함)
            context: gRPC 컨텍스트 객체
            
        Yields:
            CostsInfo: 처리된 비용 데이터 정보 객체들의 스트림
        """
        # gRPC 요청을 파싱하여 파라미터와 메타데이터 추출
        params, metadata = self.parse_request(request, context)

        # CostService를 사용하여 비용 데이터 수집 및 처리
        with self.locator.get_service(CostService, metadata) as cost_service:
            # 데이터 소스에서 비용 데이터를 스트리밍으로 수집
            response_stream = cost_service.get_data(params)
            
            # 각 비용 데이터를 CostsInfo 객체로 변환하여 응답 스트림 생성
            for costs_data in response_stream:
                yield self.locator.get_info(CostsInfo, costs_data)
