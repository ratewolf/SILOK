# 공통 인터페이스 v1

## 데이터 계약

`records` 스키마는 이번 단계에서 유지한다. XML의 `level5/front/biblioData[type=T]`만 일반 기사로 적재하며 서문·총서·부록의 `level3` 기사는 별도 작업 전까지 제외한다.

| 필드 | 의미 |
| --- | --- |
| article_id | 원본 XML ID, 기본키. 웹의 국역 ID와 같다고 가정하지 않는다. |
| reign | XML 재위연도에서 추출한 왕대 이름 |
| year | XML `type=서기`의 연도 정수. 재위 연도가 아니다. |
| date_raw | XML 날짜 문자열 보존. 윤달 표기를 제거하거나 현대 양력으로 변환하지 않는다. |
| title_ko | 한국어 기사 제목 |
| original_text | 한문 본문과 XML 내부 주석 등을 공백 정규화한 문자열. 한국어 번역문이 아니다. |
| categories | XML 분류를 `; `로 연결한 문자열. 현행 웹의 분류와 차이가 날 수 있다. |

적재는 기존과 같이 ID 충돌 시 교체한다. 이 정책과 본문·주석 분리는 데이터 파트에서 후속 검토한다. 출처 링크 자동 생성과 스키마 확장은 관련 파트가 합의 후 변경한다.

## 질문 서비스

웹은 `sillok_poc.service.QuestionService` 인스턴스를 프로세스당 하나 만들고 `ask(question)`를 호출한다. 기본 DB 경로를 숨겨서 결정하지 않으며 생성자에 전달한다.

```python
from sillok_poc.service import QuestionService

service = QuestionService("data/validation-v2.db")
answer = service.ask("왕대별 기사 수를 알려줘.")
payload = answer.to_dict()
```

생성자와 모듈 import는 모델을 로드하지 않는다. 첫 유효 요청에서 모델을 로드하고 이후 재사용한다. 요청은 인스턴스 내부 Lock으로 직렬 처리한다. 여러 프로세스를 띄우면 모델이 중복 로드되므로 현재 기준은 단일 프로세스·단일 인스턴스다. Gradio 연결 시에도 이 인스턴스를 재사용한다.

| 반환 필드 | 의미 |
| --- | --- |
| question | 전달받은 질문 |
| status | `ok` 또는 `error` |
| sql | 생성 SQL. 생성 전 실패는 `null` |
| columns | 결과 열 이름 순서 |
| rows | 열 순서에 대응하는 행 배열. 중복 열 이름도 값 손실 없이 보존 |
| truncated | 표시 한도보다 결과가 더 존재하는지 여부 |
| model_time_sec | 모델 생성 단계 시간. 첫 요청은 로딩 시간 포함 |
| sql_time_sec | 성공한 SQL 실행·결과 수집 시간. 실행 전 또는 오류 시 0 |
| error_code / error_message | 성공은 둘 다 `null`. 실패는 아래 코드와 사용자용 메시지 |

빈 결과는 `status=ok, rows=[]`이며 `columns`를 유지한다. 기본 표시 한도는 20행이고 페이지 기능은 아직 없다. SQL 실행 중 실패하면 부분 결과를 반환하지 않는다. 질문은 공백 제외 1자 이상, 원래 문자열 길이 1000자 이하로 제한한다.

오류 코드는 `invalid_question`, `database_missing`, `model_error`, `sql_rejected`, `query_timeout`, `query_error`다. 모델/SQLite의 내부 예외 문자열을 UI에 직접 표시하지 않는다. 인스턴스 설정 오류는 개발자가 수정할 문제이며 사용자 오류 코드로 보장하지 않는다.

## SQL 실행

`database.execute_query(db_path, sql, max_rows=20, timeout_sec=2.0)`는 `QueryResult(columns, rows, truncated, sql_time_sec)`를 반환한다. 기존 `execute_readonly`는 CLI 호환용 dict 행 반환 함수로 남긴다. 신규 UI·평가는 `execute_query`를 사용한다.

현재 SQL 지원 범위는 SELECT 시작 단일 문장, `records` 테이블, 허용 함수 목록이다. SQLite 읽기 전용 URI·authorizer·progress handler를 함께 사용한다. WITH로 시작하는 CTE와 문자열 내부 세미콜론도 현재 제한에 걸린다. 실행 시간 제한은 SQLite VM 명령 단위 확인으로 적용되며 정밀한 벽시계 중단 보장은 아니다.

평가는 최대 10,000행까지 비교하되 잘린 결과는 정답으로 처리하지 않는다. 정답 SQL에 ORDER BY가 있는 문항은 순서도 비교한다. 열 별칭은 무시하지만 열 순서와 값은 비교한다. 단일 표본에서 결과가 같아도 의미적으로 올바른 SQL임을 증명하지는 않는다.
