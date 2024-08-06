import asyncio
import aiohttp
from aiohttp import ClientSession, TCPConnector
from bs4 import BeautifulSoup
import json
import time
from urllib.parse import urljoin, urlparse
from charset_normalizer import from_bytes
from datetime import datetime
import logging
import argparse

class WebCrawler:
    def __init__(self, host, depth_limit, rate_limit=5):
        self.host = host
        self.depth_limit = depth_limit
        self.rate_limit = rate_limit
        self.visited_urls = set()
        self.result = []
        self.semaphore = asyncio.Semaphore(rate_limit)  # 비동기 작업 제한
        logging.basicConfig(level=logging.DEBUG)

    async def fetch(self, session: ClientSession, url: str) -> str:
        # URL의 HTML 콘텐츠를 가져오는 함수
        async with self.semaphore:
            for _ in range(3):  # 최대 3번 시도
                try:
                    async with session.get(url) as response:
                        raw_content = await response.read()
                        result = from_bytes(raw_content).best()
                        logging.debug(f"Fetched HTML content from {url}")
                        return str(result)
                except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError) as e:
                    logging.warning(f'Error: {e}, retrying...')
                    await asyncio.sleep(2)  # 2초 후 재시도
                except Exception as e:
                    logging.error(f'Decode error: {e}, skipping...')
                    return ""
            return ""

    def get_representative_image(self, soup):
        # 페이지의 대표 이미지를 가져오는 함수
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            return og_image["content"]
        
        icon_link = soup.find("link", rel="icon")
        if icon_link and icon_link.get("href"):
            return urljoin(self.host, icon_link["href"])
        
        img_tag = soup.find("img")
        if img_tag and img_tag.get("src"):
            return urljoin(self.host, img_tag["src"])
        
        return None

    async def parse(self, session: ClientSession, url: str, depth: int):
        # HTML 콘텐츠를 파싱하고 유용한 정보를 추출하는 함수
        if depth > self.depth_limit or url in self.visited_urls:
            logging.debug(f"Skipping URL: {url}, Depth: {depth}, Already Visited: {url in self.visited_urls}")
            return
        
        self.visited_urls.add(url)
        html = await self.fetch(session, url)
        if not html:
            logging.debug(f"Empty HTML content for URL: {url}")
            return
        
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.title.string if soup.title else 'No Title'
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

    async def crawl(self):
        # 크롤링 프로세스를 시작하는 함수
        connector = TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
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