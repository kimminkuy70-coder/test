# 인적성 시험 도우미

Windows와 macOS(맥북)에서 문제 창 옆에 놓고 쓰는 오프라인 시험 보조 프로그램입니다. API, 로그인, 별도 사용료가 없습니다.

## 다운로드 (권장)

저장소의 **Releases**에서 운영체제에 맞는 파일 하나를 받습니다. Python 설치가 필요 없습니다.

| 운영체제 | 파일 | 실행 |
| --- | --- | --- |
| Windows 10/11 (64비트) | `AptitudeCompanion-Windows.exe` | 더블 클릭. "Windows의 PC 보호"가 뜨면 **추가 정보 → 실행** |
| macOS 11 이상 (Apple Silicon·Intel 공용) | `AptitudeCompanion-macOS.zip` | 압축을 풀어 `AptitudeCompanion.app`을 응용 프로그램 폴더로 옮긴 뒤 실행 |

macOS 앱은 Apple 개발자 서명이 없어 처음 한 번 경고가 뜹니다. macOS 15 이상은 **시스템 설정 → 개인정보 보호 및 보안 → 그래도 열기**, macOS 14 이하는 앱을 **Control+클릭 → 열기**로 엽니다. 그래도 열리지 않으면 터미널에서 `xattr -dr com.apple.quarantine /Applications/AptitudeCompanion.app`을 실행합니다.

## 소스에서 실행

1. 저장소의 **Code → Download ZIP**으로 내려받아 압축을 풉니다.
2. Python 3.10 이상(python.org 공식 설치본, Tcl/Tk 포함)을 설치합니다. macOS 기본 `/usr/bin/python3`는 버전이 낮아 사용할 수 없습니다.
3. Windows는 `start.bat`, macOS는 `start.command`를 더블 클릭합니다. 또는 `python app.py`(macOS: `python3 app.py`)를 실행합니다.

외부 Python 패키지는 필요하지 않습니다. 실행 파일은 GitHub Actions의 **Build apps** 워크플로가 만들며, Actions 실행 화면 아래 Artifacts의 `AptitudeCompanion-Windows.exe`/`AptitudeCompanion-macOS.zip`에서도 받을 수 있습니다(추가 압축 없이 그대로 받아집니다).

## 사용

- 왼쪽 문제 창은 직접 엽니다. 이 프로그램을 화면 오른쪽으로 이동하세요.
- 제목과 회차를 입력하고 과목 선택 상자로 전환합니다.
- 순서: 언어이해 → 자료해석 → 창의수리 → 언어추리 → 수열추리. 각각 20문항, 5지선다입니다.
- 각 문항 하나의 선택지, `해제`로 미응답 전환. 과목 전환 시 답안과 메모가 유지됩니다.
- 두 구분선을 드래그해 세 영역 높이를 조절합니다. 각 영역의 최소 높이를 보장하며, 답안지/계산기는 내부 스크롤, 메모는 줄바꿈과 독립 스크롤을 사용합니다.
- 기본 최소 크기는 360×540이며, 높은 글자 배율에서는 실제 버튼·글자 크기에 맞춰 최소 너비와 영역 높이가 자동으로 커집니다. 3개 영역을 동시에 사용할 수 있는 크기를 유지합니다. Windows 배율과 작업 표시줄(macOS: 메뉴 막대와 Dock) 때문에 공간이 부족하면 디스플레이 설정을 조절하세요.
- macOS에서는 트랙패드 두 손가락 스크롤로 답안지/계산기 영역을 스크롤하며, `Cmd+C/V/Z`와 `Cmd+Q` 종료를 지원합니다. `Cmd+Q`로 종료해도 입력 내용을 임시 저장합니다.
- 계산기 입력칸에서 Enter로 계산, Esc로 지우기. 사칙연산, 괄호, 소수점을 지원합니다.
- `답안 저장` 첫 사용 시 폴더를 선택합니다. 이후 위치를 기억하며 `저장 위치 변경`으로 바꿀 수 있습니다.
- `답안지 폴더 열기`로 탐색기(macOS: Finder)를 열어 TXT와 정답표 사진을 같은 ChatGPT 채팅에 첨부하세요.
- `채점 프롬프트 복사`로 첫 채팅에 지침을 붙여넣습니다. 이후 “이번 시험 채점하고 누적 기록 갱신해줘”라고 요청합니다.
- 성적 채점과 추이는 ChatGPT에서 관리합니다. 프로그램 내부 채점/API/성적 그래프/결과 가져오기는 포함하지 않습니다.

