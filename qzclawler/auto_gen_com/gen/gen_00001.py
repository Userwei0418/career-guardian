import json
from bs4 import BeautifulSoup

#
def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.find_all(class_='list-item-main'):
        name = item.find(class_='pos-name').get_text(strip=True)
        publish_time = item.find(class_='pos-pubTime').get_text(strip=True)
        #部门
        dept_name = ''
        if item.find(class_='pos-department'):
            dept_name = item.find(class_='pos-department').get_text(strip=True)
        if dept_name == "" and item.find(class_='pos-company'):
            dept_name = item.find(class_='pos-company').get_text(strip=True)
        #职业类别
        job_category_name = ''
        if item.find('div', class_='pos-cate'):
            job_category_name =  item.find('div', class_='pos-cate').get_text(strip=True)
        #地区
        loc_name = ''
        if item.find(class_='pos-locate'):
            loc_name = item.find(class_='pos-locate').get_text(strip=True)
        elif loc_name == '' and item.find(class_='pos-workPlace'):
            loc_name = item.find(class_='pos-workPlace').get_text(strip=True)
        #薪资
        salary = ""
        salary_tag = item.find(class_='pos-salary')
        if salary_tag:
            salary = salary_tag.get_text(strip=True)

        #招聘人数
        job_num = ""
        job_tag = item.find(class_='pos-num')
        if job_tag:
            job_num = job_tag.get_text(strip=True)

        link = ""
        announcements.append({
            "announcement_name": name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": dept_name,
            "hd_loc": loc_name,
            "hd_job_num": job_num,
            "hd_job_category": job_category_name,
            "hd_salary": salary
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)

# Note: The temp_file parameter should be a valid file path where the JSON file will be saved.