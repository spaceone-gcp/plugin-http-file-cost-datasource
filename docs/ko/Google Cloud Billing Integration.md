# Google Cloud Billing 통합 가이드

이 문서는 SpaceONE의 HTTP 파일 비용 데이터 소스 플러그인을 사용하여 Google Cloud Billing Export 데이터를 처리하고 분석하는 방법을 상세히 설명합니다.

## 목차
1. [개요](#1-개요)
2. [사전 준비: Google Cloud 설정](#2-사전-준비-google-cloud-설정)
3. [플러그인 설정](#3-플러그인-설정)
4. [필드 매핑 (Field Mapping)](#4-필드-매핑-field-mapping)
5. [플러그인을 활용한 비용 분석](#5-플러그인을-활용한-비용-분석)
6. [고급 설정](#6-고급-설정)
7. [문제 해결](#7-문제-해결)
8. [참고 자료](#8-참고-자료)

---


## 1. 개요

Google Cloud는 BigQuery를 통해 상세한 비용 및 사용량 데이터를 제공합니다. 이 플러그인은 Google Cloud Storage에 저장된 Billing Export 데이터를 읽어와 SpaceONE의 표준 비용 데이터 형식으로 변환하여, 사용자가 비용을 심층적으로 분석하고 관리할 수 있도록 돕습니다.

### 지원 데이터 형식
- CSV, JSON, Parquet
- 압축 파일 (.gz, .snappy, .zstd 등)

### 핵심 기능
- Google Cloud Billing 데이터의 자동 스키마 매핑
- 크레딧, 유효 할인 등 복잡한 비용 구조 분석 지원
- 라벨, 태그를 활용한 세분화된 비용 추적

> **[중요] 데이터 스키마 이해하기**
> 플러그인을 효과적으로 사용하려면 Google Cloud Billing 데이터의 구조를 이해하는 것이 필수적입니다. 아래 가이드를 먼저 읽어보시는 것을 권장합니다.
> - **[Google Cloud Billing 데이터 분석 가이드](./Google%20Cloud%20Billing.md)**

---


## 2. 사전 준비: Google Cloud 설정

### 2.1. Billing Export 설정
1.  **BigQuery로 내보내기**: Google Cloud 콘솔에서 **결제 > 결제 내보내기**로 이동하여, **상세 사용량 비용 데이터**를 BigQuery로 내보내도록 설정합니다. 이것이 가장 상세한 데이터를 제공합니다.
2.  **파일로 내보내기**: 동일한 메뉴의 **파일 내보내기** 탭에서, 비용 데이터를 저장할 **Google Cloud Storage(GCS) 버킷**을 지정하고 파일 형식(CSV 권장)을 선택합니다.

### 2.2. 서비스 계정(Service Account) 생성 및 권한 부여
플러그인이 GCS 버킷에 접근하려면 서비스 계정이 필요합니다.
1.  **IAM 및 관리자 > 서비스 계정**에서 새 서비스 계정을 생성합니다.
2.  생성된 서비스 계정에 **`Storage 개체 뷰어(Storage Object Viewer)`** 역할을 부여하여 GCS 버킷의 파일을 읽을 수 있도록 허용합니다.
3.  서비스 계정 키(JSON 형식)를 생성하고 다운로드합니다. 이 키는 플러그인 설정의 `secret_data`에 사용됩니다.

---


## 3. 플러그인 설정

데이터 소스 추가 시 다음과 같은 구조로 플러그인 옵션을 설정합니다.

```yaml
# options 설정
options:
  bucket_name: "your-billing-export-bucket" # GCS 버킷 이름
  provider: "google_cloud"              # 필수로 google_cloud 지정
  field_mapper: ...                     # 4. 필드 매핑 섹션 참고
  default_vars:                       # 데이터에 없는 필드의 기본값 설정
    provider: "google_cloud"

# secret_data 설정
secret_data:
  # 다운로드한 서비스 계정 JSON 키의 전체 내용을 여기에 붙여넣습니다.
  type: "service_account"
  project_id: "your-project-id"
  private_key_id: "..."
  private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email: "..."
  ...
```

---


## 4. 필드 매핑 (Field Mapping)

`field_mapper`는 원본 데이터의 필드명을 SpaceONE의 표준 필드명으로 변환하는 핵심 설정입니다. `provider: google_cloud`로 설정하면 대부분의 필드가 자동으로 매핑되지만, 분석 목적에 따라 커스터마이징이 가능합니다.

### 4.1. 기본 필수 필드 매핑

`provider: google_cloud` 옵션이 활성화되면 아래 매핑이 자동으로 적용됩니다.

```yaml
field_mapper:
  cost: "cost"
  billed_date: "usage_start_time"
  currency: "currency"
  provider: "provider"
```

### 4.2. 분석을 위한 추가 정보(additional_info) 매핑

SpaceONE 비용 분석 화면에서 더 많은 정보를 확인하려면 `additional_info`에 원하는 필드를 매핑합니다. 아래는 추천 매핑 예시입니다.

```yaml
field_mapper:
  # ... 기본 필드 ...
  additional_info:
    # --- 비용 및 할인 관련 --- #
    cost_at_list: "cost_at_list"       # 유효 할인율 계산에 필요
    credits: "credits"                # 크레딧 상세 분석에 필요

    # --- 리소스 및 계층 구조 --- #
    billing_account_id: "billing_account_id"
    project_id: "project.id"
    project_name: "project.name"
    service_description: "service.description"
    sku_description: "sku.description"

    # --- 위치 및 시간 --- #
    location_region: "location.region"
    invoice_month: "invoice.month"

    # --- 태그 및 라벨 --- #
    project_labels: "project.labels"
    labels: "labels"
    tags: "tags"
```

---


## 5. 플러그인을 활용한 비용 분석

플러그인과 `field_mapper`를 올바르게 설정하면, SpaceONE 비용 분석 페이지에서 Google Cloud Billing 보고서와 유사한, 혹은 더 강력한 분석을 수행할 수 있습니다.

### 5.1. 크레딧(Credits) 분석

`additional_info.credits`에 `credits` 필드를 매핑하면, 각 비용 항목에 어떤 할인이 적용되었는지 상세히 확인할 수 있습니다. `credits` 필드는 배열(record) 형태로, 다음과 같은 정보를 포함합니다.

```json
"credits": [
  {
    "name": "Sustained Use Discount",
    "amount": -0.123,
    "type": "SUSTAINED_USAGE_DISCOUNT"
  }
]
```

**활용 방안**:
- SpaceONE 비용 분석에서 `additional_info.credits.type` 필드를 기준으로 그룹화하여, **약정 사용 할인(CUD)과 지속 사용 할인(SUD)의 기여도를 비교**할 수 있습니다.
- 특정 프로모션 크레딧(`name` 기준)이 적용된 비용만 필터링하여 효과를 측정할 수 있습니다.

### 5.2. 유효 할인율(Effective Discount) 분석

`cost` (실제 비용)와 `cost_at_list` (정가) 필드를 모두 수집하면, 계약에 따른 실질적인 할인 혜택을 분석할 수 있습니다.

**필드 매핑**:
```yaml
field_mapper:
  cost: "cost"
  additional_info:
    cost_at_list: "cost_at_list"
```

**활용 방안**:
- SpaceONE의 대시보드나 위젯에서 `(cost_at_list - cost) / cost_at_list` 공식을 사용하여 **평균 유효 할인율을 시각화**할 수 있습니다.
- 서비스별, 프로젝트별 유효 할인율을 비교하여 할인 혜택이 특정 영역에 집중되고 있는지 파악할 수 있습니다.

### 5.3. 비용 그룹화 및 필터링

Google Cloud Billing 보고서의 그룹화 및 필터 기능은 SpaceONE에서 더욱 유연하게 구현할 수 있습니다.

- **그룹화(Group By)**: `project.name`, `service.description`, `labels.key` 등 `field_mapper`로 매핑한 거의 모든 필드를 기준으로 비용을 그룹화하여 다차원적인 분석을 수행할 수 있습니다.
- **필터링(Filtering)**: `task_options`을 사용하여 특정 조건에 맞는 데이터만 동기화하거나, SpaceONE 비용 분석 페이지에서 특정 프로젝트, 라벨, 태그 값으로 비용을 필터링할 수 있습니다.

---


## 6. 고급 설정

### 6.1. 특정 파일만 처리 (File Pattern Filtering)

`task_options`에 `file_pattern`을 설정하여 특정 패턴의 파일만 처리할 수 있습니다. 월별로 생성되는 파일 중 특정 월의 데이터만 가져올 때 유용합니다.

```yaml
# task_options 설정 예시
task_options:
  file_pattern: "gcp_billing_export_v1_01XXXX-XXXXXX-XXXXXX_202407.csv"
```

### 6.2. 날짜 범위 필터링

`date_range`를 설정하여 특정 날짜 범위의 데이터만 처리할 수 있습니다. 파일명에 날짜 정보가 없는 경우 유용합니다.

```yaml
# task_options 설정 예시
task_options:
  date_range:
    start_date: "2024-07-01"
    end_date: "2024-07-31"
```

---


## 7. 문제 해결

- **인증 오류**: `secret_data`에 서비스 계정 키가 올바르게 입력되었는지, 키가 만료되지 않았는지 확인하세요.
- **권한 오류**: 서비스 계정에 `Storage 개체 뷰어` 역할이 제대로 부여되었는지 확인하세요.
- **데이터 누락**: Billing Export가 활성화된 시점 이후의 데이터만 수집됩니다. 또한, `task_options`의 필터 조건이 너무 엄격하지 않은지 확인하세요.

---


## 8. 참고 자료

- **[Google Cloud Billing 데이터 분석 가이드](./Google%20Cloud%20Billing.md)**
- **[BigQuery로 Billing 데이터 내보내기 (Google 공식 문서)](https://cloud.google.com/billing/docs/how-to/export-data-bigquery?hl=ko)**
- **[SpaceONE 플러그인 개발 가이드](https://spaceone.io/docs/guides/developer/plugin-development/)**