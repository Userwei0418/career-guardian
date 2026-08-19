
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_listings = []

    job_cards = soup.find_all('a', class_='hover:no-underline')
    
    for job in job_cards:
        announcement_name = job.find('div', class_='text-xl')
        announcement_name = announcement_name.get_text(strip=True) if announcement_name else ""
        publish_time = job.find('div', class_='text-sm tracking-normal text-[#666] max-lg:mt-2').text.strip() if job.find('div', class_='text-sm tracking-normal text-[#666] max-lg:mt-2') else ""
        link = job['href'] if 'href' in job.attrs else ""
        
        details = job.find_all('div', class_='w-1/2 lg:w-40 xl:w-48')
        hd_dept = hd_loc = hd_job_num = hd_job_category = ""
        
        for detail in details:
            label = detail.find('div', class_='text-sm text-[#666]').text.strip() if detail.find('div', class_='text-sm text-[#666]') else ""
            value = detail.find('div', class_='mt-3 text-sm text-gray-800 lg:mt-5 lg:text-base').text.strip() if detail.find('div', class_='mt-3 text-sm text-gray-800 lg:mt-5 lg:text-base') else ""
            
            if label == "岗位类别":
                hd_job_category = value
            elif label == "工作地点":
                hd_loc = value
            elif label == "招聘人数":
                hd_job_num = value  # Assuming this field is present in the actual HTML
            # Add more fields as necessary

        job_listings.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_listings, f, ensure_ascii=False, indent=4)
