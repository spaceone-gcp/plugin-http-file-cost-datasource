# Google Cloud Billing 통합 가이드

이 문서는 SpaceONE HTTP 파일 비용 데이터 소스 플러그인을 사용하여 Google Cloud Billing Export 데이터를 처리하는 방법을 설명합니다.

## 목차
1. [개요](#1-개요)
2. [Google Cloud Billing Export 설정](#2-google-cloud-billing-export-설정)
3. [플러그인 설정](#3-플러그인-설정)
4. [필드 매핑](#4-필드-매핑)
5. [사용 예시](#5-사용-예시)
6. [고급 설정](#6-고급-설정)

---

## 1. 개요

Google Cloud Billing Export는 BigQuery로 내보내는 표준 사용량 비용 데이터를 제공합니다. 이 플러그인은 Google Cloud Storage에 저장된 Billing Export 데이터를 읽어와 SpaceONE에서 사용할 수 있는 형태로 변환합니다.

### 지원하는 데이터 형식
- CSV (쉼표로 구분된 값)
- JSON (JavaScript Object Notation)
- Parquet (컬럼 기반 데이터 형식)
- 압축된 파일 (.gz, .snappy, .zstd 등)

### 지원하는 Google Cloud Billing 필드
- `billing_account_id`: Cloud Billing 계정 ID
- `invoice.month`: 인보이스 월 (YYYYMM 형식)
- `service.id`, `service.description`: 서비스 정보
- `sku.id`, `sku.description`: SKU 정보
- `project.id`, `project.name`: 프로젝트 정보
- `location.location`, `location.region`, `location.zone`: 위치 정보
- `usage_start_time`, `usage_end_time`: 사용 시간 정보
- `cost`, `currency`: 비용 및 통화 정보
- `credits`: 크레딧 정보
- `tags`, `labels`: 태그 및 라벨 정보

---

## 2. Google Cloud Billing Export 설정

### 2.1. BigQuery Export 설정
1. Google Cloud Console에서 Billing 페이지로 이동
2. "Billing export" 메뉴 선택
3. "BigQuery export" 탭에서 "Edit settings" 클릭
4. 데이터 세트 선택 및 설정 완료

### 2.2. Google Cloud Storage Export 설정
1. Billing 페이지에서 "Billing export" 메뉴 선택
2. "File export" 탭에서 "Edit settings" 클릭
3. 버킷 선택 및 파일 형식 설정 (CSV 권장)
4. 내보내기 일정 설정

### 2.3. Service Account 설정
1. Google Cloud Console에서 IAM & Admin > Service Accounts로 이동
2. 새로운 Service Account 생성
3. 다음 권한 부여:
   - `Storage Object Viewer` (버킷 읽기)
   - `BigQuery Data Viewer` (BigQuery 읽기, 선택사항)

---

## 3. 플러그인 설정

### 3.1. 기본 설정 구조
```yaml
options:
  bucket_name: "your-billing-export-bucket"
  provider: "google_cloud"
  field_mapper:
    # 필드 매핑 설정
  default_vars:
    provider: "google_cloud"
    currency: "USD"

secret_data:
  # Service Account 키 정보
```

### 3.2. 필수 설정 항목
- `bucket_name`: Google Cloud Storage 버킷 이름
- `provider`: "google_cloud"로 설정
- `secret_data`: Service Account 키 정보

---

## 4. 필드 매핑

### 4.1. 기본 필수 필드
```yaml
field_mapper:
  cost: "cost"
  billed_date: "usage_start_time"
  provider: "google_cloud"
```

### 4.2. Google Cloud Billing 전용 필드
```yaml
field_mapper:
  # 기본 필드
  cost: "cost"
  billed_date: "usage_start_time"
  
  # Google Cloud Billing 필드
  billing_account_id: "billing_account_id"
  service_id: "service.id"
  service_description: "service.description"
  sku_id: "sku.id"
  sku_description: "sku.description"
  project_id: "project.id"
  project_name: "project.name"
  location_region: "location.region"
  location_zone: "location.zone"
  invoice_month: "invoice.month"
  usage_amount: "usage.amount"
  usage_unit: "usage.unit"
  currency: "currency"
  cost_type: "cost_type"
```

### 4.3. Additional Info 필드 매핑
```yaml
field_mapper:
  additional_info:
    billing_account_id: "billing_account_id"
    service_id: "service.id"
    service_description: "service.description"
    sku_id: "sku.id"
    sku_description: "sku.description"
    project_id: "project.id"
    project_number: "project.number"
    project_name: "project.name"
    location_location: "location.location"
    location_country: "location.country"
    location_region: "location.region"
    location_zone: "location.zone"
    invoice_month: "invoice.month"
    invoice_publisher_type: "invoice.publisher_type"
    cost_type: "cost_type"
    usage_amount: "usage.amount"
    usage_unit: "usage.unit"
    usage_amount_in_pricing_units: "usage.amount_in_pricing_units"
    usage_pricing_unit: "usage.pricing_unit"
    credits: "credits"
    adjustment_info: "adjustment_info"
    export_time: "export_time"
    cost_at_list: "cost_at_list"
    transaction_type: "transaction_type"
    seller_name: "seller_name"
    currency: "currency"
    currency_conversion_rate: "currency_conversion_rate"
    project_labels: "project.labels"
    labels: "labels"
    system_labels: "system_labels"
    tags: "tags"
```

---

## 5. 사용 예시

### 5.1. 기본 설정 예시
```yaml
options:
  bucket_name: "gcp-billing-export-bucket"
  provider: "google_cloud"
  field_mapper:
    cost: "cost"
    billed_date: "usage_start_time"
    billing_account_id: "billing_account_id"
    service_id: "service.id"
    project_id: "project.id"
    location_region: "location.region"
  default_vars:
    provider: "google_cloud"
    currency: "USD"

secret_data:
  type: "service_account"
  project_id: "your-project-id"
  private_key_id: "your-private-key-id"
  private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email: "your-service-account@your-project.iam.gserviceaccount.com"
  client_id: "your-client-id"
  auth_uri: "https://accounts.google.com/o/oauth2/auth"
  token_uri: "https://oauth2.googleapis.com/token"
  auth_provider_x509_cert_url: "https://www.googleapis.com/oauth2/v1/certs"
  client_x509_cert_url: "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
```

### 5.2. 고급 설정 예시
```yaml
options:
  bucket_name: "gcp-billing-export-bucket"
  provider: "google_cloud"
  field_mapper:
    cost: "cost"
    billed_date: "usage_start_time"
    additional_info:
      billing_account_id: "billing_account_id"
      service_id: "service.id"
      service_description: "service.description"
      sku_id: "sku.id"
      sku_description: "sku.description"
      project_id: "project.id"
      project_name: "project.name"
      location_region: "location.region"
      location_zone: "location.zone"
      invoice_month: "invoice.month"
      usage_amount: "usage.amount"
      usage_unit: "usage.unit"
      currency: "currency"
      cost_type: "cost_type"
      credits: "credits"
      tags: "tags"
  default_vars:
    provider: "google_cloud"
    currency: "USD"
  type_mapper:
    additional_info:
      Account ID: "billing_account_id"

task_options:
  bucket_name: "gcp-billing-export-bucket"
  file_pattern: "gcp_billing_export_v1_*.csv"
  date_range:
    start_date: "2024-01-01"
    end_date: "2024-12-31"
```

---

## 6. 고급 설정

### 6.1. 파일 패턴 필터링
특정 패턴의 파일만 처리하려면 `task_options`에 `file_pattern`을 설정합니다.

```yaml
task_options:
  bucket_name: "gcp-billing-export-bucket"
  file_pattern: "gcp_billing_export_v1_*.csv"
```

### 6.2. 날짜 범위 필터링
특정 날짜 범위의 데이터만 처리하려면 `date_range`를 설정합니다.

```yaml
task_options:
  bucket_name: "gcp-billing-export-bucket"
  date_range:
    start_date: "2024-01-01"
    end_date: "2024-12-31"
```

### 6.3. 크레딧 처리
Google Cloud Billing의 크레딧 정보를 처리하려면 `cost_metric`을 설정합니다.

```yaml
options:
  cost_metric: "AmortizedCost"  # 크레딧을 포함한 비용 계산
```

### 6.4. 유효 할인율 처리

Google Cloud Billing은 맞춤 가격 계약에 따라 유효 할인율을 제공할 수 있습니다. 이 할인율은 정가(`cost_at_list`)와 실제 청구 비용(`cost`)의 차이를 기반으로 계산됩니다.

자세한 내용은 [Google Cloud Billing의 유효 할인](Google%20Cloud%20Billing.md#유효-할인-effective-discount) 문서를 참고하세요.

이 플러그인을 사용하여 유효 할인율을 계산하고 분석하려면, `field_mapper` 설정에 `cost`와 `cost_at_list` 필드가 올바르게 매핑되었는지 확인해야 합니다.

```yaml
field_mapper:
  cost: "cost"
  additional_info:
    cost_at_list: "cost_at_list"
```

### 6.5. 다중 통화 지원
여러 통화의 데이터를 처리하려면 `currency_conversion_rate` 필드를 활용합니다.

```yaml
field_mapper:
  currency: "currency"
  additional_info:
    currency_conversion_rate: "currency_conversion_rate"
```

---

## 7. 플러그인을 활용한 비용 분석

Google Cloud Billing 보고서에서 제공하는 다양한 분석 기능을 이 플러그인을 사용하여 유사하게 구현할 수 있습니다. `field_mapper`와 `task_options`를 적절히 활용하면 비용 데이터를 원하는 방식으로 집계하고 필터링할 수 있습니다.

### 7.1. 크레딧 분석

Google Cloud에서 제공하는 다양한 크레딧(약정 사용 할인, 프로모션 등)은 비용에 큰 영향을 미칩니다. 내보낸 데이터의 `credits` 필드는 크레딧 상세 내역을 담고 있는 배열(record) 형태입니다.

`field_mapper`를 사용하여 `credits` 필드를 `additional_info`에 매핑하면 각 비용 항목에 적용된 크레딧 정보를 확인할 수 있습니다.

```yaml
field_mapper:
  cost: "cost"
  billed_date: "usage_start_time"
  additional_info:
    credits: "credits"
```

이렇게 매핑하면, 데이터 소스 동기화 후 각 비용 데이터의 `additional_info.credits` 필드에서 다음과 같은 형태의 크레딧 정보를 확인할 수 있습니다.

```json
"credits": [
  {
    "name": "Sustained Use Discount",
    "amount": -0.123,
    "type": "SUSTAINED_USAGE_DISCOUNT"
  }
]
```

이 정보를 활용하여 크레딧 유형별 할인 금액을 집계하거나, 특정 크레딧이 적용된 비용 항목을 필터링하는 등 상세한 분석이 가능합니다.

### 7.2. 비용 그룹화

결제 보고서의 그룹화 기능처럼, 특정 기준으로 비용을 집계하고 싶을 때가 있습니다. `field_mapper`를 사용하여 원하는 그룹화 기준 필드(예: `project.name`, `service.description`)를 매핑하면, SpaceONE의 비용 분석 기능에서 해당 기준으로 비용을 그룹화하여 볼 수 있습니다.

```yaml
field_mapper:
  # ... (기본 필드)
  project_name: "project.name"
  service_description: "service.description"
  sku_description: "sku.description"
  additional_info:
    cost_type: "cost_type"
```

### 7.3. 데이터 필터링

결제 보고서의 기간 필터나 프로젝트 필터처럼, `task_options`를 사용하여 처리할 데이터의 범위를 좁힐 수 있습니다.

- **날짜 범위 필터링**: `date_range` 옵션을 사용하여 특정 기간의 데이터만 동기화합니다.
- **파일 패턴 필터링**: `file_pattern` 옵션을 사용하여 특정 파일명의 데이터만 처리합니다. 이는 특정 월이나 특정 데이터 형식의 파일만 선택적으로 처리할 때 유용합니다.

자세한 내용은 [고급 설정](#6-고급-설정) 섹션을 참고하세요.

---

## 8. 문제 해결

### 8.1. 일반적인 오류
- **인증 오류**: Service Account 키가 올바르게 설정되었는지 확인
- **권한 오류**: Service Account에 적절한 권한이 부여되었는지 확인
- **파일 형식 오류**: 지원하는 파일 형식인지 확인

### 8.2. 디버깅
- 로그에서 "Google Cloud Billing 데이터인지 확인" 메시지 확인
- `additional_info` 필드에 Google Cloud Billing 데이터가 포함되었는지 확인
- 필드 매핑이 올바르게 설정되었는지 확인

---

## 9. 참고 자료

- [Google Cloud Billing Export 문서](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Google Cloud Storage 문서](https://cloud.google.com/storage/docs)
- [SpaceONE 플러그인 개발 가이드](https://spaceone.io/docs/guides/developer/plugin-development/)
