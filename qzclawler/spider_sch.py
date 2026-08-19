# -*- coding: utf-8 -*-
import os,hashlib,json,time
import configparser
import glob
import requests
import re
from collections import defaultdict

from auto_gen.func_call import call_func,execute_page_action,execute_index_action
from utils import ner_logger,get_long_url_domain
from utils_date import is_near_month
from utils import get_final_url,check_contact,check_url_type,get_random_number
from utils import is_wechat_url
from utils_html import clean_html,find_wx_url
from utils_html import get_directory_from_url
from utils_resume import remove_announcement_word
from utils_playwright import click_by_text_and_get_url,get_iframe_urls,get_redirect_url
from utils_bs4 import get_node_text
from monitor import CrawlerMonitor  # 导入监控模块

#设置临时爬取进度文件
TMP_PROGRESS_FILE = "data/progress.txt"
#设置首页的停顿时间
FIRST_PAUSE_TIME = 10
#明细页面停顿时间
# SECOND_PAUSE_TIME = 5
# 设置整个测试的超时时间为 120 秒
PAGE_TIMEOUT = 60000
#默认的函数执行包
DEFAULT_FUNC_PACKAGE = "auto_gen.gen"
#默认节点的key值
DEFAULT_COMMON = "Common"
DEFAULT_TEMPLATE = "Template"
DEFAULT_SCH = "School"

