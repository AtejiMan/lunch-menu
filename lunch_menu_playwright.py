#!/usr/bin/env python3
"""
점심 메뉴 자동 알림 시스템 - Playwright 버전
React SPA를 위해 실제 브라우저로 JavaScript 실행
"""

import os
import re
from datetime import datetime
from html import unescape
from urllib.parse import unquote, parse_qs, urlparse
from PIL import Image
from io import BytesIO
import logging
import time

# Playwright import
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Restaurant:
    """식당 정보 클래스"""
    def __init__(self, name, url, channel_id, date_in_post=True):
        self.name = name
        self.url = url
        self.channel_id = channel_id
        self.date_in_post = date_in_post


class MenuScraper:
    """메뉴 스크래핑 클래스 - Playwright 사용"""
    
    def __init__(self):
        self.reader = None  # EasyOCR reader는 필요할 때 초기화
        
    def init_ocr(self):
        """OCR 리더 초기화 (지연 로딩)"""
        if self.reader is None:
            logger.info("OCR 엔진 초기화 중...")
            import easyocr
            self.reader = easyocr.Reader(['ko', 'en'], gpu=False)
            logger.info("OCR 엔진 초기화 완료")
    
    def fetch_page_with_playwright(self, url):
        """Playwright로 웹페이지 가져오기 (JavaScript 실행)"""
        try:
            with sync_playwright() as p:
                # 브라우저 실행 (headless mode)
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = context.new_page()
                
                # 페이지 로드
                logger.info(f"페이지 로딩 중: {url}")
                page.goto(url, wait_until='networkidle', timeout=30000)
                
                # 콘텐츠가 로드될 때까지 대기
                try:
                    # 게시글 또는 프로필 이미지가 나타날 때까지 대기
                    page.wait_for_selector('.wrap_fit_thumb, .img_thumb', timeout=10000)
                    logger.info("콘텐츠 로딩 완료")
                except PlaywrightTimeout:
                    logger.warning("일부 콘텐츠 로딩 타임아웃 (계속 진행)")
                
                # HTML 가져오기
                html = page.content()
                
                browser.close()
                return html
                
        except Exception as e:
            logger.error(f"Playwright 페이지 로드 실패: {e}")
            return None
    
    def extract_image_url(self, html, restaurant):
        """HTML에서 이미지 URL 추출"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        
        if restaurant.name == "원테이블":
            # 프로필 이미지
            img_tag = soup.find('img', class_='img_thumb', alt='프로필이미지')
            if img_tag and 'src' in img_tag.attrs:
                src = img_tag['src']
                if 'fname=' in src:
                    parsed = urlparse(src)
                    params = parse_qs(parsed.query)
                    if 'fname' in params:
                        decoded_url = unquote(params['fname'][0])
                        return decoded_url
        else:
            # 게시글 이미지
            div = soup.find('div', class_='wrap_fit_thumb')
            if div and 'style' in div.attrs:
                style = div['style']
                style = unescape(style)
                match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                if match:
                    return match.group(1)
        
        return None
    
    def extract_post_date(self, html):
        """게시글에서 날짜 추출"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        
        title_tag = soup.find('strong', class_='tit_card')
        if title_tag:
            return title_tag.text.strip()
        
        return None
    
    def download_image(self, url):
        """이미지 다운로드"""
        import requests
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return Image.open(BytesIO(response.content))
        except Exception as e:
            logger.error(f"이미지 다운로드 실패: {e}")
            return None
    
    def preprocess_image(self, image):
        """이미지 전처리 (OCR 정확도 향상)"""
        max_size = 2000
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        return image
    
    def extract_text_from_image(self, image):
        """이미지에서 텍스트 추출"""
        self.init_ocr()
        
        image = self.preprocess_image(image)
        
        try:
            results = self.reader.readtext(image)
            texts = [text for (bbox, text, conf) in results]
            return '\n'.join(texts)
        except Exception as e:
            logger.error(f"OCR 처리 실패: {e}")
            return ""
    
    def parse_date(self, text):
        """텍스트에서 날짜 파싱"""
        patterns = [
            (r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', lambda m: datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3))
            )),
            (r'(\d{1,2})월\s*(\d{1,2})일', lambda m: datetime(
                datetime.now().year, int(m.group(1)), int(m.group(2))
            )),
            (r'(\d{1,2})\.(\d{1,2})', lambda m: datetime(
                datetime.now().year, int(m.group(1)), int(m.group(2))
            )),
            (r'(\d{1,2})/(\d{1,2})', lambda m: datetime(
                datetime.now().year, int(m.group(1)), int(m.group(2))
            )),
        ]
        
        for pattern, parser in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    date = parser(match)
                    logger.info(f"날짜 파싱 성공: {text} -> {date.strftime('%Y-%m-%d')}")
                    return date
                except ValueError:
                    continue
        
        logger.warning(f"날짜 파싱 실패: {text}")
        return None
    
    def is_today(self, date):
        """오늘 날짜인지 확인"""
        if date is None:
            return False
        today = datetime.now().date()
        return date.date() == today
    
    def scrape_menu(self, restaurant):
        """식당 메뉴 스크래핑"""
        logger.info(f"=== {restaurant.name} 스크래핑 시작 ===")
        
        # 1. Playwright로 페이지 가져오기
        html = self.fetch_page_with_playwright(restaurant.url)
        if not html:
            return None
        
        logger.info(f"HTML 길이: {len(html):,} bytes")
        
        # 2. 이미지 URL 추출
        image_url = self.extract_image_url(html, restaurant)
        if not image_url:
            logger.warning(f"{restaurant.name}: 이미지 URL을 찾을 수 없습니다")
            return None
        
        logger.info(f"이미지 URL: {image_url}")
        
        # 3. 이미지 다운로드
        image = self.download_image(image_url)
        if not image:
            return None
        
        # 4. 날짜 확인
        menu_date = None
        
        if restaurant.date_in_post:
            post_title = self.extract_post_date(html)
            if post_title:
                logger.info(f"게시글 제목: {post_title}")
                menu_date = self.parse_date(post_title)
        
        # 5. OCR로 이미지에서 텍스트 추출
        ocr_text = self.extract_text_from_image(image)
        logger.info(f"OCR 결과:\n{ocr_text[:200]}...")
        
        # 원테이블의 경우 이미지에서 날짜 추출
        if not restaurant.date_in_post or menu_date is None:
            menu_date = self.parse_date(ocr_text)
        
        # 6. 오늘 날짜 확인
        is_today_menu = self.is_today(menu_date)
        
        result = {
            'restaurant': restaurant.name,
            'date': menu_date.strftime('%Y-%m-%d') if menu_date else '날짜 미확인',
            'is_today': is_today_menu,
            'image_url': image_url,
            'menu_text': ocr_text,
            'image': image
        }
        
        logger.info(f"{restaurant.name} 스크래핑 완료 - 오늘 메뉴: {is_today_menu}")
        return result


