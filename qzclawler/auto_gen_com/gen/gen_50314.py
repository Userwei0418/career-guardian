
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='joinus_list_con'):
        title = job.find('div', class_='joinus_list_con_tit').get_text(strip=True)
        link = job.find('a')['href']
        details = job.find('div', class_='joinus_list_desc')
        job_type = details.find_all('ul')[0].find_all('li')[0].get_text(strip=True) if details.find_all('ul')[0].find_all('li') else ''
        location = details.find_all('ul')[0].find_all('li')[1].get_text(strip=True) if details.find_all('ul')[0].find_all('li') else ''
        category = details.find_all('ul')[0].find_all('li')[2].get_text(strip=True) if details.find_all('ul')[0].find_all('li') else ''
        department = details.find_all('ul')[0].find_all('li')[3].get_text(strip=True) if len(details.find_all('ul')[0].find_all('li')) > 3 else ''
        job_num = ''  # Placeholder as the job number is not provided in the HTML
        publish_time = ''  # Placeholder as the publish time is not provided in the HTML

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": department,
            "hd_loc": location,
            "hd_job_num": job_num,
            "hd_job_category": category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
