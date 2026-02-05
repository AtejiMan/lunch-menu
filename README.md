# 🍱 점심 메뉴 자동 알림 시스템 (GitHub Actions + Telegram)

매일 자동으로 세 곳의 식당 메뉴를 확인하고 텔레그램으로 알림을 보내주는 시스템입니다.

## 📋 지원하는 식당

- **왕의밥상** - https://pf.kakao.com/_kSxlln/posts
- **착한한식뷔페** - https://pf.kakao.com/_xgPnnn/posts
- **원테이블** - https://pf.kakao.com/_gVFMn

## ✨ 주요 기능

- ✅ 매일 오전 11:00 자동 실행
- ✅ 이미지에서 메뉴 텍스트 추출 (OCR)
- ✅ 날짜 자동 검증 (오늘 날짜만 알림)
- ✅ **스마트 재시도**: 메뉴 미업로드 시 15분마다 자동 재확인 (최대 6번)
- ✅ 이메일 알림 (HTML 형식, 이미지 포함)
- ✅ 완전 무료 (GitHub Actions 무료 티어)

## 🚀 설치 및 설정

### 1. 텔레그램 봇 생성

1. 텔레그램에서 [@BotFather](https://t.me/botfather) 검색
2. `/newbot` 명령어 입력
3. 봇 이름 설정 (예: 점심메뉴알리미)
4. 봇 유저네임 설정 (예: lunch_menu_bot)
5. **Bot Token** 복사 (예: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Chat ID 얻기

1. 생성한 봇과 대화 시작 (아무 메시지나 보내기)
2. 브라우저에서 `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` 접속
   - `<BOT_TOKEN>`을 실제 토큰으로 교체
3. `"chat":{"id":123456789}` 에서 숫자 부분이 **Chat ID**

또는 [@userinfobot](https://t.me/userinfobot)에게 메시지를 보내면 Chat ID를 알려줍니다.

### 3. GitHub 저장소 설정

1. 이 저장소를 Fork 또는 새로 생성
2. Settings → Secrets and variables → Actions
3. 다음 Secrets 추가:
   - `TELEGRAM_BOT_TOKEN`: 위에서 받은 Bot Token
   - `TELEGRAM_CHAT_ID`: 위에서 받은 Chat ID

### 4. 배포

코드를 GitHub에 Push하면 자동으로 설정 완료!

```bash
git add .
git commit -m "점심 메뉴 알림 시스템 초기 설정"
git push origin main
```

## 📅 실행 시간 변경

매일 오전 10:30이 기본값입니다. 변경하려면:

`.github/workflows/lunch_menu.yml` 파일의 cron 표현식 수정:

```yaml
schedule:
  - cron: '30 1 * * *'  # 한국시간 10:30
```

참고:
- 한국시간 = UTC + 9시간
- 오전 11:00 → `0 2 * * *`
- 오전 11:30 → `30 2 * * *`
- 정오 12:00 → `0 3 * * *`

## 🧪 수동 실행

GitHub Actions 탭에서 "Run workflow" 버튼으로 즉시 실행 가능합니다.

## 📁 파일 구조

```
lunch-menu-notification/
├── .github/
│   └── workflows/
│       └── lunch_menu.yml      # GitHub Actions 설정
├── lunch_menu.py                # 메인 스크립트
├── requirements.txt             # Python 패키지
└── README.md                    # 이 파일
```

## 🔧 로컬 테스트

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt

# 환경 변수 설정
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# 실행
python lunch_menu.py
```

## 📊 알림 형식

```
🍱 2026년 02월 05일 점심 메뉴

🍽️ 왕의밥상
📅 2026-02-05

[메뉴 이미지]
메뉴 텍스트...

---

⚠️ 아직 업데이트되지 않은 메뉴:
  • 원테이블 (마지막 업데이트: 2026-02-04)
```

## ⚙️ 커스터마이징

### 식당 추가/제거

`lunch_menu.py`의 `restaurants` 리스트 수정:

```python
restaurants = [
    Restaurant(
        name="새로운 식당",
        url="https://pf.kakao.com/_xxxxx/posts",
        channel_id="_xxxxx",
        date_in_post=True  # False면 이미지에서만 날짜 확인
    ),
]
```

### 날짜 형식 추가

`parse_date()` 함수에 새로운 패턴 추가:

```python
patterns = [
    (r'새로운패턴(\d+)', lambda m: datetime(...)),
    # ...
]
```

## 🐛 트러블슈팅

### 알림이 안 와요
1. GitHub Actions 탭에서 실행 로그 확인
2. Secrets 설정 재확인
3. 텔레그램 봇과 대화가 시작되었는지 확인

### OCR 정확도가 낮아요
- 이미지 품질이 낮은 경우 발생
- `preprocess_image()` 함수에서 전처리 로직 강화
- 또는 유료 OCR API (Google Vision, Naver Clova) 사용 고려

### 날짜 인식이 안 돼요
- `parse_date()` 함수에 해당 형식의 정규표현식 추가
- 로그에서 실제 OCR 결과 확인

## 💰 비용

- **GitHub Actions**: 월 2000분 무료 (이 프로젝트는 1일 약 2-3분 사용)
- **EasyOCR**: 무료
- **Telegram Bot**: 무료

**총 비용: $0/월** 🎉

## 📝 라이선스

MIT License

## 🤝 기여

Issues와 Pull Requests는 언제나 환영입니다!

## 📧 문의

텔레그램 봇이 동작하지 않는 경우:
1. GitHub Issues에 등록
2. 실행 로그 첨부
