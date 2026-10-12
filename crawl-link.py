import asyncio
import aiohttp
from aiohttp import ClientSession, TCPConnector
from bs4 import BeautifulSoup
import json
import random
import time
from urllib.parse import urljoin, urlparse, urlunparse
from charset_normalizer import from_bytes
from datetime import datetime
import logging
import argparse

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36'
]


def _strip_fragment(url: str) -> str:
    # 같은 페이지를 #fragment가 다르다는 이유로 중복 방문하지 않도록 정규화한다
    return urlunparse(urlparse(url)._replace(fragment=''))


class RateLimiter:
    # 세마포어(동시 실행 수 제한)가 아니라 실제 초당 요청 수를 제한하는 토큰 버킷
    def __init__(self, rate_per_second: float):
        self.rate = rate_per_second
        self._tokens = float(rate_per_second)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.rate, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self.rate)


class WebCrawler:
    def __init__(self, host, depth_limit, rate_limit=5):
        self.host = host
        self.depth_limit = depth_limit
        self.rate_limit = rate_limit
        self.visited_urls = set()
        self.result = []
        self.rate_limiter = RateLimiter(rate_limit)  # 초당 요청 수 제한

    async def fetch(self, session: ClientSession, url: str) -> str:
        # URL의 HTML 콘텐츠를 가져오는 함수
        for _ in range(3):  # 최대 3번 시도
            await self.rate_limiter.acquire()  # 매 요청 시도마다 초당 요청 수 게이트를 통과
            try:
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                async with session.get(url, headers=headers) as response:
                    if response.status >= 400:
                        logging.warning(f'HTTP {response.status} for {url}, skipping...')
                        return ""
                    raw_content = await response.read()
                    result = from_bytes(raw_content).best()
                    logging.debug(f"Fetched HTML content from {url}")
                    return str(result) if result is not None else ""
            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError) as e:
                logging.warning(f'Error: {e}, retrying...')
                await asyncio.sleep(2)  # 2초 후 재시도
            except Exception as e:
                logging.error(f'{type(e).__name__} while fetching {url}: {e}, skipping...')
                return ""
        return ""

    def get_representative_image(self, soup):
        # 페이지의 대표 이미지를 가져오는 함수
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            return og_image["content"]
        
        icon_link = soup.find("link", rel="icon", href=lambda href: href and not href.startswith("data:"))
        if icon_link and icon_link.get("href"):
            return urljoin(self.host, icon_link["href"])

        img_tag = soup.find("img", src=lambda src: src and not src.startswith("data:"))
        if img_tag and img_tag.get("src"):
            return urljoin(self.host, img_tag["src"])
        
        return None

    async def parse(self, session: ClientSession, url: str, depth: int):
        # HTML 콘텐츠를 파싱하고 유용한 정보를 추출하는 함수
        url = _strip_fragment(url)
        if depth > self.depth_limit or url in self.visited_urls:
            logging.debug(f"Skipping URL: {url}, Depth: {depth}, Already Visited: {url in self.visited_urls}")
            return

        self.visited_urls.add(url)
        html = await self.fetch(session, url)
        if not html:
            logging.debug(f"Empty HTML content for URL: {url}")
            return

        soup = BeautifulSoup(html, 'html.parser')
        title = soup.title.get_text().strip() if soup.title else ''
        title = title or 'No Title'
        image = self.get_representative_image(soup)
        self.result.append({'url': url, 'title': title, 'image': image})
        
        logging.debug(f'Parsed URL: {url}, Title: {title}')

        links = [a.get('href') for a in soup.find_all('a', href=True)]
        logging.debug(f'Found {len(links)} links on {url}')
        tasks = []
        for link in links:
            absolute_link = urljoin(url, link)
            if self.is_valid_link(absolute_link):
                logging.debug(f'Valid link found: {absolute_link}')
                tasks.append(self.parse(session, absolute_link, depth + 1))
            else:
                logging.debug(f'Invalid link skipped: {absolute_link}')

        if tasks:
            await asyncio.gather(*tasks)

    def is_valid_link(self, link: str) -> bool:
        # 링크가 유효하고 동일한 호스트에 속하는지 확인하는 함수
        parsed_host = urlparse(self.host).netloc
        parsed_link = urlparse(link).netloc
        return parsed_host == parsed_link

    def _build_connector(self) -> TCPConnector:
        # 인증서 검증을 켠 기본 커넥터. 교체가 필요하면 이 메서드만 바꾸면 된다.
        return TCPConnector()

    async def crawl(self):
        # 크롤링 프로세스를 시작하는 함수
        async with aiohttp.ClientSession(connector=self._build_connector()) as session:
            await self.parse(session, self.host, 1)

    def run(self):
        # 크롤러를 실행하는 함수
        start_time = time.time()
        
        # 호스트, 날짜 및 시간 정보를 포함한 사전 생성
        date_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.result.append({
            'host': self.host,
            'date': date_time_str.split(' ')[0],
            'time': date_time_str.split(' ')[1]
        })

        asyncio.run(self.crawl())
        end_time = time.time()
        logging.info(f'Crawled {len(self.visited_urls)} pages in {end_time - start_time} seconds.')
        
        # 호스트 이름과 현재 날짜 및 시간을 사용하여 파일 이름 생성
        host_name = urlparse(self.host).netloc.replace('.', '_')
        file_date_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{host_name}_{file_date_time_str}.json"
        
        # 결과를 JSON 파일로 저장
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.result, f, ensure_ascii=False, indent=4)
        logging.info(json.dumps(self.result, ensure_ascii=False, indent=4))

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description='Web Crawler')
    parser.add_argument('host', type=str, help='The host URL to crawl')
    parser.add_argument('--depth', type=int, default=3, help='Maximum crawl depth (default: 3)')
    parser.add_argument('--rate', type=int, default=5, help='Rate limit (requests per second, default: 5)')

    args = parser.parse_args()
    host = args.host
    depth_limit = args.depth
    rate_limit = args.rate

    logging.debug(f"Starting crawl with host: {host}, depth_limit: {depth_limit}, rate_limit: {rate_limit}")
    
    crawler = WebCrawler(host, depth_limit, rate_limit)
    crawler.run()
