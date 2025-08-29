# plugin-http-file-cost-datasource

SpaceONE의 비용 분석(cost-analysis) 서비스에서 사용하는 플러그인으로, 다양한 소스로부터 비용 데이터를 수집합니다.

- **주요 기능**: CSV, JSON, Parquet 형식의 파일에서 비용 데이터를 수집합니다.
- **지원 소스**: HTTP/HTTPS URL, Google Cloud Storage, Google Cloud Billing Export
- **특징**: 연결된 계정 정보 조회 및 다양한 파일 포맷 자동 감지

---

## 목차
1.  [개요](#1-개요)
2.  [지원 파일 형식](#2-지원-파일-형식)
3.  [플러그인 옵션](#3-플러그인-옵션)
4.  [CI/CD 및 품질 관리](#4-cicd-및-품질-관리)
5.  [사용 방법 (Deprecated)](#5-사용-방법-deprecated)
6.  [문제 해결](#6-문제-해결)
7.  [연결 계정(Linked Accounts) 기능](#7-연결-계정linked-accounts-기능)

---

## 1. 개요

이 플러그인은 CSV, JSON, Parquet 형식의 파일로부터 비용 데이터를 수집하여 SpaceONE 비용 분석 서비스와 연동하는 것을 목표로 합니다. 파일은 웹 서버(HTTP/HTTPS) 또는 Google Cloud Storage에 위치할 수 있으며, Google Cloud Billing Export에서 직접 데이터를 가져오는 기능도 지원합니다.

파일 형식과 플러그인 옵션에 대한 자세한 내용은 아래 섹션을 참고해 주십시오.

## 2. 지원 파일 형식

![img.png](examples/img.png)
*위 이미지는 CSV 파일의 예시입니다.*

### 2.1. 필수 및 선택 필드
- **필수 필드**: `cost`
- **날짜 필드 (아래 조건 중 하나 충족)**: 
  1. `billed_date` 필드 (예: "2023-09-01")
  2. `year`, `month`, `day` 필드
  3. `year`, `month` 필드 (이 경우 `day`는 1일로 자동 설정)
- **선택 필드**: `usage_quantity`, `usage_type`, `provider`, `region_code`, `product` 등

### 2.2. 지원 포맷 상세

#### CSV 파일
- **구분자**: 쉼표(,), 세미콜론(;), 탭(\t), 파이프(|)를 자동으로 감지합니다.
- **인코딩**: UTF-8, UTF-8-BOM 등 다양한 인코딩을 자동으로 감지합니다.
- **헤더**: 반드시 헤더 행(컬럼명)이 존재해야 합니다.

#### JSON 파일
- **형식**: 각 줄이 개별 JSON 객체인 JSON Lines(JSONL) 형식을 지원합니다.
- **인코딩**: UTF-8을 지원합니다.

#### Parquet 파일
- **엔진**: `pyarrow`와 `fastparquet` 엔진을 모두 지원합니다.
- **압축 형식**: `.parquet.gz`, `.parquet.snappy`, `.parquet.zst` 등 다양한 압축 포맷을 지원합니다.

### 2.3. Google Cloud Billing Export 필드
Google Cloud Billing Export 데이터의 경우, `billing_account_id`, `service.id`, `project.name` 등 표준 빌링 필드를 지원합니다. 상세 필드 매핑 정보는 [Google Cloud Billing Integration Guide](docs/ko/Google%20Cloud%20Billing%20Integration.md) 문서를 참고하십시오.

---

## 3. 플러그인 옵션

플러그인 옵션은 YAML 형식으로 지정하며, 데이터 소스를 등록하거나 업데이트할 때 사용합니다.

```yaml
# update_data_source_options.yml 예시
---
options:
  base_url:
    - https://.../cost_example.csv
  field_mapper:
    cost: TotalCost
    currency: CurrencyCode
  default_vars:
    currency: KRW
```

- **`base_url` (필수)**: 비용 데이터 파일의 URL 목록입니다.
- **`field_mapper` (선택)**: 파일의 컬럼명이 표준 필드와 다를 경우 매핑 정보를 지정합니다.
- **`default_vars` (선택)**: 특정 필드에 기본값을 설정하고 싶을 때 사용합니다.
- **Google Cloud Storage (선택)**: `bucket_name`, `provider` 등의 옵션과 `secret_data`를 통해 GCS 연동을 설정합니다.

---

## 4. CI/CD 및 품질 관리

이 프로젝트는 GitHub Actions를 통한 자동화된 검증과 개발자 로컬 환경에서의 수동 검증을 통해 코드의 품질과 안정성을 유지합니다.

### 4.1. 로컬 개발 환경에서의 품질 관리

Pull Request를 생성하기 전, 모든 개발자는 로컬 환경에서 다음 절차를 통해 코드 품질을 **반드시** 검증해야 합니다.

1.  **린트 검사 및 포맷팅**: `Ruff`를 사용하여 코드 스타일을 검사하고 수정합니다.
    ```bash
    # 린트 검사 및 자동 수정
    ruff check src/ --fix
    
    # 포맷팅 적용
    ruff format src/
    ```

2.  **단위 및 통합 테스트**: `pytest`를 실행하여 모든 테스트가 통과(`PASSED`)하는지 확인합니다.
    ```bash
    pytest
    ```
상세한 규칙은 `.cursor/rules/project-rules.mdc` 문서를 참고하십시오.

### 4.2. 자동화된 검증 프로세스
GitHub Actions를 통해 CI/CD 파이프라인이 운영되며, 주요 절차는 다음과 같습니다.

1.  **커밋 서명 확인**: 모든 커밋은 DCO(Developer Certificate of Origin)를 준수하기 위해 서명되어야 합니다.
2.  **도커 이미지 빌드**: 변경 사항이 적용된 플러그인 실행 환경을 도커 이미지로 빌드합니다.
3.  **보안 취약점 스캔**: 빌드된 도커 이미지를 대상으로 `Trivy`를 사용하여 알려진 보안 취약점을 검사합니다.

이러한 자동화된 검증 절차는 모든 Pull Request와 코드 변경에 적용되어 프로젝트의 신뢰성을 보장합니다.

---

## 5. 사용 방법 (Deprecated)

> [!WARNING]
> 아래의 `spacectl` CLI를 이용한 방법은 예전 방식이며, 현재는 SpaceONE 콘솔을 통한 데이터 소스 설정을 권장합니다.

[spacectl CLI tools](https://github.com/cloudforet-io/spacectl)을 사용하여 플러그인을 등록하고 설정할 수 있습니다.

1.  **플러그인 조회**
2.  **데이터 소스 등록**
3.  **플러그인 옵션 설정**
4.  **데이터 동기화**

---

## 6. 문제 해결

### 주요 에러 메시지 및 해결 방안

- **`ERROR_EMPTY_FILE`**: 파일이 비어있거나 다운로드에 실패했습니다. 소스 파일의 내용과 접근 권한을 확인하십시오.
- **`ERROR_NO_DATA_ROWS`**: 파일에 헤더만 있고 데이터 행이 없습니다. 파일 내용을 확인하십시오.
- **`ERROR_CSV_PARSING`**: CSV 파일 형식이 잘못되었습니다. 구분자, 인코딩, 파일 손상 여부를 확인하십시오.

### 디버깅 팁
- 플러그인 로그에서 상세한 에러 메시지를 확인합니다.
- 파일 URL 또는 GCS 버킷에 대한 접근성을 확인합니다.
- 파일을 직접 열어 형식과 인코딩이 올바른지 검사합니다.

---

## 7. 연결 계정(Linked Accounts) 기능

### 개요
여러 클라우드 계정의 비용을 통합 분석하기 위해 데이터 소스에 연결된 계정 정보를 조회하는 기능입니다.

### 현황 및 향후 계획
- **현재**: 기능의 기본 구조와 gRPC 인터페이스가 구현되어 있습니다.
- **향후**: 각 데이터 소스(HTTP 파일, GCS)의 특성에 맞는 계정 정보 추출 로직을 구체화하고, 캐싱 및 에러 처리 기능을 고도화할 예정입니다.

