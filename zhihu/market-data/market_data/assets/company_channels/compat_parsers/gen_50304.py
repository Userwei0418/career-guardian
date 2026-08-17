import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='pb-8 border-b border-[#CECECF] font-[MontForAnker]')

    for job in job_elements:
        title_tag = job.find('h3', class_='font-[500] text-[24px] leading-[28px] text-[#1D1D1F]')
        title = title_tag.get_text(strip=True) if title_tag else ""

        publish_tag = job.find('span', class_='font-HarmonyOS text-[16px] leading-[24px] text-[#86868C]')
        publish_time = publish_tag.get_text(strip=True) if publish_tag else ""

        details = job.find_all('span', class_='text-[16px] leading-[24px] text-[#1D1D1F]')
        job_category = details[0].get_text(strip=True) if len(details) >= 1 else ""
        job_location = details[1].get_text(strip=True) if len(details) >= 2 else ""
        job_type = details[2].get_text(strip=True) if len(details) >= 3 else ""

        link_tag = job.find('a')
        link = link_tag['href'] if link_tag and 'href' in link_tag.attrs else ""

        job_info = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": "",
            "hd_dept": "",
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": job_type.split(' / ')[0] if ' / ' in job_type else job_type
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
