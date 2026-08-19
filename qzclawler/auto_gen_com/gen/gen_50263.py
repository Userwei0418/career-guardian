
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card card-job'):
        announcement_name = card.find('h3', class_='card-title').get_text(strip=True)
        link = card.find('a', class_='stretched-link js-view-job')['href']
        hd_dept = card.find('p', class_='card-subtitle').get_text(strip=True)
        locations = [loc.get_text(strip=True) for loc in card.select('ul.list-inline.locations li.list-inline-item')]
        hd_loc = ', '.join(locations)
        hd_job_num = "" # Assuming the number of locations is the job number
        hd_job_category = hd_dept  # Assuming job category is the same as department
        hd_hope_worktype = ""  # Placeholder as no work type is provided in the HTML
        if "intern" in announcement_name.lower():
            hd_hope_worktype = "实习"
        else:
            hd_hope_worktype = ""
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",  # Placeholder as no publish time is provided in the HTML
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hope_worktype": hd_hope_worktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
