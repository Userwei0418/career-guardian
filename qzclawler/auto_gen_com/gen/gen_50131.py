
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all(class_='pro-item')
    
    result = []
    
    for item in items:
        announcement_name = item.find(class_='name-label').get_text(strip=True)
        link = item.find('a')['href']
        publish_time = item.find_all('span')[-1].get_text(strip=True)
        hd_job_category = item.find(class_='wrap-span').find_all('span')[0].get_text(strip=True)
        hd_loc = item.find(class_='wrap-span').find_all('span')[1].get_text(strip=True)
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        hd_dept = ""  # Assuming job category is the same as department
        
        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
