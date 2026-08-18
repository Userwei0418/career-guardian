
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.find_all('tr')[1:]  # Skip the header row
    announcements = []
    #获取公司
    div_element = soup.find('div', class_='title')
    company_name = ""
    if div_element:
        company_name = div_element.text.strip()
    email = ""
    div_element = soup.find('ul', class_='contact-list')
    if  div_element:
        #获取邮箱
        for li in div_element.find_all('li'):
            label = li.find('div', class_='label').text.strip()
            if label == '邮箱：':
                _email = li.find('div', class_='ct-info').text.strip()
                if "@" in _email:
                    email = _email
                    break

    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 5:
            announcement_name = cols[0].find('a').text.strip()
            link = cols[0].find('a')['href'].strip()
            publish_time = cols[4].text.strip()
            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_company": company_name,
                "hd_email": email
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)