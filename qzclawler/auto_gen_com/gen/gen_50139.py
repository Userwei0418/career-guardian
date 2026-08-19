import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='eve-list clearfix'):
        announcement_name = job.find('h2').text.strip()
        publish_time = job.find('div', class_='date').text.strip()
        link = ""  # Assuming the link is in the 'href' attribute
        tips = job.find('div', class_='tips').find_all('span')

        hd_dept =  ''
        hd_loc = tips[1].text.strip() if len(tips) > 1 else ''
        hd_job_num = ''  # Placeholder as the job number is not provided in the HTML
        hd_job_category = tips[2].text.strip() if len(tips) > 2 else ''  # Assuming the job category is the third tip

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


