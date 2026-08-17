
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        a_tag = li.find('a', class_='item')
        title = a_tag.get('title').strip()
        link = a_tag.get('href')

        # Extracting job details from the description
        description = a_tag.find('p', class_='txt').text.strip()
        location = description.split('：')[1].split(' ')[0] if '招聘城市：' in description else ''

        # Placeholder values for other fields
        publish_time = ''  # This would need to be extracted from the context if available
        hd_dept = ''       # This would need to be extracted from the context if available
        hd_job_num = ''    # This would need to be extracted from the context if available
        hd_job_category = ''  # This would need to be extracted from the context if available

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": location,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
