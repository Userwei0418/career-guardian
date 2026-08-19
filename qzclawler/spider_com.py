# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import configparser
from collections import defaultdict
from typing import Any, Callable

from auto_gen_com.func_call import call_func,execute_page_action
from utils import ner_logger,get_long_url_domain
from utils_date import is_near_month
from utils import get_final_url,check_contact,check_url_type,get_random_number
from utils import is_wechat_url
from utils_html import clean_html
from utils_resume import remove_announcement_word
from utils_playwright import click_by_text_and_get_url,get_iframe_urls,get_redirect_url
from auto_api.baidu_data_proc_api import api_proc as auto_api_proc
from auto_on_response.main_proc import on_response_proc
from monitor import CrawlerMonitor  # 导入监控模块

#设置临时爬取进度文件
TMP_PROGRESS_FILE = "data/progress_com.txt"
#设置首页的停顿时间
FIRST_PAUSE_TIME = 10
#明细页面停顿时间
# SECOND_PAUSE_TIME = 5
# 设置整个测试的超时时间为 120 秒
PAGE_TIMEOUT = 60000
#默认的函数执行包
DEFAULT_FUNC_PACKAGE = "auto_gen_com.gen"
#默认节点的key值
DEFAULT_COMMON = "Common"
DEFAULT_TEMPLATE = "Template"
DEFAULT_COM = "Company"

