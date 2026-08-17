
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    articles = soup.find_all('article', class_='col-12 job-search-results-card-col')

    for article in articles:
        announcement_name = article.find('h3', class_='card-title job-search-results-card-title').get_text(strip=True)
        link = article.find('a', id=lambda x: x and x.startswith('link_job_title_')).get('href')
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        hd_dept = article.find('li', class_='job-component-dropdown-field-3').get_text(strip=True) if article.find('li', class_='job-component-dropdown-field-3') else ""
        hd_loc = ', '.join([loc.get_text(strip=True) for loc in article.find_all('li', class_='job-component-location')])
        hd_job_num = ""  # Assuming hd_job_num is not available in the provided HTML
        hd_job_category = article.find('li', class_='job-component-dropdown-field-4').get_text(strip=True) if article.find('li', class_='job-component-dropdown-field-4') else ""

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
