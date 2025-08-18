import unittest
from unittest.mock import patch

from spaceone.core.unittest.result import print_data
from spaceone.core.unittest.runner import RichTestRunner
from spaceone.core import config
from spaceone.core.transaction import Transaction
from plugin.service.job_service import JobService
from plugin.connector.http_file_connector import HTTPFileConnector
from test.factory.common_config import OPTIONS


class TestJobService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.init_conf(package="plugin")
        cls.transaction = Transaction({"service": "cost_analysis", "api_class": "Cost"})
        super().setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()

    @patch.object(HTTPFileConnector, "__init__", return_value=None)
    def test_get_tasks(self, *args):
        params = {"options": OPTIONS, "secret_data": {}}

        self.transaction.method = "get_tasks"
        data_source_svc = JobService(transaction=self.transaction)
        responses = data_source_svc.get_tasks(params.copy())

        print_data(responses, "test_get_tasks")


if __name__ == "__main__":
    unittest.main(testRunner=RichTestRunner)
