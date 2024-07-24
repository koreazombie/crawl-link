```markdown
# 웹 크롤러 (WebCrawler)

비동기 방식의 파이썬 웹 크롤러로, 지정된 깊이까지 웹 페이지를 스크랩하며, 요청 속도를 제한하여 서버 과부하를 방지합니다. 크롤러는 각 방문한 페이지의 제목, 대표 이미지, 링크를 수집합니다.

## 기능

- 고성능 비동기 방식 `aiohttp` 사용
- 과도한 재귀를 방지하기 위한 깊이 제한 크롤링
- 서버 과부하 방지를 위한 요청 속도 제한
- 페이지 제목과 대표 이미지 추출
- 크롤링 진행 상황 및 오류 로그 기록
- 결과를 JSON 파일로 출력

## 요구 사항

- Python 3.7+
- `aiohttp`
- `beautifulsoup4`
- `charset_normalizer`

필요한 패키지는 pip으로 설치할 수 있습니다:

```sh
pip install aiohttp beautifulsoup4 charset_normalizer
```

## 사용 방법

크롤러를 원하는 호스트 URL, 최대 크롤 깊이, 요청 속도로 실행합니다. 결과는 타임스탬프가 포함된 JSON 파일로 저장됩니다.

### 명령줄 인수

- `host`: 크롤링할 호스트 URL (필수)
- `--depth`: 최대 크롤 깊이 (기본값: 3)
- `--rate`: 요청 속도 제한 (초당 요청 수, 기본값: 5)

### 예시

```sh
python webcrawler.py https://example.com --depth 3 --rate 5
```

### 출력

크롤러는 `host_date_time.json` 형식의 JSON 파일에 결과를 저장합니다. 여기서 `host`는 호스트 URL을 정리한 값이고, `date_time`은 현재 타임스탬프입니다.

### 샘플 출력

```json
[
    {
        "host": "https://example.com",
        "date": "2024-07-24",
        "time": "14:22:15"
    },
    {
        "url": "https://example.com",
        "title": "Example Domain",
        "image": "https://example.com/image.png"
    },
    ...
]
```

## 코드 개요

### `WebCrawler` 클래스

- **`__init__(self, host, depth_limit, rate_limit=5)`**: 호스트, 깊이 제한, 속도 제한으로 크롤러를 초기화합니다.
- **`fetch(self, session, url)`**: URL의 내용을 비동기적으로 가져옵니다.
- **`get_representative_image(self, soup)`**: BeautifulSoup 객체에서 대표 이미지를 추출합니다.
- **`parse(self, session, url, depth)`**: URL을 파싱하고, 링크를 추출하며, 추가 크롤링을 예약합니다.
- **`is_valid_link(self, link)`**: 링크가 유효하고 동일한 호스트에 속하는지 확인합니다.
- **`crawl(self)`**: 비동기 크롤링 프로세스를 관리합니다.
- **`run(self)`**: 크롤러를 실행하고 결과를 JSON 파일로 저장합니다.

```