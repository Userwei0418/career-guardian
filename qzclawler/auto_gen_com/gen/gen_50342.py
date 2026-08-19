
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []

    for item in soup.find_all('div', class_='position-item'):
        name = item.find('a', class_='name').text.strip()
        link = item.find('a', class_='name')['href']
        salary = item.find('div', class_='salary').text.strip()
        info = item.find('div', class_='position-info')
        
        city = info.find('span', class_='city').text.strip()
        experience = info.find('span', class_='experience').text.strip()
        degree = info.find('span', class_='degree').text.strip()
        job_num = info.find('span', class_='number').text.strip()
        publish_time = info.find('span', class_='updated').text.strip()

        position = {
            "announcement_name": name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # Placeholder as the department is not provided in the HTML
            "hd_loc": city,
            "hd_job_num": job_num,
            "hd_job_category": "",  # Placeholder as the job category is not provided in the HTML
        }
        
        positions.append(position)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)
