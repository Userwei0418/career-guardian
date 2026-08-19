
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_listings = []

    for li in soup.find_all('li')[1:]:  # Skip the header row
        date_div = li.find('div', style="float:left;width:120px;")
        name_div = li.find('div', style="float:left;width:500px;")
        
        if date_div and name_div:
            publish_time = date_div.get_text(strip=True)
            announcement_name = name_div.get_text(strip=True)
            link = date_div.find('a')['onclick'].split("'")[1] if date_div.find('a') else None
            
            link = f"https://jobcareer.sdu.edu.cn/eweb/jygl/index.so?modcode=jygl_zpxxck&subsyscode=zpfw&rklx=jyw&lmxhV=0402&type=ssoZxzpView&id={link}" if link else None

            job_listings.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_listings, f, ensure_ascii=False, indent=4)