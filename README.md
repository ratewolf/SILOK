# SILOK — 조선왕조실록 자연어 검색·분석 서비스

조선왕조실록의 역사 데이터를 SQLite 데이터베이스로 구축하고, Hugging Face의 Text-to-SQL 모델을 활용해 비전문가도 한국어 자연어 질문만으로 조선시대의 기록을 조건 검색하고 분석할 수 있는 교육용 웹 서비스를 구현한다.

PoC는 최종 목표에 이르는 첫 검증 단계다. 현재 저장소에는 XML 적재, 읽기 전용 SQL 조회, 모델 추론 및 평가를 위한 CLI가 있으며, Gradio 웹 GUI는 후속 구현 대상이다.

## 기술과 개발 환경

| 구분 | 선택 |
| --- | --- |
| 개발 언어 | Python (현재 Docker 이미지: 3.11) |
| 데이터베이스 | SQLite |
| AI | Hugging Face `huggingface-KREW/Llama-3.1-8B-Spider-SQL-Ko` |
| 웹 GUI | Gradio (구현 예정) |
| 협업 | Git · GitHub, 4인 |
| 실행 환경 | Docker Container, VS Code Dev Containers |
| 기준 하드웨어 | Intel Xeon W-2223 · NVIDIA RTX 3080 10GB · RAM 32GB |

현재 모델 코드는 Hugging Face 모델을 다운로드하여 로컬 GPU에서 추론하는 방식이다. 호스팅된 추론 API를 호출하는 구조는 아니다. GPU 추론 의존성은 `requirements-gpu.txt`와 선택형 Docker `gpu` stage로 분리한다. 기본 이미지는 데이터 처리용이다.

## 프로젝트 구조

```text
.devcontainer/       VS Code 개발 컨테이너 설정 (GPU 요청)
Dockerfile           CPU 기본 stage와 선택형 GPU stage
compose.yaml         CPU CLI 실행 및 로컬 데이터 마운트
compose.gpu.yaml     GPU·모델 캐시 override
requirements.txt     데이터 처리·테스트 의존성
requirements-gpu.txt GPU 추론 의존성 (constraints-gpu.txt로 버전 제약)
sillok_poc/          현재 CLI 패키지 (기존 실행 명령 유지)
  __main__.py        inspect / import / query / ask / evaluate
  xml_loader.py      XML 기사 추출
  database.py        스키마·적재·읽기 전용 조회
  model.py           Text-to-SQL 추론
  evaluate.py        기본 10문항 평가
  service.py         공통 질문→SQL→결과 인터페이스
  validate_data.py   대표 실제 XML 검사 및 별도 검증 DB 생성
  environment.py     실행 환경 기록
  benchmark.py       단일 모델 재사용·평가·VRAM 측정
tests/              단위 테스트 및 가상 XML fixture
data/raw/           실제 원본 XML (Git 제외)
reports/            로컬 평가 결과 (Git 제외)
docs/               구현 계획 및 협업 규칙
```

구현 단계는 [개발 계획](docs/DEVELOPMENT.md), 분업할 작업은 [작업 목록](docs/TASKS.md), 파트 간 연결 규칙은 [공통 인터페이스](docs/INTERFACES.md)를 참고한다. 실제 데이터 검사 결과와 원문 대조 근거는 [데이터 검증](docs/DATA_VALIDATION.md)에 기록한다. GPU 환경·평가 결과와 실행 한계는 [실행 환경](docs/RUNTIME.md)을 참고한다.

## 현재 단계: PoC 실행

검증 흐름: 공식 실록 XML → SQLite → 원문·수동 SELECT 확인 → 모델 추론 → 10질문 평가. 현재는 대표 XML 검사와 3개 왕대 300건 검증 DB에서 GPU 평가까지 확인했으며, 결과 일치는 9/10이다. 전체 데이터 검증과 Gradio 구현은 후속 단계다.

> **중요**: 동봉된 `tests/fixtures/synthetic.xml`은 파서 단위테스트용 *가상 데이터*입니다.
> 실제 역사 사료가 아니며, 진짜 PoC 결과나 시연 데이터로 사용하면 안 됩니다.

## 1. 준비 (Python 3.11 추천)

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

## 2. 실제 XML 다운로드와 구조 확인

1. 공식 데이터: https://www.data.go.kr/data/15053647/fileData.do
2. 다운로드 및 압축 해제 → XML 파일들을 `data/raw/`에 저장.
3. 아래 커맨드로 기사 샘플의 제목·날짜·왕대·분류를 확인합니다.

```bash
python -m sillok_poc inspect data/raw
```

**주의:** XML 파서가 대응하는 것은 일반 재위년 기록의 `level5/front/biblioData` 구조입니다.
실제 파일에서 기사가 0건으로 나오거나 DTD 엔티티 파싱 오류가 발생하면 그 파일의 XML 태그와 DTD를 확인하고 로더를 수정하세요.
DTD 참조를 이유로 외부 네트워크 엔티티를 무조건 허용하지 마세요.

## 3. DB 적재 및 수동 SQL

