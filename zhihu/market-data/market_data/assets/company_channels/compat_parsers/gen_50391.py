

import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    articles = soup.find_all('article', class_='article--result')
    for article in articles:
        title_tag = article.find('h3', class_='article__header__text__title')
        link = title_tag.find('a')['href']
        announcement_name = title_tag.get_text(strip=True)

        subtitle = article.find('div', class_='article__header__text__subtitle')
        hd_loc = subtitle.find('b').get_text(strip=True)
        publish_time = subtitle.find_all('span')[-1].get_text(strip=True).replace('Posted ', '')

        # Placeholder values for hd_dept, hd_job_num, and hd_job_category
        hd_dept = ""
        hd_job_num = ""
        hd_job_category = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
