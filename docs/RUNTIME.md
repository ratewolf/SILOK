# 실행 환경과 재현 — 2026-10-15

현재 컨테이너에서 관측한 환경이다. CPU 데이터 처리·테스트와 GPU 추론 환경을 분리한다.

| 항목 | 관측 값 |
| --- | --- |
| Python | 3.11.17 |
| SQLite | 3.46.1 |
| OS | Linux / WSL2 커널, glibc 2.41 |
| GPU / 드라이버 | RTX 3080 10GB / 595.95 |
| PyTorch / CUDA build | 2.14.1+cu130 / 13.0 |
| Unsloth / Unsloth Zoo | 2026.10.5 / 2026.10.5 |
| Transformers / PEFT | 5.17.0 / 0.21.2 |
| bitsandbytes / Triton | 0.50.2 / 3.8.0 |
| lxml / pytest | 6.1.3 / 9.1.1 |

GPU 환경의 `python -m pip check`는 통과했다. xformers 0.0.35 바이너리는 현재 Torch와 맞지 않아 Unsloth가 PyTorch attention으로 대체한다. 이번 추론은 이 대체 경로를 기준으로 한다. 이 경고를 숨기려고 기존 환경의 패키지를 임의로 제거하지 않았다.

## 버전과 모델

`requirements.txt`는 확인한 CPU 의존성을 고정한다. `requirements-gpu.txt`는 CUDA 13.0 공식 wheel 인덱스와 Unsloth를 지정하며, `constraints-gpu.txt`는 현재 Linux/Python 3.11 환경의 기본 의존성 연결을 따라 수집한 88개 패키지 버전을 제약한다. extras와 다른 OS의 의존성까지 잠근 범용 lock 파일은 아니다. wheel 해시와 기본 Docker 이미지 digest도 고정하지 않았다.

