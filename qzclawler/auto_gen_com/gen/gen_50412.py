
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # Assuming the job postings are in a specific structure, we would need to find that structure
    # For example, if they are in a table or a specific div class
    # Here we will just create a mock structure since the provided HTML does not contain job postings

    # This is a placeholder for the actual extraction logic
    # You would replace this with the actual parsing logic based on the HTML structure
    job_postings = soup.find_all('div', class_='job-posting')  # Example class name

    for job in job_postings:
        announcement_name = job.find('h2', class_='announcement-name').text.strip()  # Example
        publish_time = job.find('span', class_='publish-time').text.strip()  # Example
        link = job.find('a', class_='job-link')['href']  # Example
        hd_dept = job.find('span', class_='hd-dept').text.strip()  # Example
        hd_loc = job.find('span', class_='hd-loc').text.strip()  # Example
        hd_job_num = job.find('span', class_='hd-job-num').text.strip()  # Example
        hd_job_category = job.find('span', class_='hd-job-category').text.strip()  # Example

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # Write the job list to a JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
