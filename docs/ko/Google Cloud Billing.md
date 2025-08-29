# Google Cloud Billing 데이터 분석 가이드

이 문서는 BigQuery로 내보낸 Cloud Billing 데이터의 스키마를 상세히 설명하고, 이를 활용한 비용 분석 방법을 안내합니다. SpaceONE 플러그인은 이 데이터를 기반으로 동작하므로, 데이터 구조를 이해하는 것은 매우 중요합니다.

## BigQuery Billing Export 데이터 스키마

BigQuery로 내보내는 Google Cloud Billing 데이터는 `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` 형식의 테이블에 저장됩니다. 이 데이터는 **표준 사용량 비용**과 **상세 사용량 비용** 두 가지 유형이 있으며, 상세 데이터가 더 많은 정보를 포함합니다.

> **권장 사항**: 정확한 리소스 수준의 비용 분석을 위해 **상세 사용량 비용 데이터 내보내기**를 활성화하는 것을 적극 권장합니다. 상세 데이터는 표준 데이터의 모든 필드를 포함하고 있어 호환성에 문제가 없습니다.
>
> - **[상세 사용량 비용 데이터 내보내기 설정 방법](https://cloud.google.com/billing/docs/how-to/export-data-bigquery#enable-detailed-usage-cost)**

### 데이터 스키마 상세 설명

다음은 BigQuery로 내보내는 데이터의 주요 필드에 대한 설명입니다.

| 필드 | 유형 | 설명 | 분석 활용 방안 |
| :--- | :--- | :--- | :--- |
| `billing_account_id` | `STRING` | 청구 계정 ID입니다. 리셀러의 경우 하위 계정 ID가 표시됩니다. | 여러 청구 계정을 사용하는 경우, 계정별 비용을 분리하는 기준이 됩니다. |
| `invoice.month` | `STRING` | 청구서가 발행된 월(YYYYMM 형식)입니다. | 월별 청구 비용을 정확히 집계하고 인보이스와 대조할 때 사용합니다. |
| `cost_type` | `STRING` | 비용 유형입니다. (예: `REGULAR`, `TAX`, `ADJUSTMENT`, `ROUNDING_ERROR`) | 세금, 정기 비용, 조정 금액 등을 분리하여 분석할 수 있습니다. |
| `service.description` | `STRING` | 비용이 발생한 Google Cloud 서비스입니다. (예: `Compute Engine`) | 서비스별 비용 분포를 파악하는 핵심 필드입니다. |
| `sku.description` | `STRING` | 서비스 내에서 사용된 구체적인 리소스 항목입니다. (예: `N1 Standard CPU`) | SKU 단위로 비용을 분석하여 가장 비용이 많이 드는 항목을 식별합니다. |
| `usage_start_time` | `TIMESTAMP` | 비용이 계산된 사용 기간의 시작 시간입니다. | **실제 리소스 사용일**을 기준으로 비용을 분석할 때 사용합니다. |
| `project.id` | `STRING` | 리소스를 소유한 Google Cloud 프로젝트의 ID입니다. | 프로젝트별 비용을 추적하고 할당하는 가장 기본적인 기준입니다. |
| `project.labels` | `RECORD` | 프로젝트에 할당된 라벨의 키-값 쌍입니다. | 조직의 비용 분류 체계(예: 팀, 환경)에 따라 비용을 분석할 때 유용합니다. |
| `labels` | `RECORD` | 개별 리소스에 할당된 라벨의 키-값 쌍입니다. | 리소스 단위의 세밀한 비용 분석 및 추적에 사용됩니다. |
| `location.region` | `STRING` | 리소스가 사용된 리전입니다. (예: `us-central1`) | 리전별 비용을 분석하여 특정 지역의 비용 집중도를 파악합니다. |
| `cost` | `FLOAT` | **크레딧 적용 후**의 실제 청구 비용입니다. | 실제 지불해야 하는 최종 비용을 나타냅니다. |
| `cost_at_list` | `FLOAT` | **크레딧 적용 전**의 정가(List Price)입니다. | 할인 및 크레딧의 효과를 계산하기 위한 기준 금액으로 사용됩니다. |
| `currency` | `STRING` | 비용이 청구된 통화입니다. | 다중 통화를 사용하는 경우, 통화별 비용을 분석하거나 기준 통화로 환산합니다. |
| `usage.amount` | `FLOAT` | `usage.unit` 단위로 측정된 리소스 사용량입니다. | 비용뿐만 아니라 실제 리소스 사용량을 분석하여 효율성을 측정합니다. |
| `credits` | `RECORD` | 적용된 크레딧의 상세 내역입니다. (이름, 유형, 금액 등) | 어떤 종류의 할인(CUD, SUD, 프로모션 등)이 얼마나 적용되었는지 상세히 분석합니다. |
| `tags` | `STRUCT` | 리소스에 연결된 태그 정보입니다. (키, 값, 네임스페이스 등) | 비용 할당, 접근 제어, 자동화 등 다양한 목적으로 비용을 분류하고 분석합니다. |

---

## 핵심 개념을 활용한 비용 분석

### 1. 사용일 기준 vs. 인보이스 월 기준

- **사용일 기준 (Usage Date)**: `usage_start_time` 필드를 사용하며, 리소스가 **실제로 사용된 시점**을 기준으로 비용을 집계합니다. 특정 기간의 리소스 소비 패턴을 분석하는 데 유용합니다.
- **인보이스 월 기준 (Invoice Month)**: `invoice.month` 필드를 사용하며, **청구서가 발행된 월**을 기준으로 비용을 집계합니다. 월별 재무 보고 및 인보이스 금액과 일치시키는 데 사용됩니다.

> **주의**: 월말에 발생한 사용량은 다음 달 인보이스에 포함될 수 있으므로, 두 기준의 집계 금액은 다를 수 있습니다.

### 2. 크레딧(Credits) 분석

Google Cloud는 다양한 크레딧을 제공하여 비용을 절감할 수 있도록 지원합니다. `credits` 필드는 적용된 모든 크레딧의 상세 정보를 담고 있는 배열(record)입니다.

- **주요 크레딧 유형**:
  - **약정 사용 할인 (CUDs)**: 1년 또는 3년 약정을 통해 받는 할인입니다.
  - **지속 사용 할인 (SUDs)**: 특정 사용량 이상을 꾸준히 사용할 때 자동으로 적용되는 할인입니다.
  - **프로모션 및 기타 크레딧**: 무료 체험, 마케팅 캠페인 크레딧 등입니다.

`credits` 레코드를 분석하면, 어떤 유형의 할인이 비용 절감에 얼마나 기여했는지 정확히 파악하고, 향후 비용 최적화 전략을 수립하는 데 활용할 수 있습니다.

- **[결제 보고서의 크레딧 분석 자세히 보기](https://cloud.google.com/billing/docs/how-to/reports?hl=ko#credits)**

### 3. 유효 할인 (Effective Discount) 분석

맞춤 가격 계약이 있는 경우, 정가와 실제 청구 비용의 차이를 통해 **유효 할인율**을 계산할 수 있습니다. 이는 계약에 따른 할인 혜택을 정확히 측정하는 데 중요합니다.

- **계산 공식**: `유효 할인율 = (정가 - 계약 가격) / 정가 × 100`
- **BigQuery 필드**:
  - **정가 (List Price)**: `cost_at_list`
  - **계약 가격 (Contract Price)**: `cost`

이 두 필드를 사용하여 할인율을 계산하고, 계약 조건이 비용에 미치는 영향을 정량적으로 분석할 수 있습니다.

- **[가격표 보고서의 유효 할인 자세히 보기](https://cloud.google.com/billing/docs/how-to/pricing-table?hl=ko#effective-discount)**

---

## BigQuery 쿼리 예시

다음은 BigQuery에서 직접 데이터를 조회할 때 사용할 수 있는 유용한 쿼리 예시입니다.

**쿼리 실행 시 주의사항**: `FROM` 절의 `project.dataset.gcp_billing_export_v1_...` 부분을 실제 환경에 맞게 수정해야 합니다.

### 예시 1: 인보이스 월별 총 비용 계산
각 인보이스 월의 최종 비용(크레딧 적용 후)을 계산합니다.

```sql
SELECT
  invoice.month,
  SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS total_cost
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
GROUP BY
  1
ORDER BY
  1 ASC;
```

### 예시 2: 프로젝트별, 라벨별 비용 분석
`app`이라는 라벨 키를 기준으로 프로젝트별 비용을 분류합니다.

```sql
SELECT
  project.name,
  (SELECT value FROM UNNEST(labels) WHERE key = 'app') as app_label,
  SUM(cost) as cost
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
GROUP BY
  1, 2
ORDER BY
  1, 2;
```

### 예시 3: 크레딧 유형별 할인 금액 집계
월별로 어떤 종류의 크레딧이 얼마나 적용되었는지 상세히 보여줍니다.

```sql
SELECT
  invoice.month,
  c.type,
  SUM(c.amount) as total_credit_amount
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`,
  UNNEST(credits) AS c
GROUP BY
  1, 2
ORDER BY
  1, 2;
```

---

## 관련 공식 문서

- **[BigQuery로 Billing 데이터 내보내기](https://cloud.google.com/billing/docs/how-to/export-data-bigquery?hl=ko)**
- **[표준 사용량 비용 데이터 스키마](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage?hl=ko)**
- **[결제 보고서 및 비용 추세 분석](https://cloud.google.com/billing/docs/how-to/reports?hl=ko)**