class EmailNotifier:
    """이메일 알림 클래스"""
    
    def __init__(self, sender_email, sender_password, recipient_email):
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.recipient_email = recipient_email
    
    def send_menu_notification(self, menu_results):
        """메뉴 이메일 전송"""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.image import MIMEImage
        import requests
        
        today = datetime.now().strftime('%Y년 %m월 %d일')
        
        msg = MIMEMultipart('related')
        msg['Subject'] = f"🍱 {today} 점심 메뉴"
        msg['From'] = self.sender_email
        msg['To'] = self.recipient_email
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .restaurant {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .restaurant h2 {{ color: #333; }}
                .menu-image {{ max-width: 100%; height: auto; }}
                .menu-text {{ background: #f5f5f5; padding: 10px; white-space: pre-wrap; }}
                .warning {{ color: #ff6b6b; padding: 10px; background: #fff3cd; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>🍱 {today} 점심 메뉴</h1>
        """
        
        today_menus = [m for m in menu_results if m and m['is_today']]
        old_menus = [m for m in menu_results if m and not m['is_today']]
        
        if not today_menus and not old_menus:
            html += "<p>❌ 오늘 메뉴를 찾을 수 없습니다.</p>"
        
        if today_menus:
            for i, menu in enumerate(today_menus):
                html += f"""
                <div class="restaurant">
                    <h2>🍽️ {menu['restaurant']}</h2>
                    <p>📅 {menu['date']}</p>
                    <img src="cid:image{i}" class="menu-image" alt="{menu['restaurant']} 메뉴"/>
                    <div class="menu-text">{menu['menu_text'][:1000]}</div>
                </div>
                """
                
                try:
                    response = requests.get(menu['image_url'], timeout=10)
                    response.raise_for_status()
                    
                    # Content-Type에서 MIME 타입 추출
                    content_type = response.headers.get('Content-Type', 'image/jpeg')
                    if '/' in content_type:
                        subtype = content_type.split('/', 1)[1].split(';')[0].strip()
                    else:
                        subtype = 'jpeg'
                    
                    img = MIMEImage(response.content, _subtype=subtype)
                    img.add_header('Content-ID', f'<image{i}>')
                    msg.attach(img)
                    logger.info(f"이미지 첨부 성공: {menu['restaurant']}")
                except Exception as e:
                    logger.error(f"이미지 첨부 실패 ({menu['restaurant']}): {e}")
        
        if old_menus:
            html += """
            <div class="warning">
                <h3>⚠️ 아직 업데이트되지 않은 메뉴</h3>
                <ul>
            """
            for menu in old_menus:
                html += f"<li>{menu['restaurant']} (마지막 업데이트: {menu['date']})</li>"
            html += """
                </ul>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        
        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            logger.info("이메일 전송 성공!")
            return True
        except Exception as e:
            logger.error(f"이메일 전송 실패: {e}")
            return False


def main():
    """메인 함수 - 재시도 로직 포함"""
    SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
    SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
    RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL')
    
    if not SENDER_EMAIL or not SENDER_PASSWORD or not RECIPIENT_EMAIL:
        logger.error("SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL 환경 변수를 설정해주세요")
        return
    
    restaurants = [
        Restaurant(
            name="왕의밥상",
            url="https://pf.kakao.com/_kSxlln/posts",
            channel_id="_kSxlln",
            date_in_post=True
        ),
        Restaurant(
            name="착한한식뷔페",
            url="https://pf.kakao.com/_xgPnnn/posts",
            channel_id="_xgPnnn",
            date_in_post=True
        ),
        Restaurant(
            name="원테이블",
            url="https://pf.kakao.com/_gVFMn",
            channel_id="_gVFMn",
            date_in_post=False
        ),
    ]
    
    MAX_RETRIES = 6
    RETRY_INTERVAL = 15 * 60
    
    scraper = MenuScraper()
    notifier = EmailNotifier(SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL)
    
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"시도 {attempt}/{MAX_RETRIES}")
        logger.info(f"현재 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")
        
        results = []
        for restaurant in restaurants:
            try:
                result = scraper.scrape_menu(restaurant)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"{restaurant.name} 처리 중 오류: {e}")
        
        today_menus = [r for r in results if r and r['is_today']]
        
        if today_menus:
            logger.info(f"✅ 오늘 메뉴를 찾았습니다! ({len(today_menus)}개)")
            notifier.send_menu_notification(results)
            logger.info("이메일 전송 완료. 프로그램 종료.")
            return
        else:
            logger.warning(f"⚠️ 아직 오늘 메뉴가 올라오지 않았습니다.")
            
            if attempt < MAX_RETRIES:
                wait_minutes = RETRY_INTERVAL // 60
                logger.info(f"⏰ {wait_minutes}분 후에 다시 시도합니다...")
                time.sleep(RETRY_INTERVAL)
            else:
                logger.warning(f"⏰ 최대 재시도 횟수에 도달했습니다.")
                if results:
                    logger.info("가장 최근 메뉴를 전송합니다.")
                    notifier.send_menu_notification(results)
                else:
                    logger.error("수집된 메뉴 정보가 없습니다.")
                return


if __name__ == "__main__":
    main()
