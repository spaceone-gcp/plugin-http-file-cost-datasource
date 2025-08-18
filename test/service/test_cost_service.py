import unittest
from unittest.mock import patch

from spaceone.core.unittest.result import print_data
from spaceone.core.unittest.runner import RichTestRunner
from spaceone.core import config
from spaceone.core.transaction import Transaction

from plugin.connector.http_file_connector import HTTPFileConnector
from plugin.service.cost_service import CostService
from test.factory.common_config import OPTIONS

class TestCostService(unittest.TestCase):
    """
    CostService 클래스의 단위 테스트
    
    비용 데이터 수집 및 연결된 계정 정보 조회 기능을 테스트합니다.
    HTTP 파일이나 Google Cloud Storage에서 데이터를 수집하는 기능을 검증합니다.
    """
    @classmethod
    def setUpClass(cls):
        config.init_conf(package="plugin")
        cls.transaction = Transaction({"service": "cost_analysis", "api_class": "Cost"})
        super().setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()

    @patch.object(HTTPFileConnector, "__init__", return_value=None)
    def test_get_cost_data(self, *args):
        """비용 데이터 수집 기능 테스트
        
        HTTP 파일에서 비용 데이터를 수집하는 기능을 테스트합니다.
        """
        params = {"options": OPTIONS, "secret_data": {}, "task_options": OPTIONS}

        self.transaction.method = "get_data"
        cost_svc = CostService(transaction=self.transaction)
        responses = cost_svc.get_data(params.copy())

        for response in responses:
            print_data(response, "test_get_cost_data")

    def test_get_linked_accounts(self):
        """연결된 계정 정보 조회 기능 테스트
        
        연결된 계정들의 목록을 조회하는 기능을 테스트합니다.
        """
        params = {"options": OPTIONS, "secret_data": {}}

        self.transaction.method = "get_linked_accounts"
        cost_svc = CostService(transaction=self.transaction)
        linked_accounts = cost_svc.get_linked_accounts(params.copy())

        print_data(linked_accounts, "test_get_linked_accounts")
        
        # 기본 반환값 검증
        self.assertIsInstance(linked_accounts, list)
        if linked_accounts:  # 리스트가 비어있지 않다면
            self.assertIn("account_id", linked_accounts[0])
            self.assertIn("name", linked_accounts[0])


if __name__ == "__main__":
    unittest.main(testRunner=RichTestRunner)