## 저장과 개인정보

- TXT는 UTF-8 BOM으로 저장해 한글 메모장에서 읽을 수 있습니다. 모든 과목, 미응답, 메모, 추후 채점란을 포함합니다.
- 같은 저장 폴더에 제목·회차가 같은 답안이 있으면 덮어쓰기 여부를 묻습니다. 예는 최근 파일 교체(기입한 채점 내용 포함), 아니요는 별도 파일 저장, 취소는 저장 중단입니다. 파일명 대신 TXT 내부의 제목·회차로 비교하며 여러 파일이 있으면 가장 최근 파일명을 알림에 표시합니다. 같은 시험 식별번호는 ChatGPT에서 중복 시험으로 집계하지 않습니다.
- 편집 후 0.45초에 임시 저장하고 정상 종료 시 즉시 저장합니다. 강제 종료 직전 입력은 잃을 수 있습니다.
- 임시 기록/설정: Windows `%LOCALAPPDATA%\AptitudeCompanion`, macOS `~/Library/Application Support/AptitudeCompanion`. 새 시험 시작 전 JSON 원본은 `archives`에 보관합니다.
- 앱은 답안이나 사진을 네트워크로 전송하지 않습니다. 사용자가 직접 ChatGPT에 첨부합니다.

## 개발 검증

`python -m unittest -v` — 100문항 내보내기, 저장/복원, 덮어쓰기 방지, 데이터 검증, 계산기 안전성, 운영체제별 저장 위치.
`python ui_check.py` — 그래픽 디스플레이가 필요하며 창 크기/분할 경계/과목 전환을 검증합니다.

`main`·`claude/**` 브랜치 push 때마다 GitHub Actions의 **Build apps** 워크플로가 Windows 러너에서 EXE(PyInstaller onefile)를, macOS 러너에서 python.org universal2 Python으로 Intel·Apple Silicon 공용 `.app`을 빌드합니다. macOS 빌드는 두 아키텍처 포함 여부, 코드 서명(ad-hoc) 무결성, 실제 실행(Apple Silicon 및 Rosetta를 통한 Intel)을 검사합니다. 실제 PC의 배율별 사용감, 탐색기/Finder 실행, macOS 보안 경고 처리는 사용자 PC에서 최종 확인이 필요합니다.

## 릴리즈

`v1.2.3` 형식 태그를 push하거나, Actions → Build apps → **Run workflow**에서 `release_tag`에 새 태그를 입력하면 두 운영체제 빌드와 검사가 모두 성공한 뒤 `AptitudeCompanion-Windows.exe`와 `AptitudeCompanion-macOS.zip`을 첨부한 릴리즈를 만듭니다. 릴리즈 설명은 `.github/release-notes.md`를 사용합니다.

## 디스플레이 회귀 검사

Windows 러너에서 1920×1080 및 2880×1800 화면 정보를 모사하고 Tk 글자 배율 100/125/150/200%를 적용해 검사합니다. 8개 조합 × 창 크기 4개 × 분할 위치 3개 = 96개 배치에서 영역 경계, 내부 버튼/글자 잘림, 끝까지 스크롤 가능 여부를 확인합니다. 과목별 입력 보존 및 재실행 복원도 검사합니다.

macOS 러너에서는 맥북 논리 해상도 1280×832, 1470×956, 1512×982, 1728×1117을 macOS 기본 글자 배율로 모사해 같은 항목을 48개 배치에서 검사합니다.

이 검사는 물리 모니터 해상도를 변경하거나 OS 디스플레이 배율을 직접 전환하는 검사가 아닙니다. 실제 다중 모니터 이동 및 OS 배율 변경은 별도 실기 확인이 필요합니다.