[공식 PyTorch wheel 인덱스](https://download.pytorch.org/whl/cu130/torch/)에서 `2.14.1+cu130` 제공을 확인했다. 깨끗한 새 환경의 전체 설치와 GPU 이미지 빌드는 별도 확인이 필요하다.

[사용 모델](https://huggingface.co/huggingface-KREW/Llama-3.1-8B-Spider-SQL-Ko)은 LoRA 어댑터다. 이번에 확인한 revision은 다음과 같다.

- 어댑터: `11d1e533ccbe48c9135baeba83a16205ca4ca251`
- 로더가 선택한 기반 모델: `unsloth/meta-llama-3.1-8b-instruct-bnb-4bit`
- 기반 모델 캐시 revision: `f15c379fb32bb402fa06a7ae9aecb1febf4b79ec`

`MODEL_REVISION`의 기본값은 위 어댑터 hash다. `SILOK_MODEL_REVISION`으로 실험할 revision을 재정의할 수 있다. Unsloth의 어댑터 로더는 기반 모델을 별도로 해석하므로 이 설정만으로 기반 모델까지 고정되는 것은 아니다. 기반 모델 hash는 평가 보고서에도 기록하고, 완전히 고정된 배포에는 기반 모델 snapshot 지정 로더를 추가한다. 현재 모델 캐시는 Git과 이미지에 넣지 않는다.

[Transformers chat template 문서](https://huggingface.co/docs/transformers/main/en/chat_templating)에 맞춰 토큰화 결과를 명시적으로 dict로 받고 `input_ids`와 `attention_mask`를 함께 전달한다. 프롬프트 부분을 제외한 생성 토큰만 디코딩한다.

## 로컬 재현 명령

```bash
# 활성화된 Python 3.11 환경에서
python -m pip install -r requirements.txt
python -m pytest -q
python -m sillok_poc.environment
python -m sillok_poc.validate_data --db data/validation-v2.db

# Linux GPU 환경에서 추가
python -m pip install -r requirements-gpu.txt
python -m pip check
export SILOK_MODEL_REVISION=11d1e533ccbe48c9135baeba83a16205ca4ca251
python -m sillok_poc.benchmark --db data/validation-v2.db
```

검증 도구는 DB가 존재하면 덮어쓰지 않는다. DB를 다시 만들 때는 새로운 경로를 지정하고 벤치마크의 경로도 맞춘다. 상세 결과는 `reports/data-validation.json`, `reports/environment.json`, `reports/benchmark.json`, `reports/benchmark-evaluation.json`에 생성된다. 모델 접근 동의가 필요한 환경에서는 제공처의 절차를 따른다.

## 컨테이너 구성

기본 Compose는 Dockerfile의 `cpu` stage를 사용한다. `compose.gpu.yaml`을 추가하면 `gpu` stage와 GPU 전달, 모델 캐시 named volume, 어댑터 revision 설정을 사용한다. Dev Container는 이 GPU override를 포함한다. GPU가 없는 팀원은 기본 Compose를 사용한다.

```bash
docker compose build
docker compose run --rm poc python -m pytest -q
docker compose -f compose.yaml -f compose.gpu.yaml config
docker compose -f compose.yaml -f compose.gpu.yaml build
docker compose -f compose.yaml -f compose.gpu.yaml run --rm poc python -m sillok_poc.benchmark --db data/validation-v2.db
```

현재 컨테이너에 Docker CLI가 없어 이미지 빌드·실행은 검증하지 못했다. YAML 파싱과 Dev Container 참조 파일 경로는 확인했다. 호스트의 NVIDIA 드라이버와 컨테이너 GPU 지원도 필요하다. 실제 측정은 기존 컨테이너의 가상환경에서 실행한 것으로, 새 이미지의 검증 결과와 구분한다.

## GPU 측정 결과

`data/validation-v2.db` 300건, 3개 왕대·연도에서 어댑터 revision을 지정해 2026-10-15 실행했다. 보고서의 기반 모델 config hash도 위 캐시 revision과 일치했다. 4비트 로딩, 문맥 길이 2048, 최대 생성 180토큰, 단일 요청 기준이다.

| 항목 | 측정 |
| --- | ---: |
| 모델 초기화 (import·캐시 접근 포함, 가중치 캐시 존재) | 176.06초 |
| 초기화 후 첫 공통 서비스 질문 | 7.96초 |
| 10문항 SQL 실행 성공 | 10/10 |
| 10문항 결과 일치 | 9/10 |
| 평가 생성 시간 중앙값 | 1.64초 |
| 평가 생성 시간 평균 | 1.93초 |
| 평가 생성 시간 범위 | 0.71~6.51초 |
| 로딩 최대 PyTorch allocated | 5814.92MiB |
| 추론 최대 PyTorch allocated | 6042.00MiB |
| 추론 최대 PyTorch reserved | 6064.00MiB |

첫 질문은 `SELECT count(*) FROM records`를 생성해 `[[300]]`을 반환했고, 공통 서비스의 `status=ok`를 확인했다. VRAM 수치는 해당 프로세스의 PyTorch allocator 기준이며 CUDA context·다른 프로세스를 포함한 GPU 전체 사용량과 다르다. 지연은 단일 실행 관측값이며 장시간·동시 요청 부하 시험은 아니다.

오답은 최다 기사 왕대·기사 수 집계 질문이다. 정답은 `[['세종', 100]]`였지만 모델이 `records`를 왕대·연도로 자기 조인해 `[['세종', 10000]]`을 반환했다. 왕대별 100건이 100×100건으로 중복 집계되었고, 동률 정렬 조건도 생성하지 않았다. 이는 실행 가능한 SQL도 잘못된 분석을 반환할 수 있음을 보여 준다. AI 파트의 평가셋과 프롬프트 개선 사례로 남긴다.

10문항 중 왕대·연도 조건은 아직 단순하고 왕대별 표본 수가 같다. 이 9/10을 전체 실록의 정확도로 해석하지 않는다. 질문 일부를 명확히 고치고 DB·비교기를 바꿨으므로 예전 `reports/evaluation.json`의 9/10과 직접 비교하지 않는다.

## CPU 독립 환경 검증

새 임시 가상환경에 `requirements.txt`만 설치한 뒤 GPU 패키지 없이 테스트 20개와 `pip check`가 통과했다. 데이터·DB·서비스 계약 테스트는 모델 다운로드 없이 재현된다. 모델 추론은 별도의 GPU 벤치마크로 검증했다.
