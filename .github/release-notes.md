## 다운로드 — 사용하는 컴퓨터에 맞는 파일 하나만 받으세요

| 운영체제 | 파일 | 지원 |
| --- | --- | --- |
| 🪟 **Windows** | `AptitudeCompanion-Windows.exe` | Windows 10/11 (64비트) |
| 🍎 **macOS (맥북)** | `AptitudeCompanion-macOS.zip` | macOS 11 Big Sur 이상, Apple Silicon(M1~) · Intel 모두 지원 |

Python 설치 없이 바로 실행됩니다. 두 버전의 기능과 TXT 답안 양식은 같습니다.

### Windows
1. `AptitudeCompanion-Windows.exe`를 내려받아 더블 클릭합니다.
2. "Windows의 PC 보호" 창이 뜨면 **추가 정보 → 실행**을 누릅니다(코드 서명이 없는 앱이라 처음 한 번 표시됩니다).

### macOS (맥북)
1. `AptitudeCompanion-macOS.zip`을 내려받으면 `AptitudeCompanion.app`이 생깁니다. **응용 프로그램(Applications)** 폴더로 옮깁니다.
2. 앱을 더블 클릭합니다. Apple 개발자 서명이 없는 앱이라 처음에는 "확인할 수 없음" 경고가 뜹니다.
   - macOS 15 Sequoia 이상: **완료**를 누른 뒤 **시스템 설정 → 개인정보 보호 및 보안** 아래쪽의 **그래도 열기**를 누르고 암호를 입력합니다.
   - macOS 14 이하: 앱을 **Control+클릭(우클릭) → 열기 → 열기**를 누릅니다.
   - 그래도 열리지 않으면 터미널에서 `xattr -dr com.apple.quarantine /Applications/AptitudeCompanion.app` 실행 후 다시 엽니다.
3. 이후에는 일반 앱처럼 바로 열립니다. `Cmd+Q`로 종료해도 입력 내용이 임시 저장됩니다.

### 데이터 저장 위치
- Windows: `%LOCALAPPDATA%\AptitudeCompanion`
- macOS: `~/Library/Application Support/AptitudeCompanion`

답안 TXT는 처음 `답안 저장` 때 선택한 폴더에 저장됩니다. 앱은 답안이나 사진을 네트워크로 전송하지 않습니다.
