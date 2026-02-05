#!/usr/bin/env python3
"""
점심 메뉴 자동 알림 시스템
GitHub Actions + EasyOCR + Telegram Bot
"""

import os
import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
import easyocr
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Restaurant:
    """식당 정보 클래스"""
    def __init__(self, name, url, channel_id, date_in_post=True):
        self.name = name
        self.url = url
        self.channel_id = channel_id
        self.date_in_post = date_in_post  # False면 이미지에서만 날짜 확인


class MenuScraper:
    """메뉴 스크래핑 클래스"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.reader = None  # EasyOCR reader는 필요할 때 초기화
        
    def init_ocr(self):
        """OCR 리더 초기화 (지연 로딩)"""
        if self.reader is None:
            logger.info("OCR 엔진 초기화 중...")
            self.reader = easyocr.Reader(['ko', 'en'], gpu=False)
            logger.info("OCR 엔진 초기화 완료")
    
    def fetch_page(self, url):
        """웹페이지 가져오기"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"페이지 로드 실패 ({url}): {e}")
            return None
    
    def extract_image_url(self, html, restaurant):
        """HTML에서 이미지 URL 추출"""
        soup = BeautifulSoup(html, 'html.parser')
        
        if restaurant.name == "원테이블":
            # 프로필 이미지 찾기
            img_tag = soup.find('img', class_='img_thumb', alt='프로필이미지')
        else:
            # 게시글 이미지 찾기
            div = soup.find('div', class_='wrap_fit_thumb')
            if div and 'style' in div.attrs:
                style = div['style']
                match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                if match:
                    return match.group(1)
            return None
        
        if img_tag and 'src' in img_tag.attrs:
            # 썸네일이 아닌 원본 이미지 URL 추출
            src = img_tag['src']
            if 'fname=' in src:
                match = re.search(r'fname=(.*?)$', src)
                if match:
                    from urllib.parse import unquote
                    return unquote(match.group(1))
            return src
        
        return None
    
    def extract_post_date(self, html):
        """게시글에서 날짜 추출"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # 게시글 제목에서 날짜 찾기
        title_tag = soup.find('strong', class_='tit_card')
        if title_tag:
            return title_tag.text.strip()
        
        return None
    
    def download_image(self, url):
        """이미지 다운로드"""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return Image.open(BytesIO(response.content))
        except Exception as e:
            logger.error(f"이미지 다운로드 실패: {e}")
            return None
    
    def preprocess_image(self, image):
        """이미지 전처리 (OCR 정확도 향상)"""
        # 이미지가 너무 크면 리사이즈
        max_size = 2000
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        # RGB로 변환
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        return image
    
    def extract_text_from_image(self, image):
        """이미지에서 텍스트 추출"""
        self.init_ocr()
        
        # 이미지 전처리
        image = self.preprocess_image(image)
        
        # OCR 수행
        try:
            results = self.reader.readtext(image)
            # 텍스트만 추출
            texts = [text for (bbox, text, conf) in results]
            return '\n'.join(texts)
        except Exception as e:
            logger.error(f"OCR 처리 실패: {e}")
            return ""
    
    def parse_date(self, text):
        """텍스트에서 날짜 파싱"""
        patterns = [
            # 2026년 02월 05일
            (r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', lambda m: datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3))
            )),
            # 2월 5일 (목)
            (r'(\d{1,2})월\s*(\d{1,2})일', lambda m: datetime(
                datetime.now().year, int(m.group(1)), int(m.group(2))
            )),
            # 02.05 또는 2.5
            (r'(\d{1,2})\.(\d{1,2})', lambda m: datetime(
                datetime.now().year, int(m.group(1)), int(m.group(2))
            )),
            # 2/5
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
        
        # 1. 페이지 가져오기
        html = self.fetch_page(restaurant.url)
        if not html:
            return None
        
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
            # 게시글 제목에서 날짜 추출
            post_title = self.extract_post_date(html)
            if post_title:
                logger.info(f"게시글 제목: {post_title}")
                menu_date = self.parse_date(post_title)
        
        # 5. OCR로 이미지에서 텍스트 추출 (날짜 또는 메뉴 정보)
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
        from io import BytesIO
        
        today = datetime.now().strftime('%Y년 %m월 %d일')
        
        # 이메일 메시지 생성
        msg = MIMEMultipart('related')
        msg['Subject'] = f"🍱 {today} 점심 메뉴"
        msg['From'] = self.sender_email
        msg['To'] = self.recipient_email
        
        # HTML 본문 시작
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
        
        # 오늘 메뉴
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
                
                # 이미지 첨부
                try:
                    response = requests.get(menu['image_url'], timeout=10)
                    img = MIMEImage(response.content)
                    img.add_header('Content-ID', f'<image{i}>')
                    msg.attach(img)
                except Exception as e:
                    logger.error(f"이미지 첨부 실패: {e}")
        
        # 아직 업데이트 안 된 메뉴
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
        
        # 이메일 전송
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
    """메인 함수"""
    # 환경 변수에서 이메일 정보 가져오기
    SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
    SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
    RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL')
    
    if not SENDER_EMAIL or not SENDER_PASSWORD or not RECIPIENT_EMAIL:
        logger.error("SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL 환경 변수를 설정해주세요")
        return
    
    # 식당 정보
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
            date_in_post=False  # 이미지에서만 날짜 확인
        ),
    ]
    
    # 스크래핑 실행
    scraper = MenuScraper()
    results = []
    
    for restaurant in restaurants:
        try:
            result = scraper.scrape_menu(restaurant)
            if result:
                results.append(result)
        except Exception as e:
            logger.error(f"{restaurant.name} 처리 중 오류: {e}")
    
    # 이메일 알림 전송
    if results:
        notifier = EmailNotifier(SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL)
        notifier.send_menu_notification(results)
    else:
        logger.warning("수집된 메뉴 정보가 없습니다")


if __name__ == "__main__":
    main()
