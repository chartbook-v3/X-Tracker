# X-Tracker

글로벌 빅테크·AI·반도체·매크로 주요 인사 44인의 X(트위터) 실시간 게시글을 24시간 감시해 텔레그램 채널(`@chartbooknews`)로 전송하는 전용 봇입니다.

## 주요 기능
- 고빈도 핵심 인물(일론 머스크 등) 단독 쿼리 + 나머지 2~3인 소그룹 20개 분할 수집 (`when:2h` 정상 작동)
- 핵심 기술·시장 발언을 포함한 45자 이상 `@` 답글 선택 허용, 빈 리포스트 및 잡담 차단
- X Snowflake Status ID 기반 정확한 UTC 발행시각 및 작성자 핸들 1:1 실증 검증
- Gemini Flash 금융 특화 한국어 번역 + 무료 Google Translate 자동 폴백
- GitHub Actions 24시간 Zero-Lag 릴레이 실행