class SpiderSch():
    """学校职位抓取"""
    def __init__(self,_file="99"):
        self.browser = None
        self.file = _file
        self.config = configparser.ConfigParser()  # 创建对象
        self.config.read("data/setting_default.ini", encoding="utf-8")
        self.config.read("data/setting_template.ini", encoding="utf-8")
        self.config.read(f"data/setting_sch_{_file}.ini", encoding="utf-8")
        self.title_includes = self.config.get(DEFAULT_COMMON, "title_include").split("|")
        # self.title_excludes = self.config.get(DEFAULT_COMMON, "title_exclude").split("|")
        with open("data/black_wx_exclude_title.txt",encoding="utf-8") as f:
            _wxlist = f.read().splitlines()
            self.title_excludes = list(set(_wxlist))
        # self.executable_path = self.config.get("Common", "executable_path")
        #按行读取TMP_PROGRESS_FILE文件，生成数组
        self.progress_list = []
        if os.path.exists(self.get_progress_file()):
            with open(self.get_progress_file(),"r",encoding="utf-8") as f:
                for line in f.readlines():
                    if line.strip():
                        self.progress_list = [line.strip()]
        #获取临时目录
        TMP_DIR = self.get_savepath()
        ner_logger.info(f"临时目录：{TMP_DIR}")
        
        # 初始化监控
        self.monitor = CrawlerMonitor()
        ner_logger.info(f"SpiderSch 监控系统已初始化")

    #获取进度文件
    def get_progress_file(self):
        return f"data/progress_{self.file}.txt" 
    #打印所有的学校
    def print_all_sch(self):
        config = configparser.ConfigParser()  # 创建对象
        config.read("data/setting_default.ini", encoding="utf-8")
        printdict = defaultdict(list)
        #循环0-100，加载所有的配置文件
        for i in range(0,100): 
             _confilefile = f"data/setting_sch_{i}.ini"
             if os.path.exists(_confilefile):
                config.read(_confilefile, encoding="utf-8")
        #打印所有的学校
        for _key in config.options(DEFAULT_SCH):
            if _key.startswith("sch_"):
                _svalue = config.get(DEFAULT_SCH,_key)
                _value = json.loads(_svalue) 
                for _sch_info in _value:
                    sch = _sch_info.get("sch_name")
                    sch_webname = _sch_info.get("sch_webname")
                    printdict[sch].append(sch_webname)
        #打印 出现一次的
        for _key in printdict.keys():
            if len(printdict[_key]) == 1 : 
                print(f'{_key} : {" ".join(printdict[_key])}')
        #打印*出现20次
        print("-"*20)
        for _key in printdict.keys():
            if len(printdict[_key]) > 1 : 
                print(f'{_key} : {" ".join(printdict[_key])}')
    #判断标题是否在包括里面
    def is_title_include(self,title):
        _title = remove_announcement_word(title.strip())
        for _blkre in self.title_excludes:
            if _blkre.strip() == "":
                continue
            pattern = re.compile(_blkre) 
            if re.findall(pattern,_title):
                ner_logger.info(f"招聘公告的标题不符合要求，被过滤掉{title} : {_blkre}")
                return False       
        # for _title in self.title_includes:
        #     if _title in title:
        #         return True
        return True
    #获取微信等的外部stype
    def get_other_type(self):
        return self.config.get(DEFAULT_COMMON,"weixin_style") 
    #检查链接是否是外部链接
    def is_external_link(self,domain,_fullurl):
        #如果跟域名保持一致
        if _fullurl.startswith(domain):
            return False
        #微信也算内部连接
        if 'mp.weixin.qq.com' in _fullurl:
            return False
        #返回是外部链接
        return True
    #获取浏览器的路径
    def get_browser_path(self):
        tmp_dir = ""
        #获取当前操作系统是win10的时候
        if os.name == "nt":
            tmp_dir = self.config.get(DEFAULT_COMMON,"browser_path_win") 
        #如果浏览器是mac
        if os.name == "posix":
            tmp_dir = self.config.get(DEFAULT_COMMON,"browser_path_mac") 
        #检查一下目录，如果没有，则创建
        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)
        return tmp_dir
     #获取保存数据的目录 
    def get_savepath(self,_tmp = "/data/tmp"):
        if os.name == "nt":
            return self.config.get(DEFAULT_COMMON,"savepath_win") + _tmp 
        if os.name == "posix":
            return self.config.get(DEFAULT_COMMON,"savepath_mac") + _tmp 
        return ""
    #获取保存数据的目录
    def get_md_exe(self):
        if os.name == "nt":
            return self.config.get(DEFAULT_COMMON,"md_path_win")
        if os.name == "posix":
            return self.config.get(DEFAULT_COMMON,"md_path_mac")
        return ""
    #获取保存数据的目录
    def get_html_md_exe(self):
        if os.name == "nt":
            return self.config.get(DEFAULT_COMMON,"html_md_path_win")
        if os.name == "posix":
            return self.config.get(DEFAULT_COMMON,"html_md_path_mac")
        return ""
    #写入新的一行临时文件
    def write_process_file(self,line):
        with open(self.get_progress_file(),"w",encoding="utf-8") as f:
            f.write(line)
            f.write("\n")
        if not line in self.progress_list:
            self.progress_list = [line]
    #读取进度
    def get_progress(self):
        _finish = []
        _remain = []
        _find = False
        #如果进度100% ，则需要重新跑
        for _key , _node in self.get_nodes().items():
            if _key in self.progress_list:
                _finish.append(_key)
                _find = True
            elif _find == True:
                _remain.append(_key)
            else:
                _finish.append(_key) 

        if len(_remain) > 0 and not 'sch_88888' in _remain or len(_remain) > 1 and 'sch_88888' in _remain:
            _msg = "\n".join(_remain)
            ner_logger.info(f'剩余进度{len(_remain)/len(self.get_nodes())} - {_msg}%，人工启动重新跑')
            return _remain
        elif len(_finish) > 0 and not 'sch_88888' in _finish or len(_finish) > 1 and 'sch_88888' in _finish:
            _msg = "\n".join(_finish)
            ner_logger.info(f'重新进度{len(_finish)/len(self.get_nodes())} - {_msg}%，人工启动重新跑')
            return _finish
        return _finish + _remain
    #获取节点列表
    def get_nodes(self):
        nodes = {}
        #循环1000
        for i in range(1,100000):
             #把数字i变成五位长度的字符串，前面用0填充
             num = str(i).zfill(5)
             _key = f"sch_{num}"
             if self.config.has_option(DEFAULT_SCH,_key):
                 _svalue = self.config.get(DEFAULT_SCH,_key)
                #  ner_logger.info(f"获取节点{_key} / {_svalue}")
                 _value = json.loads(_svalue)
                #  ner_logger.info(f"获取节点1{_key} / {_value}")
                 #补充字段
                 self.supplement_node_info(_value)
                 nodes[_key] = _value
        return nodes
    #补充节点信息
    def supplement_node_info(self,_node):
        for _sch_info in _node:
            _template = _sch_info.get("template")
            if _template:
                _tv = self.config.get(DEFAULT_TEMPLATE,_template)
                # ner_logger.info(f"获取节点{_template} / {_tv}")
                _tvjson = json.loads(_tv)
                for _key,_va in _tvjson.items():
                    if not _key in _sch_info:
                        _sch_info[_key] = _va
    #获取链接补充上域名
    def get_full_url(self,domain,_link):
        #如果带着域名，则无需增加了
        if _link.startswith("http"):
            return _link
        #如果带有/开头的
        if _link.startswith("/"):
             return f'{domain}{_link}'
        return f'{domain}/{_link}'
    #获取目录 
    def get_key_dir(self,_key):
        TMP_DIR = self.get_savepath()
        key_tmp_dir = f"{TMP_DIR}/{_key}"
        if not os.path.exists(key_tmp_dir):
            os.makedirs(key_tmp_dir)   
        return key_tmp_dir
    #尝试获取页面的元素，如何没有则返回错误
    def get_selector_text(self,page,sch_info,selector1,selector2,style3 = ""):
        #获取页面的html
        html = page.content()
        #判断有没有这个元素，如果没有，则返回空
        table_selector = sch_info.get(selector1) #"table_selector"
        #page判断这个节点在page上有没有
        # 查找页面中第一个 <style> 元素
        style_element = page.query_selector(table_selector)
        if not style_element:
            #找一下是否有明细的
            table_selectors = sch_info.get(selector2) #"table_selectors"
            if table_selectors:
                table_selectors = table_selectors + style3
            elif  style3:
                table_selectors = style3
            #进行循环尝试获取
            if table_selectors:
                #循环查找
                for _selector in table_selectors.split("|"):
                    if not _selector.strip():
                        continue
                    ner_logger.info(f"尝试使用{_selector}")
                    style_element = page.query_selector(_selector)
                    if style_element:
                        table_selector = _selector
                        break
        #如果找到，则返回
        if style_element:
            ner_logger.info(f"找到元素{table_selector}")
            return True,table_selector
        #打印内容
        ner_logger.info(f"没有找到元素在页面内容里面:\n{html}")
        #返回没有找到
        ner_logger.info(f"没有找到元素{table_selector}")
        return False,table_selector
    #检查网址是否有问题
    def open_with_url(self,page,url,refer=""): 
        try:
            #设置页面的refer
            if refer: 
                page.set_extra_http_headers({"Referer": refer}) 
            response = page.goto(url,timeout=PAGE_TIMEOUT) 
            print(response,refer,url)
            if response:
                status = response.status
                if status in [200,412]: #有个学校特殊，兰州大学返回412 不知道为啥
                    try:
                        page.wait_for_load_state('load',timeout=PAGE_TIMEOUT)
                        page.wait_for_load_state('networkidle',timeout=120000)
                    except Exception as e:
                        ner_logger.info(f"尝试打开url时出错 networkidle: {e}")
                    time.sleep(3)
                    return True
                else:
                    ner_logger.debug(f"函数(open_with_url)调用:页面状态码错误{status}")
                    #等待页面加载完 
            elif page.url == url:
                ner_logger.debug(f"函数(open_with_url)调用无返回值，默认成功：{url}")
                time.sleep(3)
                return True
            else:
                ner_logger.debug(f"函数(open_with_url)调用:{response}")
        except Exception as e: 
            ner_logger.debug(f"操作超时{e}") 
        ner_logger.debug(f"函数(open_with_url)调用:页面存在问题{url}") 
        return False  
    #执行打开的前置任务
    def pre_page_run(self,page, sch_info):
        #获取信息
        #处理打开页面后的前置任务 ,比如打开页面后点击页面上的按钮
        func_package = DEFAULT_FUNC_PACKAGE#sch_info.get("func_package")
        table_func_name = sch_info.get("table_func_name")
        if table_func_name:
            package_func_name = f"{func_package}.{table_func_name}"
            # 调用函数
            execute_page_action(package_func_name,page) 
            ner_logger.info(f"执行前置任务{package_func_name}")
        # islink = sch_info.get("islink")  #跳转职位投递链接是否可以抓取下来 
    #获取index的列表，默认是配置，有些三级的列表需要爬取
    def get_index_list(self,page,sch_info):
        #获取信息
        urls = sch_info.get("urls")
        if 'index_url_func' in sch_info:
            _ok = self.open_with_url(page,urls.get('k1'))
            if not _ok:
                return []
            func_name = sch_info.get("index_url_func")
            #获取html解析的函数
            func_package = DEFAULT_FUNC_PACKAGE#sch_info.get("func_package") 
            package_func_name = f"{func_package}.{func_name}"
            # 调用函数
            urls = execute_index_action(package_func_name,page,sch_info) 
            ner_logger.info(f"执行获取index_url_func\n{urls}")
        else:
            urls = sch_info.get("urls")
        return urls
    def run(self,page,_key, sch_info,_stat = {}):
        #保存返回的列表
        _ret_list = []
        _list = []
        #获取信息
        sch_name = sch_info.get("sch_name")    #公司名
        sch_webname = sch_info.get("sch_webname")
        print(f"爬取学校{sch_name} - {sch_webname}")
        urls = self.get_index_list(page,sch_info)
        for i,k in enumerate(urls):
            url = urls.get(k) 
            #需要检测是否有预先要打开的页面
            pre_open_url = sch_info.get("pre_open_url")
            if pre_open_url:
                _ok = self.open_with_url(page,pre_open_url)
                if not _ok:
                    ner_logger.info(f"预先打开页面{pre_open_url}失败")
                    return False
                #输出日志
                ner_logger.info(f"预先打开页面{pre_open_url}")
                time.sleep(FIRST_PAUSE_TIME)
            else:
                #获取域名
                domain = get_long_url_domain(url)
                ner_logger.info(f"预先打开页面{url},{domain}")
                if len(domain) > 0:
                    _ok = self.open_with_url(page,domain[0])
                    if not _ok:
                        ner_logger.info(f"预先打开页面{domain[0]}失败")
                        return False
                    time.sleep(FIRST_PAUSE_TIME)

            _list = self.get_page_data(page,_key,sch_info,url)
            #如果有false在列表中
            if False in _list:
                _ret_list.append(False)
            else:
                _ret_list.append(True)
            #停顿
            time.sleep(FIRST_PAUSE_TIME)
        #写入处理的临时进度表
        self.write_process_file(_key)
    #爬取页面数据信息
    def get_page_data(self,page,_key,sch_info,url):
        #保存返回的列表
        _ret_list = []
        #打印爬取地址
        ner_logger.info(f"开始爬取链接：{_key} / {url}")
        #使用浏览器打开链接
        _ok =self.open_with_url(page,url)
        # page.goto(url)
        if not _ok:
            ner_logger.info(f"浏览器打开的页面存在问题，跳过{url}")
            _ret_list.append(False)
            return _ret_list
        _ok,table_selector = self.get_selector_text(page,sch_info,"table_selector","table_selectors")
        if not _ok: 
            ner_logger.error(f"列表页面没有找到元素：{table_selector},人工处理！")
            _ret_list.append(False)
            return _ret_list
        #执行前置任务
        self.pre_page_run(page, sch_info)

        tableObj = page.locator(table_selector)
        #如果找到多个
        if tableObj.count() > 1:
            #获取不要display: none的元素;
            for i in range(tableObj.count()):
                _tableObj = page.locator(table_selector).nth(i)
                if _tableObj.is_visible():
                    tableObj = _tableObj
                    break
        #如果还是多个，则使用第一个
        if tableObj.count() > 1:
            ner_logger.info(f"列表页面有多个元素，使用第一个")
            tableObj = tableObj.nth(0)
        outtext =[]
        outtext.append("<div>")
        outtext.append(tableObj.inner_html())
        outtext.append("</div>")
        # print("获得列表内容:\n","\n".join(outtext))
        #渠道的临时目录
        key_tmp_dir = self.get_key_dir(_key)
        #写入临时文件名
        _hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        _context_outtext = "\n".join(outtext)
        tmp_file = os.path.join(key_tmp_dir,f"index_{_hash}.html")
        with open(tmp_file,"w",encoding="utf-8") as f:
            f.write(_context_outtext)
        #获取html解析的函数
        func_package = DEFAULT_FUNC_PACKAGE#sch_info.get("func_package")
        func_name = sch_info.get("func_name")
        package_func_name = f"{func_package}.{func_name}"
        #输出临时JSON文件路径
        tmp_fname = f'{key_tmp_dir}/index_{_hash}.json'
        # 调用函数并打印结果
        _ok = call_func(package_func_name,_context_outtext,tmp_fname) 
        if not _ok:
            ner_logger.info(f"解析列表页面失败，跳过{url}")
            _ret_list.append(False)
            return _ret_list
        #等待3秒
        time.sleep(FIRST_PAUSE_TIME)
        #加载json文件
        with open(tmp_fname,"r",encoding="utf-8") as f:
            _data = json.load(f)
            #循环json
            for i,_item in enumerate(_data):
                _ok = self.get_page_detail_data(page,_key,url,key_tmp_dir,sch_info,_item) 
                time.sleep(get_random_number())
                _ret_list.append(_ok)

        #返回
        return _ret_list
    #爬取明细页面的数据信息
    def get_page_detail_data(self,page,_key,url,key_tmp_dir,sch_info,_item):
        # 记录开始时间
        start_time = time.time()
        
        #获取发布日期
        _publish_time = _item.get("publish_time")
        _item_title = _item.get("announcement_name")
        if _publish_time and not is_near_month(_publish_time): 
            ner_logger.info(f"日期不在180天内过期了{_publish_time}，跳过{_item_title}")
            return True
        #判断标题是否需要爬取 
        if not self.is_title_include(_item_title):
            ner_logger.info(f"标题在关键词排除之列，{_item_title}不需要爬取，跳过")
            return True
        #获取链接
        _link = _item.get("link") 
        #获取点击的文字
        _click_text = sch_info.get("click_text")
        _click_type = sch_info.get("click_type")
        #默认内容
        _context_outtext = ""
        #如果链接是个javascript:则跳过 
        if _link and _link.startswith("javascript:"):
            # ner_logger.info(f"链接为javascript:，跳过{_item_title}")
            # return True
            _link = ""
        #如果是相对的 ./
        elif _link and _link.startswith("./"):
            #获取url的上一级路径
            _url_path = get_directory_from_url(url)
            _link = _link.replace("./", _url_path)
        #如果没有链接，则需要点击获取
        if not _link or _click_text == 'Y':
            _text = _item.get("announcement_name") 
            #看一下文件是否存在
            _hash = hashlib.md5(_text.encode("utf-8")).hexdigest()
            tmp_file = os.path.join(key_tmp_dir,f"detail_{_hash}.url")
            if os.path.exists(tmp_file):
                with open(tmp_file,"r",encoding="utf-8") as f:
                    _link = f.read()
                    ner_logger.info(f"根据标题的值，从文件读取链接{_link}")
            if not _link or _click_text == 'Y': 
                # 打开目标网页，替换为你实际要操作的网址
                try:
                    page.goto(url)  
                except Exception as e:
                    ner_logger.info(f"打开页面失败，错误原因{e}")
                    
                    # 记录失败
                    duration = time.time() - start_time
                    self.monitor.log_crawl(
                        key=_key,
                        company_name=sch_info.get("sch_name", ""),
                        config_file=self.file,
                        crawl_type="detail",
                        url=url,
                        file_hash="",
                        status="failed",
                        error=f"打开页面失败: {str(e)}",
                        duration=duration
                    )
                    
                    return False 
                time.sleep(get_random_number())
                #执行前置任务
                self.pre_page_run(page, sch_info)
                new_url,content = click_by_text_and_get_url(page,url,_text,_click_type)
                if new_url:
                    _link = new_url
                    # _context_outtext = content
                    #_link 写入tmp_file
                    with open(tmp_file,"w",encoding="utf-8") as f:
                        f.write(_link)
                    ner_logger.info(f"链接为空,需要其他方式，使用点击 {_text} {_link}进行测试")
                    time.sleep(get_random_number())
            if not _link: 
                ner_logger.info(f"链接为空，跳过{_item}")
                
                # 记录失败（没有链接）
                duration = time.time() - start_time
                self.monitor.log_crawl(
                    key=_key,
                    company_name=sch_info.get("sch_name", ""),
                    config_file=self.file,
                    crawl_type="detail",
                    url=url,
                    file_hash="",
                    status="failed",
                    error="链接为空",
                    duration=duration
                )
                
                return False
        #获取域名
        domain = sch_info.get("json_domain") 
        _fullurl = self.get_full_url(domain,_link)
        _final_link = get_final_url(_fullurl)
        #如果链接有变
        if _fullurl != _final_link:
            ner_logger.info(f"链接有变，从{_fullurl}到{_final_link}")
            _fullurl = _final_link 
        #生成临时文件名
        _hash = hashlib.md5(_fullurl.encode("utf-8")).hexdigest()
        tmp_file = os.path.join(key_tmp_dir,f"detail_{_hash}.html")  
        tmp_full_file = os.path.join(key_tmp_dir,f"detail_{_hash}.html.full")  
        tmp_json_file = os.path.join(key_tmp_dir,f"detail_{_hash}.json")  
        #如果文件存在，则不爬取
        if os.path.exists(tmp_file) and os.path.exists(tmp_json_file):
            print(f"{_fullurl}文件已存在，跳过")
            
            # 记录成功（文件已存在）
            duration = time.time() - start_time
            self.monitor.log_crawl(
                key=_key,
                company_name=sch_info.get("sch_name", ""),
                config_file=self.file,
                crawl_type="detail",
                url=_fullurl,
                file_hash=_hash,
                status="success",
                duration=duration
            )
            
            return True
        ner_logger.debug(f"开始爬取链接：{_fullurl}")
        
        try:
            if not _context_outtext or len(_context_outtext) < 100:
                _ok,_context_outtext,_context_full_outtext = self.get_page_detail_content(page,sch_info,domain,_fullurl,refer=url)
                if not _ok or _context_outtext == "":
                    ner_logger.info(f"获取页面内容失败，跳过{_fullurl}")
                    
                    # 记录失败
                    duration = time.time() - start_time
                    self.monitor.log_crawl(
                        key=_key,
                        company_name=sch_info.get("sch_name", ""),
                        config_file=self.file,
                        crawl_type="detail",
                        url=_fullurl,
                        file_hash=_hash,
                        status="failed",
                        error="获取页面内容失败",
                        duration=duration
                    )
                    
                    return False
            #获取最后的url，有可能会有跳转
            _last_url = page.url
            #检测内容是否很短，如果很短，里面有微信文章则获取
            if len(_context_outtext) < 400 or 'search_wx_file' in sch_info:
                _search_wx_file = sch_info.get("search_wx_file") or "Y"
                ner_logger.info(f"内容少于400个字符，开始查找微信文章{_search_wx_file}")
                _ok,___url = find_wx_url(_context_outtext,_search_wx_file)
                if _ok:
                    _last_url = ___url
            #保存文件
            with open(tmp_file,"w",encoding="utf-8") as f:
                f.write(_context_outtext)
            #保存全部的文件
            with open(tmp_full_file,"w",encoding="utf-8") as f:
                f.write(_context_full_outtext)
            #写入json的文件
            with open(tmp_json_file,"w",encoding="utf-8") as f:
                _item['full_url'] = _fullurl
                _item['last_url'] = _last_url
                _item['upload'] = ''
                _item['file_path'] = tmp_file
                _item['contact'] = check_contact(_context_outtext)
                _item['parent_url'] = url
                _item['channel'] = _key
                _item['type_url'] = check_url_type(_fullurl,_last_url)
                #处理传递过来的公司
                _outtext = json.dumps(_item,ensure_ascii=False)
                f.write(_outtext)
            
            # 记录成功
            duration = time.time() - start_time
            self.monitor.log_crawl(
                key=_key,
                company_name=sch_info.get("sch_name", ""),
                config_file=self.file,
                crawl_type="detail",
                url=_fullurl,
                file_hash=_hash,
                status="success",
                duration=duration
            )
            
            #睡眠10s
            time.sleep(get_random_number())
            #正常返回
            return True
            
        except Exception as e:
            # 记录异常
            duration = time.time() - start_time
            self.monitor.log_crawl(
                key=_key,
                company_name=sch_info.get("sch_name", ""),
                config_file=self.file,
                crawl_type="detail",
                url=_fullurl,
                file_hash=_hash,
                status="failed",
                error=str(e),
                duration=duration
            )
            
            ner_logger.error(f"爬取明细页面异常: {e}")
            return False
            
    #根据url获取内容
    def get_page_detail_content(self,page,sch_info,domain,_fullurl,refer="",noiframe=True):
        #页面内容
        _context_outtext = ""
        #全部页面内容
        _context_full_outtext = ""
        #使用浏览器打开链接
        _ok =self.open_with_url(page,_fullurl,refer) 
        if not _ok:
            ner_logger.info(f"浏览器打开的页面存在问题，跳过{_fullurl}")
            return False,_context_outtext,_context_full_outtext
        #如果是微信的url，则获取全部文本内容
        if is_wechat_url(_fullurl):
            ner_logger.info(f"微信的url，获取全部文本内容{_fullurl}")
            _context_outtext = page.content()
            return True,_context_outtext,_context_outtext    
        #如果是use_bs4提取，则单独处理
        if 'use_bs4' in sch_info and sch_info['use_bs4'] != '':
            ner_logger.info(f"使用bs4提取内容{_fullurl}")
            _context_outtext = get_node_text(_fullurl,sch_info['use_bs4'])
            return True,_context_outtext,_context_full_outtext
        #如果有跳转
        if 'redirect_url' in sch_info: 
            #检查是否有redirect
            _ok,_url = get_redirect_url(page)
            ner_logger.info(f"检查是否有跳转{_ok} {_fullurl}")
            if _ok and noiframe:
                return self.get_page_detail_content(page,sch_info,domain,_url,False)
        #其他固定的类型
        _style3 = self.get_other_type()
        #获取全部页面内容
        _context_full_outtext =clean_html(page.content())
        #定位html中的内容主体元素
        _ok,detail_selector = self.get_selector_text(page,sch_info,"detail_selector","detail_selectors",_style3)
        if _ok:
        #获取明细页面的html
            detailObj = page.locator(detail_selector)
            element_count = detailObj.count()
            if element_count > 1:
                ner_logger.error(f"明细页面找到多个元素:{detail_selector}，跳过{_fullurl}")
                return False,_context_outtext,_context_full_outtext
            outtext =[]
            outtext.append("<div>")
            outtext.append(detailObj.inner_html())
            outtext.append("</div>")
            _context_outtext = "\n".join(outtext)
            return True,_context_outtext,_context_full_outtext
        detailIframe =  ""
        if 'detail_iframe' in sch_info and sch_info['detail_iframe'] != '':
            detailIframe = sch_info['detail_iframe']
        #从里面找iframe
        _iurls = get_iframe_urls(page,detailIframe)
        ner_logger.debug(f"页面有iframe:{_iurls}")
        if noiframe and len(_iurls)>0:
            ner_logger.info(f"页面有iframe，使用第一个iframe链接{_iurls[0]}")
            return self.get_page_detail_content(page,sch_info,domain,_iurls[0],"",False)
        if self.is_external_link(domain,_fullurl):
            ner_logger.error(f"明细页面没有找到元素:{detail_selector}，域名不同{_fullurl},使用全部页面数据！") 
            return True,_context_full_outtext,_context_full_outtext
        ner_logger.error(f"明细页面没有找到元素:{detail_selector},人工处理！")
        return False,_context_outtext,_context_full_outtext