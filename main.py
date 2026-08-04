import asyncio
from datetime import datetime
import re
from xml.dom import minidom
from xml.etree import ElementTree as ET
from playwright.async_api import async_playwright

# 수집 대상 8개 카테고리 URL
CATEGORIES = [
    ("AI/Tech", "https://maily.so/app/discover/ai_tech"),
    ("Marketing", "https://maily.so/app/discover/marketing"),
    ("Culture", "https://maily.so/app/discover/culture"),
    ("Career", "https://maily.so/app/discover/career"),
    ("Money", "https://maily.so/app/discover/money"),
    ("Lifestyle", "https://maily.so/app/discover/lifestyle"),
    ("Knowledge", "https://maily.so/app/discover/knowledge"),
    ("Society", "https://maily.so/app/discover/society"),
]


def parse_korean_date(date_str):
    """'2026.08.04' 또는 '26.08.04' 문자열을 datetime 객체 및 YYYY.MM.DD 포맷 문자로 변환합니다."""
    if not date_str:
        return datetime.min, ""

    # 숫자만 추출 (예: '2026.08.04' -> ['2026', '08', '04'])
    numbers = re.findall(r"\d+", date_str)
    try:
        if len(numbers) >= 3:
            year, month, day = int(numbers[0]), int(numbers[1]), int(numbers[2])
            # 2자리 연도인 경우 2000년대 연도로 보정 (예: 26 -> 2026)
            if year < 100:
                year += 2000

            dt = datetime(year, month, day)
            # 🌟 YYYY.MM.DD 형태로 날짜 포맷팅
            formatted_date = dt.strftime("%Y.%m.%d")
            return dt, formatted_date
    except Exception:
        pass

    return datetime.min, date_str


async def fetch_all_posts_from_category(page, category_name, url):
    """지정한 카테고리 URL에서 모든 최신 포스트 데이터를 수집합니다."""
    print(f"🌐 [{category_name}] 접속 중: {url}")
    posts = []

    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)
        await page.wait_for_selector("a.not-prose", timeout=5000)

        cards = await page.query_selector_all("a.not-prose")
        print(f"  └ [{category_name}] 발견된 포스트: {len(cards)}개")

        for card in cards:
            # 1. 주소 (URL)
            href = await card.get_attribute("href")
            post_url = href if href and href.startswith("http") else f"https://maily.so{href}"

            # 2. 🌟 발행자/뉴스레터 이름 추출 (Trendium.ai 등)
            publisher_el = await card.query_selector("span.font-medium")
            publisher_name = (await publisher_el.inner_text()).strip() if publisher_el else ""

            # 3. 본문 원본 제목 추출
            title_el = await card.query_selector("p.font-bold")
            raw_title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

            # 🌟 제목 조합: [카테고리][뉴스레터 이름] 원본 제목
            if publisher_name:
                combined_title = f"[{category_name}][{publisher_name}] {raw_title}"
            else:
                combined_title = f"[{category_name}] {raw_title}"

            # 4. 날짜 추출 및 YYYY.MM.DD 변환
            date_el = await card.query_selector("div.text-\\[11px\\] span")
            raw_date = (await date_el.inner_text()).strip() if date_el else ""
            dt_obj, formatted_pub_date = parse_korean_date(raw_date)

            # 5. 요약 설명
            summary_el = await card.query_selector("p.text-slate-700")
            summary = (await summary_el.inner_text()).strip() if summary_el else ""

            posts.append({
                "category": category_name,
                "publisher": publisher_name,
                "url": post_url,
                "title": combined_title,
                "dt_obj": dt_obj,
                "pub_date": formatted_pub_date,
                "summary": summary,
            })

    except Exception as e:
        print(f"❌ [{category_name}] 수집 중 오류 발생: {e}")

    return posts


def generate_rss_xml(posts):
    """수집 후 날짜순 정렬된 리스트를 RSS 2.0 XML 표준 규격으로 변환합니다."""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    # RSS 채널 기본 헤더 정보
    ET.SubElement(channel, "title").text = "메일리 RSS"
    ET.SubElement(channel, "link").text = "https://maily.so/app/discover"
    ET.SubElement(channel, "description").text = "메일리 8개 카테고리 포스트 최신 날짜순 통합 피드"
    ET.SubElement(channel, "language").text = "ko"

    # 모든 포스트를 RSS <item> 요소로 추가
    for post in posts:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = post["title"]
        ET.SubElement(item, "link").text = post["url"]
        ET.SubElement(item, "guid").text = post["url"]
        ET.SubElement(item, "category").text = post["category"]

        # 🌟 pubDate 태그에 YYYY.MM.DD 형식 적용
        if post["pub_date"]:
            ET.SubElement(item, "pubDate").text = post["pub_date"]

        # 본문 요약
        ET.SubElement(item, "description").text = post["summary"]

    # XML 들여쓰기 정렬 후 변환
    xml_str = ET.tostring(rss, encoding="utf-8")
    parsed_xml = minidom.parseString(xml_str)
    return parsed_xml.toprettyxml(indent="  ")


async def main():
    all_collected_posts = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. 8개 카테고리를 순회하며 전체 포스트 수집
        for category_name, url in CATEGORIES:
            category_posts = await fetch_all_posts_from_category(page, category_name, url)
            all_collected_posts.extend(category_posts)

        await browser.close()

    print(f"\n🎉 총 {len(all_collected_posts)}개의 포스트 수집 완료!")

    # 2. 수집된 모든 포스트를 '최신 날짜순(내림차순)'으로 재정렬
    all_collected_posts.sort(key=lambda x: x["dt_obj"], reverse=True)
    print("⏳ 모든 포스트를 최신 날짜 순서대로 정렬 완료했습니다.")

    # 3. 통합 RSS XML 파일 생성
    rss_xml = generate_rss_xml(all_collected_posts)
    with open("maily_timeline.xml", "w", encoding="utf-8") as f:
        f.write(rss_xml)

    print("📄 'maily_timeline.xml' 파일로 최종 저장되었습니다.")


if __name__ == "__main__":
    asyncio.run(main())
