SERVICE = "plugin"

CONNECTORS = {"HTTPFileConnector": {}, "GoogleStorageCollector": {}}

MANAGERS = {"CostManager": {}, "DataSourceManager": {}, "JobManager": {}}

HANDLERS = {
    "authentication": [],
    "authorization": [],
    "mutation": [],
    "event": [],
}

LOG = {
    "filters": {
        "masking": {
            "rules": {
                "DataSource.verify": ["secret_data"],
                "Job.get_tasks": ["secret_data"],
                "Cost.get_data": ["secret_data"],
            }
        }
    }
}
