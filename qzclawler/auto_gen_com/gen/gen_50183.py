import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 循环遍历每个职位条目
    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        # 提取职位标题
        title_elem = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4")
        title = title_elem.get_text(strip=True) if title_elem else ""

        # 提取所有标签信息
        job_labels = item.find_all("div", class_="style__STJobLabel-editor__sc-10r1nhd-12 jALFTx")

        # 初始化各个字段的值
        job_type = ""
        location = ""
        job_category = ""

        # 按顺序提取实习类型、地区、职位类别
        if len(job_labels) >= 4:
            job_type = job_labels[0].get_text(strip=True).replace('招聘','') # 第一个标签作为实习类型
            location = job_labels[2].get_text(strip=True)  # 第三个标签作为地区
            job_category = job_labels[3].get_text(strip=True)  # 第四个标签作为职位类别
        elif len(job_labels) >= 3:
            job_type = job_labels[0].get_text(strip=True).replace('招聘','')  # 第一个标签作为实习类型
            location = job_labels[2].get_text(strip=True)  # 第三个标签作为地区
        elif len(job_labels) >= 2:
            job_type = job_labels[0].get_text(strip=True).replace('招聘','')  # 第一个标签作为实习类型
            job_category = job_labels[1].get_text(strip=True)  # 第二个标签作为职位类别
        if "实习" in job_type:
            job_type = "实习"
        # 组织信息字典
        job_info = {
            "announcement_name": title,
            "publish_time": "",  # 假设没有提供发布时间
            "link": "",  # 假设没有链接
            "hd_dept": "",  # 假设没有部门信息
            "hd_loc": location,  # 地区字段
            "hd_job_num": "",  # 假设没有职位编号
            "hd_job_category": job_category,  # 职位类别字段
            "hd_hopeworktype": job_type  # 实习类型字段
        }

        job_list.append(job_info)

    # 输出到文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)