class SpiderCom():
    """公司职位抓取（基于 ini 配置的可扩展爬虫）。"""
    def __init__(self,_file="99"):
        self.browser = None
        self.file = _file
        self.config = configparser.ConfigParser()  # 创建对象
        self.config.read("data/setting_default.ini", encoding="utf-8")
        self.config.read("data/setting_template.ini", encoding="utf-8")
        self.config.read(f"data/setting_com_{_file}.ini", encoding="utf-8")
        self.progress_list = []
        if os.path.exists(self.get_progress_file()):
            with open(self.get_progress_file(),"r",encoding="utf-8") as f:
                # 进度文件只记录“最后处理到的 key”，取第一条非空即可
                for line in f:
                    line = line.strip()
                    if line:
                        self.progress_list = [line]
                        break
        #获取临时目录
        TMP_DIR = self.get_savepath()
        ner_logger.info(f"临时目录：{TMP_DIR}")
        
        # 初始化监控
        self.monitor = CrawlerMonitor()
        ner_logger.info(f"监控系统已初始化")

    #获取进度文件
    def get_progress_file(self):
        return f"data/progress_com_{self.file}.txt" 
    #打印所有的学校
    def print_all_com(self):
        config = configparser.ConfigParser()  # 创建对象
        config.read("data/setting_default.ini", encoding="utf-8")
        printdict = defaultdict(list)
        #循环0-100，加载所有的配置文件
        for i in range(0,100): 
             _confilefile = f"data/setting_com_{i}.ini"
             if os.path.exists(_confilefile):
                config.read(_confilefile, encoding="utf-8")
        #打印所有的学校
        for _key in config.options(DEFAULT_COM):
            if _key.startswith("com_"):
                _svalue = config.get(DEFAULT_COM,_key)
                _value = json.loads(_svalue) 
                for _sch_info in _value:
                    sch = _sch_info.get("com_name")
                    sch_webname = _sch_info.get("com_webname")
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

        if len(_remain) > 0:
            _msg = "\n".join(_remain)
            ner_logger.info(f'剩余进度{len(_remain)/len(self.get_nodes())} - {_msg}%，人工启动重新跑')
            return _remain
        elif len(_finish) > 0:
            _msg = "\n".join(_finish)
            ner_logger.info(f'重新进度{len(_finish)/len(self.get_nodes())} - {_msg}%，人工启动重新跑')
            return _finish
        return _finish + _remain
    #获取节点列表
    def get_nodes(self):
        nodes = {}
        # 直接读取配置项并按 key 排序（比 1..100000 扫描更快）
        if not self.config.has_section(DEFAULT_COM):
            return nodes
        keys = [k for k in self.config.options(DEFAULT_COM) if k.startswith("com_")]
        for _key in sorted(keys):
            _svalue = self.config.get(DEFAULT_COM,_key)
            _value = json.loads(_svalue)
            #补充字段
            self.supplement_node_info(_value)
            nodes[_key] = _value
        return nodes
    #获取微信等的外部stype
    def get_other_type(self):
        return self.config.get(DEFAULT_COMMON,"weixin_style") 
    #获取链接补充上域名
    def get_full_url(self,domain,_link):
        #如果带着域名，则无需增加了
        if _link.startswith("http"):
            return _link
        #如果带有/开头的
        if _link.startswith("/"):
             return f'{domain}{_link}'
        return f'{domain}/{_link}'
    #补充节点信息
    def supplement_node_info(self,_node):
        for _com_info in _node:
            _template = _com_info.get("template")
            if _template:
                _tv = self.config.get(DEFAULT_TEMPLATE,_template)
                # ner_logger.info(f"获取节点{_template} / {_tv}")
                _tvjson = json.loads(_tv)
                for _key,_va in _tvjson.items():
                    if not _key in _com_info:
                        _com_info[_key] = _va
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
        #查找sch_info是否有table_selector_re
        selector1_re= f"{selector1}_re"
        ner_logger.info(f"尝试使用正则{sch_info.get(selector1_re)}")
        if sch_info.get(selector1_re): 
            regex_pattern = sch_info.get(selector1_re)
            div_elements = page.query_selector_all('div')
            for element in div_elements:
                class_name = element.get_attribute('class') or ''
                # ner_logger.info(f"div class_name:{class_name}")
                if re.search(regex_pattern, class_name):
                   return True,f"div.{class_name}"
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
            ner_logger.debug(f"goto: response={response} refer={refer} url={url}")
            if response:
                status = response.status
                if status in [200,412]: #有个学校特殊，兰州大学返回412 不知道为啥
                    page.wait_for_load_state('load',timeout=PAGE_TIMEOUT)
                    try:
                        page.wait_for_load_state('networkidle',timeout=30000)
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

    def _log_crawl(
        self,
        *,
        key: str,
        company_name: str,
        crawl_type: str,
        url: str,
        file_hash: str,
        status: str,
        duration: float,
        error: str = "",
    ) -> None:
        """统一监控记录入口，避免到处重复拼字段。"""
        try:
            self.monitor.log_crawl(
                key=key,
                company_name=company_name,
                config_file=self.file,
                crawl_type=crawl_type,
                url=url,
                file_hash=file_hash,
                status=status,
                error=error,
                duration=duration,
            )
        except Exception as e:
            # 监控写失败不影响主流程
            ner_logger.error(f"监控记录失败: {e}")

    def _auto_scroll_to_bottom(self, page, *, max_scrolls: int = 9999, sleep_s: float = 2.0) -> None:
        """滚动到底部以触发懒加载；到达稳定高度或达到上限退出。"""
        last_height = page.evaluate("document.body.scrollHeight")
        scroll_count = 0
        while scroll_count < max_scrolls:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(sleep_s)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                ner_logger.info(f"页面滚动完成，共滚动{scroll_count + 1}次")
                return
            last_height = new_height
            scroll_count += 1
            ner_logger.info(f"第{scroll_count}次滚动，当前页面高度: {new_height}")
        ner_logger.warning(f"已达到最大滚动次数({max_scrolls})，可能还有未加载的内容")

    def _click_load_more(self, page, sch_info) -> None:
        """按配置“点击加载更多”（可选）；失败时仅记录日志，不中断列表解析。"""
        click_load_more_setting = (sch_info.get("click_load_more", "") or "").upper()
        if click_load_more_setting != "Y":
            ner_logger.info(
                f"未启用点击加载更多功能(click_load_more = '{sch_info.get('click_load_more', '')}')，跳过此步骤"
            )
            return

        ner_logger.info("尝试点击加载更多内容")
        load_more_method = sch_info.get("load_more_method", "function")
        max_clicks = int(sch_info.get("max_load_more_clicks", 1))
        click_count = 0

        if load_more_method == "element":
            load_more_selector = sch_info.get("load_more_selector", "")
            if not load_more_selector:
                ner_logger.error("未提供load_more_selector，请检查配置")
                return
            while click_count < max_clicks:
                try:
                    load_more_button = page.query_selector(load_more_selector)
                    if load_more_button and load_more_button.is_visible():
                        load_more_button.click()
                        click_count += 1
                        ner_logger.info(f"第{click_count}次点击加载更多按钮成功")
                        time.sleep(5)
                    else:
                        ner_logger.info("加载更多按钮不存在或不可见，停止点击")
                        break
                except Exception as e:
                    ner_logger.error(f"点击加载更多按钮时出错: {e}")
                    break
        else:
            while click_count < max_clicks:
                _ok = self.pre_page_run(page, sch_info, "click_load_more_func_name")
                if not _ok:
                    ner_logger.info("点击加载更多内容失败或没有更多内容可加载")
                    break
                click_count += 1
                ner_logger.info(f"第{click_count}次点击加载更多内容成功")
                time.sleep(5)

        ner_logger.info(f"总共点击了{click_count}次加载更多按钮")
    #执行打开的前置任务
    def pre_page_run(self,page, sch_info,func_name = "table_func_name"):
        #获取信息
        #处理打开页面后的前置任务 ,比如打开页面后点击页面上的按钮
        func_package = DEFAULT_FUNC_PACKAGE#sch_info.get("func_package")
        table_func_name = sch_info.get(func_name)
        if table_func_name:
            package_func_name = f"{func_package}.{table_func_name}"
            ner_logger.info(f"执行前置{func_name}任务{package_func_name}")
            # 调用函数
            return execute_page_action(package_func_name,page)   
        #默认返回没有找到
        return False 
    #特殊api的执行
    def api_proc(self,page,_key, com_info,_stat):
        return self._special_proc(page, _key, com_info, _stat, label="api", proc=auto_api_proc)
    #特殊on_response的执行
    def on_resp_proc(self,page,_key, com_info,_stat):
        return self._special_proc(page, _key, com_info, _stat, label="on_response", proc=on_response_proc)

    def _special_proc(
        self,
        page,
        _key: str,
        com_info: dict,
        _stat: dict,
        *,
        label: str,
        proc: Callable[..., Any],
    ):
        sch_name = com_info.get("com_name")    #公司名
        sch_webname = com_info.get("com_webname")
        ner_logger.info(f"使用{label}爬取公司 {sch_name} - {sch_webname}")

        pre_open_url = com_info.get("pre_open_url")
        if pre_open_url:
            self.open_with_url(page, pre_open_url)

        urls = com_info.get("urls") or {}
        for k in urls:
            url = urls.get(k)
            proc(self, page, _key, com_info, k, url, _stat)
            time.sleep(FIRST_PAUSE_TIME * 30)

        self.write_process_file(_key)
    #执行
    def run(self,page,_key, com_info,_stat):
        #保存返回的列表
        _ret_list = []
        _list = []
        #获取信息
        sch_name = com_info.get("com_name")    #公司名
        sch_webname = com_info.get("com_webname")
        #特殊的走api
        data_proc_type = com_info.get("data_proc_type","")
        if data_proc_type == "api":
            return self.api_proc(page,_key, com_info,_stat)
        elif data_proc_type == "on_response":
            return self.on_resp_proc(page,_key, com_info,_stat)
        #正规的按逻辑
        ner_logger.info(f"爬取公司 {sch_name} - {sch_webname}")
        urls = com_info.get("urls")
        for i,k in enumerate(urls):
            url = urls.get(k) 
            #需要检测是否有预先要打开的页面
            pre_open_url = com_info.get("pre_open_url")
            if pre_open_url:
                _ok = self.open_with_url(page,pre_open_url)
                if not _ok:
                    ner_logger.info(f"预先打开页面{pre_open_url}失败,但是可以继续执行下一步")
                    #return False
                #输出日志
                ner_logger.info(f"预先打开页面{pre_open_url}")
                time.sleep(FIRST_PAUSE_TIME)
                    #使用浏览器打开链接
            _ok =self.open_with_url(page,url) 
            if not _ok:
                ner_logger.info(f"浏览器打开的页面存在问题，跳过{url}")
                _ret_list.append(False)
            #执行第一次列表任务
            self.get_page_data(page,_key,com_info,url,k)
            #增加判断是否爬取多少
            _page_count = 0
            _page_start = 2
            if "page_func_name" in com_info and 'method' in _stat and _stat['method'] == "cp_full":
                _page_count = 1000 
            elif "page_count" in com_info and com_info['page_count'] == 'Y':
                _page_count = 3
            #开始页面,并且是数字
            if "page_start" in _stat:
                _page_start = _stat['page_start']
            #判断是否有分页的要求
            if _page_count > 1 :
                func_name = com_info.get("page_func_name")
                for i in range(2,_page_count):
                    time.sleep(2)
                    _ok = self.pre_page_run(page, com_info,"page_func_name")
                    #如果成功并且需要没到开始页面，则继续
                    if _ok and i < _page_start:
                        ner_logger.info(f"分页{i}跳过")
                        time.sleep(3) 
                    elif _ok:
                        ner_logger.info(f"执行分页{i}任务{func_name}成功")
                        time.sleep(FIRST_PAUSE_TIME)
                        _purl = url + f"&p={i}"
                        #执行分页任务
                        self.get_page_data(page,_key,com_info,_purl,k)
                    else:
                        ner_logger.info(f"执行分页{i}任务{func_name}失败")
                        break
            #停顿
            time.sleep(FIRST_PAUSE_TIME)
        #写入处理的临时进度表
        self.write_process_file(_key)
    #爬取页面数据信息
    def get_page_data(self,page,_key,sch_info,url,k):
        #保存返回的列表
        _ret_list = []
        #打印爬取地址
        ner_logger.info(f"开始爬取链接：{_key} / {url}")
        #搜寻元素
        time.sleep(5)
        _ok,table_selector = self.get_selector_text(page,sch_info,"table_selector","table_selectors")
        if not _ok: 
            ner_logger.error(f"列表页面没有找到元素：{table_selector},人工处理！")
            _ret_list.append(False)
            return _ret_list

        # 动态列表常见为“滚动懒加载 + 点击加载更多”，两者均是可选增强
        self._auto_scroll_to_bottom(page)
        self._click_load_more(page, sch_info)

        tableObj = page.locator(table_selector)
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
                _ok = self.get_page_detail_data(page,_key,url,k,key_tmp_dir,sch_info,_item) 
                time.sleep(get_random_number())
                _ret_list.append(_ok) 
        #返回
        return _ret_list
    #爬取明细页面的数据信息
    def get_page_detail_data(self,page,_key,url,_k,key_tmp_dir,sch_info,_item):
        # 记录开始时间
        start_time = time.time()
        
        ner_logger.debug(f"detail parent url: {url}")
        _current_url = url
        #获取链接
        _link = _item.get("link")
        #获取地区
        area = _item.get("hd_loc")
        ner_logger.debug(f"area: {area}")
        #获取点击的文字
        _click_text = sch_info.get("click_text")
        _click_type = sch_info.get("click_type")
        _max_parent_level = sch_info.get("max_parent_level")
        ner_logger.debug(f"click: text={_click_text} type={_click_type} max_parent_level={_max_parent_level}")
        #默认内容
        _context_outtext = ""
        #如果链接是个javascript:则跳过 
        if _link and _link.startswith("javascript:"):
            # ner_logger.info(f"链接为javascript:，跳过{_item_title}")
            # return True
            _link = ""
        if not _link or _click_text == 'Y':
            _text = _item.get("announcement_name")
            announcement_name = _item.get("announcement_name")
            hd_loc = _item.get("hd_loc", "")
            # 拼接两个字段生成一个字符串
            combined_text = announcement_name + hd_loc
            #看一下文件是否存在
            _hash = hashlib.md5(combined_text.encode("utf-8")).hexdigest()
            tmp_file = os.path.join(key_tmp_dir,f"detail_{_hash}.url")
            if os.path.exists(tmp_file):
                with open(tmp_file,"r",encoding="utf-8") as f:
                    _link = f.read()
                    ner_logger.info(f"根据标题的值，从文件读取链接{_link}")
            if not _link or _click_text == 'Y': 
                # 打开目标网页，替换为你实际要操作的网址 
                time.sleep(get_random_number()) 
                new_url,content = click_by_text_and_get_url(page,url,_text,_click_type, area,_max_parent_level,_current_url)
                if new_url:
                    _link = new_url
                    _context_outtext = content
                    #_link 写入tmp_file
                    with open(tmp_file,"w",encoding="utf-8") as f:
                        f.write(_link)
                    ner_logger.info(f"链接为空,需要其他方式，使用点击 {_text} {_link}进行测试")
                    time.sleep(get_random_number())
            if not _link: 
                ner_logger.info(f"链接为空，跳过{_item}")
                
                # 记录失败（没有链接）
                duration = time.time() - start_time
                self._log_crawl(
                    key=_key,
                    company_name=sch_info.get("com_name", ""),
                    crawl_type="detail",
                    url=url,
                    file_hash="",
                    status="failed",
                    error="链接为空",
                    duration=duration,
                )
                
                return False
        #获取域名
        domain = sch_info.get("json_domain") 
        _fullurl = self.get_full_url(domain,_link)
        
        # 对于包含前端路由（#）的URL，直接使用原始URL，避免通过get_final_url处理
        # 因为get_final_url会忽略锚点部分，可能导致URL变化
        if "#" not in _fullurl:
            _final_link = get_final_url(_fullurl)
            #如果链接有变
            if _fullurl != _final_link:
                ner_logger.info(f"链接有变，从{_fullurl}到{_final_link}")
                _fullurl = _final_link 
        else:
            ner_logger.debug(f"检测到前端路由URL，直接使用原始URL: {_fullurl}")

        #生成临时文件名
        _hash = hashlib.md5(_fullurl.encode("utf-8")).hexdigest()
        tmp_file = os.path.join(key_tmp_dir,f"detail_{_hash}.html")  
        # tmp_full_file = os.path.join(key_tmp_dir,f"detail_{_hash}.html.full")  
        tmp_json_file = os.path.join(key_tmp_dir,f"detail_{_hash}.json")  
        #如果文件存在，则不爬取
        if os.path.exists(tmp_file) and os.path.exists(tmp_json_file):
            try:
                #如何只修改文件的修改时间 
                current_time = time.time()
                # 修改文件的访问时间和修改时间为当前时间
                os.utime(tmp_file, (current_time, current_time))
                os.utime(tmp_json_file, (current_time, current_time))
                ner_logger.info(f"文件 {tmp_json_file} 的修改时间已更新为当前时间。")
                
                # 记录成功（文件已存在，更新时间）
                duration = time.time() - start_time
                self._log_crawl(
                    key=_key,
                    company_name=sch_info.get("com_name", ""),
                    crawl_type="detail",
                    url=_fullurl,
                    file_hash=_hash,
                    status="success",
                    duration=duration,
                )
                
            except Exception as e:
                ner_logger.error(f"更新文件 {tmp_json_file} 的修改时间时出错：{str(e)}")
                
                # 记录失败
                duration = time.time() - start_time
                self._log_crawl(
                    key=_key,
                    company_name=sch_info.get("com_name", ""),
                    crawl_type="detail",
                    url=_fullurl,
                    file_hash=_hash,
                    status="failed",
                    error=f"更新文件时间失败: {str(e)}",
                    duration=duration,
                )
                
            return True
        ner_logger.debug(f"开始爬取链接：{_fullurl}")
        time.sleep(5)
        
        try:
            if _context_outtext == "": 
                _ok,_context_outtext = self.get_page_detail_content(page,sch_info,domain,_fullurl)
                if not _ok or _context_outtext == "":
                    ner_logger.info(f"获取页面内容失败，跳过{_fullurl}")
                    
                    # 记录失败
                    duration = time.time() - start_time
                    self._log_crawl(
                        key=_key,
                        company_name=sch_info.get("com_name", ""),
                        crawl_type="detail",
                        url=_fullurl,
                        file_hash=_hash,
                        status="failed",
                        error="获取页面内容失败",
                        duration=duration,
                    )
                    
                    return False
            #获取最后的url，有可能会有跳转
            _last_url = page.url
            #保存文件
            with open(tmp_file,"w",encoding="utf-8") as f:
                f.write(_context_outtext)
            #写入json的文件
            with open(tmp_json_file,"w",encoding="utf-8") as f:
                _item['full_url'] = _fullurl
                _item['last_url'] = _last_url
                # _item['upload'] = ""
                _item['file_path'] = tmp_file
                # _item['contact'] = ""
                _item['parent_url'] = url
                _item['channel'] = _key
                _item['job_type'] = _k.split("_")[0]
                # _item['type_url'] = ""
                #处理传递过来的公司
                _outtext = json.dumps(_item,ensure_ascii=False)
                f.write(_outtext)
            
            # 记录成功
            duration = time.time() - start_time
            self._log_crawl(
                key=_key,
                company_name=sch_info.get("com_name", ""),
                crawl_type="detail",
                url=_fullurl,
                file_hash=_hash,
                status="success",
                duration=duration,
            )
            
            #睡眠10s
            time.sleep(get_random_number())
            #正常返回
            return True
            
        except Exception as e:
            # 记录异常
            duration = time.time() - start_time
            self._log_crawl(
                key=_key,
                company_name=sch_info.get("com_name", ""),
                crawl_type="detail",
                url=_fullurl,
                file_hash=_hash,
                status="failed",
                error=str(e),
                duration=duration,
            )
            
            ner_logger.error(f"爬取明细页面异常: {e}")
            return False
            
    #根据url获取内容
    def get_page_detail_content(self,page,sch_info,domain,_fullurl,_redirect = True):
        # 使用浏览器新开一个 tab，打开链接（避免污染列表页上下文）
        page = self.browser.new_page()
        try:
            response = page.goto(_fullurl, wait_until="networkidle", timeout=3200000)
            # 加一句微小等待，让 JS 启动
            page.wait_for_timeout(1500)
        except Exception as e:
            ner_logger.error(f"访问页面发生异常: {e}, 链接: {_fullurl}")
            page.close()
            return False, ""

        # 尝试点掉 cookie / continue
        for btn in ["Accept", "同意", "Continue", "OK"]:
            try:
                page.locator(f"button:has-text('{btn}')").click(timeout=1500)
            except:
                pass
        time.sleep(get_random_number() * 2)
        if response and response.status == 200:
            #最后获取全部详情
            time.sleep(1)
            if 'redirect_url' in sch_info: 
                #检查是否有redirect
                _ok,_url = get_redirect_url(page)
                if _ok and _redirect:
                    return self.get_page_detail_content(page,sch_info,domain,_url,False)
            time.sleep(2)
            #获取内容
            _context_outtext = page.content()
            #先去找指定的元素
            _ok,detail_selector = self.get_selector_text(page,sch_info,"detail_selector","detail_selectors")
            if _ok:
            #获取明细页面的html
                detailObj = page.locator(detail_selector)
                element_count = detailObj.count()
                if element_count == 1:
                    outtext =[]
                    outtext.append("<div>")
                    outtext.append(detailObj.inner_html())
                    outtext.append("</div>")
                    _context_outtext = "\n".join(outtext)
                    page.close()
                    return True,_context_outtext
            #返回全部
            page.close()
            return True,_context_outtext 
        elif response and response.status == 404:
            # 如果是404错误，记录日志并返回False，继续下一个

            ner_logger.info(f"页面返回404错误，跳过此链接: {_fullurl}")
            page.close()
            return False, ""
        elif response and response.status == 403:
            # 如果是403错误，记录日志并返回False，继续下一个
            ner_logger.info(f"页面返回403错误，跳过此链接: {_fullurl}")
            page.close()
            return False, ""
        elif response and response.status == 500:
            # 如果是500错误，记录日志并返回False，继续下一个
            ner_logger.info(f"页面返回500错误，跳过此链接: {_fullurl}")
            page.close()
            return False, ""
        elif response and response.status == 503:
            # 如果是503错误，记录日志并返回False，继续下一个
            ner_logger.info(f"页面返回503错误，跳过此链接: {_fullurl}")
            page.close()
            return False, ""
        elif response and response.status == 504:
            # 如果是504错误，记录日志并返回False，继续下一个
            ner_logger.info(f"页面返回504错误，跳过此链接: {_fullurl}")
            page.close()
            return False, ""
        elif response and response.status == 502:
            # 如果是502错误，记录日志并返回False，继续下一个
            ner_logger.info(f"页面返回502错误，跳过此链接: {_fullurl}")
            page.close()
            return False, ""
        elif response and response.status == 400:
            # 如果是400错误，记录日志并返回False，继续下一个
            ner_logger.info(f"页面返回400错误，跳过此链接: {_fullurl}")
            page.close()
            return False, ""
        elif response and response.status == 401:
            # 如果是401错误，记录日志并返回False，继续下一个
            ner_logger.info(f"页面返回401错误，跳过此链接: {_fullurl}")
            page.close()
            return False, ""
        #关闭页面
        page.close()
        #错误
        ner_logger.error(f"明细页面没有找到元素,人工处理！")
        return False, ""