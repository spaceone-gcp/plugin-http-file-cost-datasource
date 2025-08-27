# 표준 데이터 내보내기의 구조

이 문서에서는 BigQuery의 각 테이블로 내보내는 Cloud Billing 표준 사용량 비용 데이터의 스키마에 대한 참조 정보를 제공합니다.

---

## 표준 사용량 비용 데이터의 스키마

BigQuery 데이터 세트에서 표준 Google Cloud 사용량 비용 데이터가 `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`라는 데이터 테이블에 로드됩니다.

다음 정보는 BigQuery로 내보내는 Google Cloud 표준 사용량 비용 데이터의 스키마를 설명합니다. 이 스키마에는 계정 ID, 인보이스 날짜, 서비스, SKU, 프로젝트, 라벨, 위치, 비용, 사용량, 크레딧, 조정, 통화 등 표준 Cloud Billing 계정 비용 사용량 정보가 포함됩니다.

BigQuery에서 표준 사용량 비용 데이터를 사용하는 경우 다음에 유의하세요.

*   표준 사용량 비용 데이터에 BigQuery 데이터 세트를 만들거나 선택할 때 Cloud Billing 데이터에서 사용할 수 있도록 지원되는 [데이터 세트 위치](https://cloud.google.com/bigquery/docs/locations)를 선택할 수 있습니다.
*   Cloud Billing에서 표준 사용량 비용 데이터 내보내기를 처음 사용 설정할 때 멀티 리전 위치(EU 또는 미국)를 사용하도록 구성된 데이터 세트를 선택하면 Cloud Billing 데이터가 이전 달 초부터 소급되어 제공됩니다. 시간순으로 데이터를 내보냅니다. 내보낸 데이터의 초기 백필의 경우 최신 사용 데이터가 표시되기 전에 소급 Cloud Billing 데이터 내보내기가 완료되는 데 최대 5일이 걸릴 수 있습니다.
*   표준 사용량 비용 데이터 내보내기를 사용 설정하고 지원되는 [리전 위치](https://cloud.google.com/bigquery/docs/locations)를 사용하도록 구성된 데이터 세트를 선택하면 Cloud Billing 데이터가 내보내기를 사용 설정한 날짜부터 제공됩니다.
*   표준 사용량 비용 데이터 내보내기를 사용 설정한 후 중지했다가 다시 사용 설정한 경우, 데이터 내보내기가 명시적으로 중단된 기간 동안에는 Cloud Billing 데이터를 사용할 수 없습니다.
*   BigQuery 테이블에 로드되는 데이터의 빈도에 대해 자세히 알아보세요.
*   표준 사용량 비용 데이터에는 서비스 사용량을 발생시키는 가상 머신 또는 SSD와 같은 리소스 수준 비용 데이터가 포함되지 않습니다. 분석을 위해 리소스 수준 비용 데이터를 BigQuery로 내보내려면 [상세 사용량 비용 데이터 내보내기](https://cloud.google.com/billing/docs/how-to/export-data-bigquery#enable-detailed-usage-cost)를 사용 설정하는 것이 좋습니다.
*   내보낸 자세한 사용 비용 데이터에는 표준 사용 비용 데이터에 포함된 모든 필드 및 정보가 포함됩니다.
*   고객 관리 암호화 키(CMEK)가 사용 설정된 데이터 세트와 같이 BigQuery로 결제 데이터를 내보내는 데 영향을 줄 수 있는 다른 [제한사항](https://cloud.google.com/billing/docs/how-to/export-data-bigquery#limitations)을 참조하세요.

| 필드 | 유형 | 설명 |
| :--- | :--- | :--- |
| `billing_account_id` | `STRING` | 사용량에 연결된 Cloud Billing 계정 ID입니다. 리셀러: Cloud Billing 하위 계정을 통해 사용량 비용이 생성된 경우 상위 리셀러 Cloud Billing 계정 ID가 아닌 하위 계정 ID입니다. |
| `invoice.month` | `STRING` | 비용 항목이 포함된 인보이스의 연도 및 월(YYYYMM)입니다. 예: '201901'은 2019년 1월입니다. |
| `invoice.publisher_type` | `STRING` | 거래와 연결된 게시자를 나타냅니다. 사용할 수 있는 값: `GOOGLE`, `PARTNER`. |
| `cost_type` | `STRING` | 정기 비용, 세금, 조정 또는 반올림 오류 등 이 항목이 나타내는 비용 유형입니다. |
| `service.id` | `STRING` | 사용량에 연결된 서비스의 ID입니다. |
| `service.description` | `STRING` | Cloud Billing 데이터를 보고한 Google Cloud 서비스입니다. |
| `sku.id` | `STRING` | 서비스에서 사용한 리소스의 ID입니다. |
| `sku.description` | `STRING` | 서비스에서 사용한 리소스 유형에 대한 설명입니다. |
| `usage_start_time` | `TIMESTAMP` | 주어진 비용이 계산된 시간별 사용 기간의 시작 시간입니다. |
| `usage_end_time` | `TIMESTAMP` | 주어진 비용이 계산된 시간별 사용 기간의 종료 시간입니다. |
| `project` | `STRUCT` | 프로젝트 ID, 숫자, 이름, 상위 항목, 라벨 등 Cloud Billing 프로젝트를 설명하는 필드가 포함됩니다. |
| `project.id` | `STRING` | Cloud Billing 데이터를 생성한 Google Cloud 프로젝트의 ID입니다. |
| `project.number` | `STRING` | Cloud Billing 데이터를 생성한 Google Cloud 프로젝트의 내부적으로 생성되고 익명 처리된 고유 식별자입니다. |
| `project.name` | `STRING` | Cloud Billing 데이터를 생성한 Google Cloud 프로젝트의 이름입니다. |
| `project.ancestry_numbers` | `STRING` | 명시된 `project.id`로 식별된 프로젝트에 대한 리소스 계층 구조의 상위 항목입니다. 예: `/ParentOrgNumber/ParentFolderNumber/`. |
| `project.ancestors` | `STRUCT` | 프로젝트, 폴더, 조직을 포함하여 비용 항목의 리소스 계층 구조의 구조체 및 값에 대해 설명합니다. |
| `project.labels` | `RECORD` | 사용량이 발생한 Google Cloud 프로젝트의 라벨을 구성하는 키-값 쌍입니다. |
| `labels` | `RECORD` | 사용량이 발생한 Google Cloud 리소스의 라벨을 구성하는 키-값 쌍입니다. |
| `system_labels` | `RECORD` | 사용량이 발생한 리소스의 시스템 생성 라벨을 구성하는 키-값 쌍입니다. |
| `location` | `STRUCT` | 사용량이 발생한 위치에 대한 세부정보입니다. |
| `location.location` | `STRING` | 멀티 리전, 국가, 리전 또는 영역 수준의 사용량이 발생한 위치입니다. |
| `location.country` | `STRING` | 사용량이 발생한 국가입니다(예: `US`). |
| `location.region` | `STRING` | 사용량이 발생한 리전입니다(예: `us-central1`). |
| `location.zone` | `STRING` | 사용량이 발생한 영역입니다(예: `us-central1-a`). |
| `cost` | `FLOAT` | 크레딧 적용 전 사용 비용입니다. |
| `currency` | `STRING` | 청구된 비용의 통화입니다. |
| `currency_conversion_rate` | `FLOAT` | 미국 달러와 현지 통화의 환율입니다. |
| `usage` | `STRUCT` | 사용량에 대한 세부정보입니다. |
| `usage.amount` | `FLOAT` | 사용한 `usage.unit`의 양입니다. |
| `usage.unit` | `STRING` | 리소스 사용량을 측정하는 기본 단위입니다. |
| `usage.amount_in_pricing_units` | `FLOAT` | 사용한 `usage.pricing_unit`의 양입니다. |
| `usage.pricing_unit` | `STRING` | Cloud Billing Catalog API에 따른 리소스 사용량 측정 단위입니다. |
| `credits` | `RECORD` | Google Cloud 및 Google Maps Platform SKU와 관련된 크레딧의 구조와 값을 설명하는 필드가 포함됩니다. 크레딧 레코드에는 `type`, `name`, `amount`, `full_name` 등의 필드가 포함될 수 있습니다. 크레딧 유형에는 약정 사용 할인(CUD), 지속 사용 할인(SUD), 프로모션 크레딧 등이 있습니다. |
| `adjustment_info` | `STRUCT` | Cloud Billing 계정과 연결된 비용 항목에 대한 조정 값과 구조를 설명하는 필드가 포함됩니다. |
| `export_time` | `TIMESTAMP` | Cloud Billing 데이터 추가와 연결된 처리 시간입니다. |
| `tags` | `STRUCT` | 키, 값, 네임스페이스 등 태그를 설명하는 필드입니다. |
| `cost_at_list` | `FLOAT` | Cloud Billing 계정에 청구되는 모든 항목과 연결된 정가입니다. |
| `transaction_type` | `STRING` | 판매자의 거래 유형입니다. (`GOOGLE`, `THIRD_PARTY_RESELLER`, `THIRD_PARTY_AGENCY`) |
| `seller_name` | `STRING` | 판매자의 법적 이름입니다. |

---

## 표준 및 세부 사용량 비용 데이터 이해하기

### 라벨 정보
특정 라벨의 비용 데이터에는 해당 라벨이 리소스에 적용된 날짜 이후의 사용량만 표시됩니다.

#### 사용 가능한 시스템 라벨
시스템 라벨은 사용량을 생성한 리소스에 대한 중요 메타데이터의 키-값 쌍입니다.

| system_labels.key | 예시 system_labels.value | 설명 |
| :--- | :--- | :--- |
| `compute.googleapis.com/machine_spec` | `n1-standard-1`, `custom-2-2048` | 가상 머신의 구성입니다. |
| `compute.googleapis.com/cores` | `n1-standard-4`의 경우는 `4` | 가상 머신에 사용할 수 있는 vCPU 수입니다. |
| `compute.googleapis.com/memory` | `n1-standard-4`의 경우는 `15360` | 가상 머신에 사용할 수 있는 메모리 양(MB)입니다. |
| `compute.googleapis.com/is_unused_reservation` | `true`; `false` | 영역별 예약을 통해 예약되었지만 사용되지 않은 사용량을 나타냅니다. |
| `storage.googleapis.com/object_state` | `live`; `noncurrent`; `soft_deleted`; `multipart` | 청구 중인 스토리지 객체의 상태입니다. |

### 결제 보고서와 내보낸 데이터 비교

Google Cloud 콘솔의 결제 보고서는 BigQuery로 내보낸 비용 데이터와 동일한 데이터를 기반으로 생성됩니다. 보고서는 데이터를 시각화하고 분석하는 데 유용한 도구이지만, 내보낸 데이터는 더 상세한 분석과 다른 시스템과의 통합을 위한 원시 데이터를 제공합니다.

#### 시간 범위: 사용일 기준 vs. 인보이스 월 기준

결제 보고서와 쿼리에서 시간 범위를 설정할 때 두 가지 주요 기준을 사용할 수 있습니다.

*   **사용일 기준 (Usage date)**: 리소스가 실제로 사용된 날짜를 기준으로 비용을 집계합니다. `usage_start_time` 필드를 사용하여 쿼리할 수 있습니다. 이 방식은 특정 기간 동안의 실제 리소스 소비를 파악하는 데 유용합니다.
*   **인보이스 월 기준 (Invoice month)**: 비용이 청구된 인보이스의 월을 기준으로 비용을 집계합니다. `invoice.month` 필드를 사용하여 쿼리할 수 있습니다. 이 방식은 월별 청구 금액을 인보이스와 정확히 일치시키는 데 사용됩니다. 월말에 발생한 사용량은 다음 달 인보이스에 포함될 수 있으므로, 사용일 기준 집계와 차이가 있을 수 있습니다.

#### 크레딧 분석

결제 보고서에서는 다양한 유형의 크레딧(예: 약정 사용 할인, 프로모션 크레딧)이 비용에 어떻게 영향을 미치는지 시각적으로 확인할 수 있습니다. 내보낸 데이터의 `credits` 레코드를 쿼리하면 각 크레딧 유형별 상세 내역을 프로그래매틱하게 분석할 수 있습니다.

### 내보낸 데이터와 인보이스의 차이점
Google Cloud 제품은 다양한 간격으로 사용량 및 비용 데이터를 보고하므로 지연이 발생할 수 있습니다. 월말에 보고된 사용량은 다음 달 인보이스로 이월될 수 있습니다. 인보이스에 직접 매핑되는 데이터를 원하면 `usage_start_time` 대신 `invoice.month`를 쿼리하세요.

### 세금
2020년 9월 1일부터 세금 책임이 단일 항목이 아니라 프로젝트별로 표시됩니다.

### 오류 및 조정
데이터에 오류가 있거나 조정이 필요한 경우, 수정 데이터가 추가됩니다. 이러한 조정은 **결제 수정사항** 또는 **수정사항** 두 가지 카테고리 중 하나에 해당합니다. 수정사항은 원래 데이터를 무효화하고 새로운 데이터로 대체하여 표시됩니다.

### 유효 할인 (Effective Discount)

맞춤 가격 계약이 적용되는 Cloud Billing 계정의 경우, 가격표에 '적용 할인' 열이 표시될 수 있습니다. 이 할인은 다음 수식을 사용하여 계산됩니다.

`적용 할인 = (정가 - 계약 가격) / 정가 × 100`

- **정가 (List Price)**: `cost_at_list` 필드에 해당합니다.
- **계약 가격 (Contract Price)**: 실제 청구되는 `cost` 필드에 해당합니다.

정가와 계약 가격이 모두 0인 경우, '적용 할인' 필드는 '할인율(%)' 필드와 동일한 값을 가집니다. 이 정보는 비용 분석 및 할인 혜택을 정확히 파악하는 데 중요합니다.

### 태그 정보
태그는 리소스에 직접 또는 상속을 통해 연결할 수 있는 키-값 쌍 형식의 리소스입니다. 비용 할당 분석, 감사 등에 사용됩니다.

*   **사용 가능한 태그**: 리소스, 프로젝트, 폴더, 조직의 비용 내보내기에 태그 데이터가 포함됩니다.
*   **태그 제한사항**: 태그가 BigQuery 내보내기에 전파되는 데 최대 1시간이 걸릴 수 있습니다.

---

## 표준 사용량 비용 쿼리 예시

### 쿼리에 사용할 테이블 이름 지정
쿼리에서 `FROM` 절에 테이블 이름을 `project.dataset.BQ_table_name` 형식으로 지정해야 합니다.
*   **project**: BigQuery 데이터 세트가 포함된 Google Cloud 프로젝트 ID
*   **dataset**: 내보낸 데이터가 포함된 BigQuery 데이터 세트
*   **BQ_table_name**: `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`

### 인보이스의 총 비용 반환

#### 예시 1: 인보이스당 모든 비용 합계
이 쿼리는 각 월의 인보이스 합계를 보여줍니다.

```sql
SELECT
  invoice.month,
  SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS total,
  (SUM(CAST(cost * 1000000 AS int64)) + SUM(IFNULL((SELECT SUM(CAST(c.amount * 1000000 as int64)) FROM UNNEST(credits) c), 0))) / 1000000 AS total_exact
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
GROUP BY
  1
ORDER BY
  1 ASC;
```

#### 예시 2: 인보이스 대상 월당 비용 유형별 세부정보 반환
이 쿼리는 월별로 각 `cost_type`의 합계를 보여줍니다.

```sql
SELECT
  invoice.month,
  cost_type,
  SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS total,
  (SUM(CAST(cost * 1000000 AS int64)) + SUM(IFNULL((SELECT SUM(CAST(c.amount * 1000000 as int64)) FROM UNNEST(credits) c), 0))) / 1000000 AS total_exact
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
GROUP BY
  1, 2
ORDER BY
  1 ASC, 2 ASC;
```

### 라벨이 있는 쿼리 예시

#### 라벨 맵에 따라 JSON 문자열로 그룹화
비용을 라벨 조합별로 분류하는 방법입니다.

```sql
SELECT
  TO_JSON_STRING(labels) as labels,
  sum(cost) as cost
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
GROUP BY
  labels;
```

#### 라벨 값의 특정 키에 따라 그룹화

```sql
SELECT
  (SELECT value FROM UNNEST(labels) WHERE key = 'app') as app,
  sum(cost) as cost
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
GROUP BY
  app;
```

#### 키-값 쌍으로 그룹화

```sql
SELECT
  label.key,
  label.value,
  sum(cost) as cost
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`,
  UNNEST(labels) as label
GROUP BY
  label.key,
  label.value;
```

### 약정 사용 할인 쿼리

#### 약정 수수료 보기

```sql
SELECT
    invoice.month,
    SUM(cost) as commitment_fees
FROM
    `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
WHERE
    sku.description LIKE '%Commitment%'
GROUP BY
    1
ORDER BY
    1;
```

#### 약정 크레딧 보기

```sql
SELECT
    invoice.month,
    SUM(c.amount) as commitment_credits
FROM
    `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`,
    UNNEST(credits) AS c
WHERE
    c.type LIKE 'COMMITTED_USAGE_DISCOUNT%'
GROUP BY
    1
ORDER BY
    1;
```

### 크레딧 유형별 합계 보기

이 쿼리는 각 크레딧 유형(`c.type`)별로 크레딧 금액의 합계를 계산하여 월별로 보여줍니다.

```sql
SELECT
  invoice.month,
  c.type,
  SUM(c.amount) as total_credits
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`,
  UNNEST(credits) AS c
GROUP BY
  1, 2
ORDER BY
  1, 2;
```

### 태그가 있는 쿼리 예시

#### 태그를 사용하여 인보이스 대상 월별 비용 계산

```sql
SELECT
  invoice.month,
  tag.key,
  tag.value,
  SUM(cost)
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`,
  UNNEST(tags) AS tag
GROUP BY
  1,
  2,
  3
;
```

#### 태그가 지정되지 않은 리소스의 비용 보기

```sql
SELECT
  invoice.month,
  SUM(cost)
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
WHERE
  (SELECT COUNT(tag.key) FROM UNNEST(tags) AS tag) = 0
GROUP BY
  1
;
```

### 추가 쿼리 예시

#### 지정된 인보이스 대상 월에 프로젝트별 비용 및 크레딧 쿼리

```sql
SELECT
  project.name,
  invoice.month,
  SUM(cost) as total_cost,
  SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) as total_credits
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
WHERE
  invoice.month = '202010'
GROUP BY
  1, 2
ORDER BY
  1;
```

---

## 관련 주제

*   [내보낸 Cloud Billing 데이터와 관련된 주제](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables)
*   [Google Cloud 콘솔에서 사용 가능한 비용 및 가격 책정 보고서](https://cloud.google.com/billing/docs/how-to/reports)