```bash
python -m sillok_poc import data/raw --limit 100
python -m sillok_poc query "SELECT COUNT(*) AS cnt FROM records"
python -m sillok_poc query "SELECT reign,year,title_ko FROM records ORDER BY article_id LIMIT 5"
```

**검증**: 기사 100건/고유 기사 ID/제목이 올바른지 공식 원문과 5건 이상 대조하세요.
서기 `date_raw`의 `L0`, `L1` 등을 절대로 현대 양력으로 임의 변환하지 않습니다.
실록 웹 링크는 ID 대응 검증 전까지 생성하지 않습니다.

## 4. HF 모델 (GPU가 있는 단일 머신에서 별도 환경 권장)

사용 모델: https://huggingface.co/huggingface-KREW/Llama-3.1-8B-Spider-SQL-Ko

이 모델 저장소는 LoRA 어댑터 형태로 제공되므로 기반 Llama 3.1 8B 가중치 접근·저장공간·GPU 환경이 필요합니다.
모델 카드의 Unsloth 4비트 로더를 사용하며, 기반 모델 라이선스 및 허깅페이스 로그인 동의를 확인하세요.

```bash
# Linux/Python 3.11 GPU 가상환경 (CUDA 13.0 wheel 기준)
python -m pip install -r requirements-gpu.txt
python -m pip check
python -m sillok_poc.environment

# 기존 DB를 보존하며 태조·정종·세종 각 100건의 검증 DB 생성
python -m sillok_poc.validate_data --db data/validation-v2.db
export SILOK_MODEL_REVISION=11d1e533ccbe48c9135baeba83a16205ca4ca251
python -m sillok_poc ask "전체 기사는 몇 건이야?" --db data/validation-v2.db
python -m sillok_poc.benchmark --db data/validation-v2.db
```

검증 DB가 이미 있으면 재생성 도구는 종료합니다. 새 경로를 지정하고 후속 명령의 `--db`도 맞추세요. 모델 로딩·평가는 GPU 환경에서 실행하며, GPU가 없어도 1~3단계와 데이터 검증 도구·단위 테스트는 실행할 수 있습니다. `ask`는 공통 결과 형식의 JSON을 출력하고 실패 시 종료 코드 1을 반환합니다.

## 5. Docker와 Dev Container

```bash
docker compose build
docker compose run --rm poc python -m pytest -q
docker compose run --rm poc python -m sillok_poc inspect data/raw
docker compose run --rm poc python -m sillok_poc import data/raw --limit 100
docker compose run --rm poc python -m sillok_poc query "SELECT COUNT(*) AS cnt FROM records"
```

Compose의 `poc` 서비스 이름은 기존 명령과의 호환성을 위해 유지합니다. 평가 보고서는 `./reports`에 보존됩니다.

VS Code에서 **Dev Containers: Reopen in Container**를 실행하면 저장소가 `/workspaces/SILOK`에 마운트됩니다. Dev Container는 GPU를 요청하므로 호스트에 NVIDIA 드라이버와 컨테이너 GPU 지원이 필요합니다. GPU가 없는 팀원은 위의 기본 Compose 명령으로 데이터 계층을 검증할 수 있습니다.

GPU용 Compose는 별도 override를 명시합니다. 모델 파일은 named volume에 캐시되며 이미지에 포함하지 않습니다.

```bash
docker compose -f compose.yaml -f compose.gpu.yaml build
docker compose -f compose.yaml -f compose.gpu.yaml run --rm poc python -m sillok_poc.benchmark --db data/validation-v2.db
```

Dev Container는 GPU override를 사용합니다. 기본 Compose는 GPU 없이 실행합니다. Gradio 의존성과 포트 공개는 GUI 구현 단계에서 추가합니다. 현재 컨테이너에는 Docker CLI가 없어 위 이미지 빌드를 실제 검증하지 못했습니다. 호스트에서 빌드·실행 확인이 필요합니다.

## 평가 방법

- `python -m sillok_poc evaluate`는 현재 DB의 왕대/연도를 이용하여 10개 기본 질문을 구성합니다.
- `reports/evaluation.json`의 질문·정답 SQL·생성 SQL·실행 성공·정답 여부를 리뷰하세요.
- 최대 10,000행까지 비교하고 잘린 결과는 정답으로 인정하지 않습니다. 정답 SQL에 정렬이 지정된 문항은 순서도 비교합니다. 결과 일치는 SQL 의미의 정확성을 보장하지 않으므로 사람이 최종 검토하세요.
- 지금 목표는 '10/10 달성'이 아니라 실행 가능성·오류 유형을 확인하는 것입니다.
- 제목과 분류에 기반한 검색은 한문 본문에 대한 의미 검색과 다릅니다.

## 라이선스·출처

조선왕조실록 원문 데이터 제공기관: 국사편찬위원회 (공공데이터포털).
https://www.data.go.kr/data/15053647/fileData.do
실제 사료 XML, 생성 DB 및 모델 가중치는 Git에 포함하지 않습니다. 원문 이용 조건과 출처 표시 방식은 데이터 배포 전에 확인합니다.
