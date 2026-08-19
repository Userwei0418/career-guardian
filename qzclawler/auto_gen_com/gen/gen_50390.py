
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job_item in soup.find_all('li', {'data-qa': 'searchResultItem'}):
        job_data = {}
        
        # Extracting the job title
        title = job_item.find('span', class_='job-tile__title')
        job_data['announcement_name'] = title.get_text(strip=True) if title else ""
        
        # Extracting the publish date
        publish_date = job_item.find('div', class_='job-list-item__job-info-label--posting-date')
        publish_value = publish_date.find_next('div') if publish_date else ""
        job_data['publish_time'] = publish_value.get_text(strip=True) if publish_value else ""
        
        # Extracting the link
        link = job_item.find('a', class_='job-list-item__link')
        job_data['link'] = link['href'] if link else ""
        
        # Extracting the location
        location_label = job_item.find('div', class_='job-list-item__job-info-label--locations')
        location_value = location_label.find_next('div') if location_label else ""
        job_data['hd_loc'] = location_value.get_text(strip=True) if location_value else ""
        
        # Extracting the department
        # Assuming the department is part of the job title or can be extracted similarly
        job_data['hd_dept'] = ""  # Placeholder, as the department is not explicitly mentioned in the provided HTML
        
        # Extracting the job number
        job_data['hd_job_num'] = ""  # Placeholder, as the job number is not explicitly mentioned in the provided HTML
        
        # Extracting the job category
        job_data['hd_job_category'] = ""  # Placeholder, as the job category is not explicitly mentioned in the provided HTML
        
        job_list.append(job_data)

    # Writing to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
