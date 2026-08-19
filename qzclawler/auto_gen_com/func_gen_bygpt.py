import os
from utils import project_path,ner_logger
from api.openai4o_api import call_gpt

prompt = '''
写一个python函数(extract_table_from_html),入参2个（1.htmlcontext  2.tempfile）
分析下面的html，转换成列表，写入json文件，
规则：
1. 只要函数即可，不要示例：
2. 输出JSON格式
3. 列表字段（公告名称(announcement_name)、发布时间(publish_time)、链接(link)、所属部门或机构(hd_dept)、工作地点(hd_loc)、招聘人数(hd_job_num)、招聘人数(hd_job_num)、职位类别(hd_job_category)）
4. 如果提取不到对应字段，赋值为空字符串""
{html_context}
'''


#根据输入的html调用大模型，生成解析函数
def gen_func_bygpt(_key,html_context): 
    #写入文件
    codefile = f"data/gen_func_code_{_key}_tmp.py"
    #如果CODE文件存在，则直接返回
    if os.path.exists(codefile):
        ner_logger.info(f"代码文件{codefile}文件存在，无需大模型生成，直接返回")
        return 

    _prompt =  prompt.replace("{html_context}",html_context) 
    ner_logger.info(f"正在调用大模型生成解析函数\n{_prompt}\n")
    _ok,_python_code = call_gpt(_prompt)
    ner_logger.info("大模型生成解析函数结束")
    if _ok:  
        #把代码写入文件
        with open(codefile, 'w', encoding='utf-8') as f:
            f.write(_python_code)
