import logging
import os
import tempfile
from typing import List

import google.oauth2.service_account
import numpy as np
import pandas as pd
from google.cloud import storage
from spaceone.core.connector import BaseConnector

from cloudforet.cost_analysis.error import *

_PAGE_SIZE = 1000

_LOGGER = logging.getLogger("spaceone")


class GoogleStorageConnector(BaseConnector):
    google_client_service = "storage"
    version = "v1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.secret_data = kwargs.get("secret_data")
        self.project_id = self.secret_data.get("project_id")
        self.credentials = (
            google.oauth2.service_account.Credentials.from_service_account_info(
                self.secret_data
            )
        )
        self.client = storage.Client(
            project=self.secret_data["project_id"], credentials=self.credentials
        )

    def get_cost_data(self, bucket_name: str):

        bucket = self.client.get_bucket(bucket_name)
        _LOGGER.debug(f'bucket: {bucket}')
        blob_names = [blob.name for blob in bucket.list_blobs()]
        _LOGGER.debug(f'blob_names: {blob_names}')
        
        # CSV 파일만 필터링 (디렉토리 제외)
        csv_blob_names = [name for name in blob_names if name.endswith('.csv')]
        _LOGGER.debug(f'csv_blob_names: {csv_blob_names}')
        
        for blob_name in csv_blob_names:
            blob = bucket.get_blob(blob_name)

            if blob:
                tmpdir = tempfile.gettempdir()
                csv_file_path = os.path.join(tmpdir, blob_name)
                blob.download_to_filename(csv_file_path)
                costs_data = self._get_csv(csv_file_path)
                _LOGGER.debug(
                    f"[get_cost_data] costs count of {blob_name} : {len(costs_data)}"
                )

                # Paginate
                page_count = int(len(costs_data) / _PAGE_SIZE) + 1

                for page_num in range(page_count):
                    offset = _PAGE_SIZE * page_num
                    yield costs_data[offset : offset + _PAGE_SIZE]

    @staticmethod
    def _check_options(options: dict) -> None:
        if "bucket_name" not in options:
            raise ERROR_REQUIRED_PARAMETER(key="options.bucket_name")

    @staticmethod
    def _get_csv(csv_file: str) -> List[dict]:
        try:
            df = pd.read_csv(csv_file, encoding="utf-8-sig")
            df = df.replace({np.nan: None})

            costs_data = df.to_dict("records")
            return costs_data

        except Exception as e:
            _LOGGER.error(f"[_get_csv] download error: {e}", exc_info=True)
            raise e
