import importlib
import sys
sys.path.append('../')
import json

from auto_gen.func_gen_bygpt import gen_func_bygpt
from utils import ner_logger

def load_and_execute(module_name, func_name,html_content,tmp_file):
    # 动态导入模块
    module = importlib.import_module(module_name)
    # 获取模块中的函数
    func = getattr(module, func_name)
    # 执行函数
    try:
        func(html_content,tmp_file)
    except Exception as e:
        with open(tmp_file,'w',encoding='utf-8') as f:
            #写入 []
            f.write("[]")
        ner_logger.error(f"执行解析html文件失败：{tmp_file}{e}！")
    
    #执行检查
    return check_result(module_name,html_content,tmp_file)

#对执行结果进行检查
def check_result(module_name,html_content,tmp_file):
    #读取文件,使用utf-8格式，转换成json格式
    with open(tmp_file,'r',encoding='utf-8') as f:
        result = f.read()
        result_json = []
        try:
            result_json = json.loads(result)
            if len(result_json) == 0:
                #调用生成处理函数代码
                gen_func_bygpt(module_name,html_content)
        except:
            ner_logger.error(f"执行解析html文件失败：{tmp_file},人工处理！")
        #检查处理返回
        if len(result_json) == 0:
            return False
        return True
#加载函数和html内容
def call_func(func_name,html_content,tmp_fname):
    # func_file  = f'gen_{func_name}.py'
    # tmp_fname = f'auto_gen/tmp/{func_name}.json'
    tmp_file = tmp_fname #project_path(tmp_fname)
    _ok = load_and_execute(func_name, 'extract_table_from_html',html_content,tmp_file)
    return _ok


def execute_page_action(module_name, page):
    # 动态导入模块
    module = importlib.import_module(module_name)
    # 获取模块中的函数
    func = getattr(module, "crawl_page")
    # 执行函数
    try:
        func(page)
    except Exception as e:
        ner_logger.error(f"执行动作错误：{module_name}{e}！")
        
def execute_index_action(module_name, page,sch_info):
    urls = []
    # 动态导入模块
    module = importlib.import_module(module_name)
    # 获取模块中的函数
    func = getattr(module, "crawl_page") 
    # 执行函数
    try:
        urls = func(page,sch_info)
    except Exception as e:
        ner_logger.error(f"执行动作错误：{module_name}  {e}！")
    return urls
# 使用示例
# 假设有一个名为 example.py 的文件，其中包含一个名为 example_function 的函数
# load_and_execute('gen_00001', 'extract_table_from_html',"",'a.txt')