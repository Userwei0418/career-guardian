import re
import os
from bs4 import BeautifulSoup
from utils import ner_logger
from urllib.parse import urlparse, urlunparse
from urllib.parse import parse_qs, urlencode
from urllib.parse import urljoin

#需要检测的标签
blacklist_tag = ['section','p','div','code']
blacklist_tag_html = ['section','p','div','code','span','a']

#重新组合url
def recombine_url(url):
    # 解析URL
    parsed_url = urlparse(url)
    # 解析查询参数
    query_params = parse_qs(parsed_url.query)
    # 对查询参数进行排序
    sorted_params = sorted(query_params.items())
    # 重新编码查询参数
    new_query = urlencode(sorted_params, doseq=True)
    # 构建新的URL
    new_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, new_query, parsed_url.fragment))
    return new_url
#获取url的目录
def get_directory_from_url(url):
    # 解析 URL
    parsed_url = urlparse(url)
    # 获取路径部分
    path = parsed_url.path
    # 找到路径中最后一个斜杠的位置
    last_slash_index = path.rfind('/')
    # 去除文件名，保留目录路径
    directory_path = path[:last_slash_index + 1]
    # 重新组合成目录的 URL
    directory_url = urlunparse((parsed_url.scheme, parsed_url.netloc, directory_path, '', '', ''))
    return directory_url

#获取链接的上级目录
def get_directory_url(url,_dir = '../'):
    # 解析 URL
    parsed_url = urlparse(url)
    # 获取 URL 的上级目录
    base_url = urljoin(url, _dir)
    #返回
    return base_url
def intit_blacklist_tail():
    _blacklist = []
    _blacklist_html = []
    _blacklist_md = []
    _blacklist_md_footer = []
    _data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    #读取black列表
    with open(os.path.join(_data_dir, "black_re.txt"), encoding="utf-8") as f:
        for _line in f.read().splitlines():
            _line = _line.strip()
            if _line:
                _blacklist.append(_line.strip())
    #读取black html列表
    with open(os.path.join(_data_dir, "black_re_html.txt"), encoding="utf-8") as f:
        for _line in f.read().splitlines():
            _line = _line.strip()
            if _line:
                _blacklist_html.append(_line.strip())
    #读取black html列表
    with open(os.path.join(_data_dir, "black_md.txt"), encoding="utf-8") as f:
        for _line in f.read().splitlines():
            _line = _line.strip()
            if _line:
                _blacklist_md.append(_line.strip())
    #读取black md footer列表
    with open(os.path.join(_data_dir, "black_md_footer.txt"), encoding="utf-8") as f:
        for _line in f.read().splitlines():
            _line = _line.strip()
            if _line:
                _blacklist_md_footer.append(_line.strip())

    return _blacklist,_blacklist_html,_blacklist_md,_blacklist_md_footer    
    # ner_logger.info(f"初始化黑名单 {len(blacklist_tail)}")
blacklist_tail,blacklist_tail_html,blacklist_md,blacklist_md_footer = intit_blacklist_tail()
# print("!!!!",blacklist_tail)
#输入html，返回清理后的html，主要是移除掉js，css等 
def clean_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.find_all('script'):
        script.extract()
    for link in soup.find_all('link', rel="stylesheet"):
        link.extract()
    # for style in soup.find_all('style'):
    #     style.extract()
    body_content = soup.body
    if body_content:
        return body_content.prettify()
    
    return soup.prettify()

#转换html到文本
def html2text(html):
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.find_all('script'):
        script.extract()
    for link in soup.find_all('link', rel="stylesheet"):
        link.extract()
    # for style in soup.find_all('style'):
    #     style.extract()
    body_content = soup.body 
    if body_content:
        return body_content.get_text()
    return soup.get_text()

#text清除空白行
def clean_text(text):
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        if line.strip():
            new_lines.append(line.strip())
    return '\n'.join(new_lines)

#获取微信里面的内容
def get_weixin_info(_hfile,_data):
    # if not os.path.exists(_hfile):
    #     return _data
    #读取html文件
    with open(_hfile, 'r', encoding='utf-8') as f:
        _hdata = f.read()
        #使用soup获取微信的部分信息
        soup = BeautifulSoup(_hdata, 'html.parser')
        # 获取公众号名称
        nickname_tag = soup.find('span', class_='profile_info_nickname')
        nickname = ""
        nickname = nickname_tag.get_text() if nickname_tag else ""
        if not nickname:#增加一层设置获取公众号获取
            nickname_tag = soup.find('a', class_='wx_tap_link js_wx_tap_highlight weui-wa-hotarea')
            nickname = nickname_tag.get_text() if nickname_tag else ""
        if not nickname:
            ner_logger.info(f"weixin 的 nickname为空，公众号名称: {_hfile}")
        _data['wx_name'] = nickname.strip()
        #获取公众号的id
        opentitle_tag = soup.find('h1', class_='rich_media_title')
        opentitle = opentitle_tag.get_text() if opentitle_tag else ""
        _data['wx_title'] = opentitle.strip()
        #获取时间
        public_time_tag = soup.find('em',id='publish_time')
        public_time = public_time_tag.get_text() if public_time_tag else ""
        _data['wx_public_time'] = public_time.strip()
#清理垃圾
def clean_weixin_html(_hfile,_hfile_0):
    #读取html文件
    with open(_hfile_0, 'r', encoding='utf-8') as f:
        _hdata = f.read()
        #使用soup获取微信的部分信息
        soup = BeautifulSoup(_hdata, 'html.parser')
        # 找到微信的#img-content节点
        img_content = soup.find('div', id='img-content')
        if not img_content:
            ner_logger.info(f'未找到微信的id img-content节点{_hfile_0}')
            img_content = soup.find('div', class_='img-content')
            if not img_content:
                ner_logger.info(f'未找到微信的class img-content节点{_hfile_0}')
                return
        #清除掉不需要的div
        _rmlist = []
        for section in img_content.find_all(blacklist_tag):
            nested_sections = section.find_all(blacklist_tag, recursive=False)  # 只查找直接子节点
            if nested_sections:
                continue
            #查询指定文本
            for _blkre in blacklist_tail:
                # 定义正则表达式，匹配 "本篇行业： xxxx"
                pattern = re.compile(_blkre)
                if re.findall(pattern, section.text) and len(section.text) < 100:
                    _rmlist.append(section)
                    # section1 = section
                    # while section1.find_next_sibling():
                    #     ner_logger.info(f'移除指定文本{section1.name},{section1.find_next_sibling().name}')
                    #     _ns1 = section1.find_next_sibling()
                    #     #如果是相同的标签，并且长度小于300，则继续移除
                    #     if _ns1.name == section1.name and len(str(_ns1)) < 300:
                    #         section1 = section1.find_next_sibling()
                    #         _rmlist.append(section1)
                    #     else:
                    #         break
        for _rm in _rmlist:
            ner_logger.info(f'移除指定文本{_rm.text},{_hfile}')
            _rm.decompose()  
        #写入html文件
        with open(_hfile, 'w', encoding='utf-8') as f:
            f.write(str(soup))     

def fix_html_blacklist(spider_data,soup,sch_info):
    for section in soup.find_all(blacklist_tag_html):
        nested_sections = section.find_all(blacklist_tag_html, recursive=False)  # 只查找直接子节点
        if nested_sections:
            continue

        # ner_logger.info(f'检查指定文本{section.text}')
        #清除掉不需要的div
        _rmlist = []
        #查询指定文本
        for _blkre in blacklist_tail_html:
            if not _blkre:
                continue
            # 定义正则表达式，匹配 "本篇行业： xxxx"
            pattern = re.compile(_blkre)
            if re.findall(pattern, section.text.strip()) and len(section.text.strip()) < 50:
                ner_logger.info(f'加入移除文本{section.text}')
                _rmlist.append(section)
                # section1 = section
                # while section1.find_next_sibling(): 
                #     _ns1 = section1.find_next_sibling()
                #     #如果是相同的标签，并且长度小于300，则继续移除
                #     if _ns1.name == section1.name and len(str(_ns1)) < 300:
                #         section1 = section1.find_next_sibling()
                #         _next_name = section1.find_next_sibling().name if section1.find_next_sibling() else ''
                #         ner_logger.info(f'加入移除相邻的文本{section1.name},{_next_name}')
                #         _rmlist.append(section1)
                #     else:
                #         break
        for _rm in _rmlist:
            ner_logger.info(f'实际移除指定文本{_rm.text}')
            _rm.decompose()  

#获取微信里面的链接
def get_weixin_hand_url(_hfile):
    #读取html文件
    with open(_hfile, 'r', encoding='utf-8') as f:
        _hdata = f.read()
        soup = BeautifulSoup(_hdata, 'html.parser')
        # 提取标题
        title = soup.h1.get_text()
        # 提取链接
        link = soup.find('a')['href']
        # 提取发布日期
        date_span = soup.find('span', string=lambda text: text and '发布时间' in text)
        date = date_span.get_text()
        match = re.search(r'发布时间:(\d{4}-\d{1,2}-\d{1,2})', date)
        # print("标题:", title)
        # print("链接:", link)
        # print("发布日期:", match.group(1))     
        return title,link,match.group(1)
#获取md文件的内容
def get_md_content(_mdfile,_tuning_md):
    # 正则表达式
    pattern = r'!?\[?.*?\]\(http'
    #空行
    pattern_jing = r'^\#\#[ ]*\#\#$'
    pattern_xing = r'^\*\*[ ]*\*\*$'

    _lines = []
    with open(_mdfile, 'r', encoding='utf-8') as f:
        #循环每一行
        for line in f: 
            #如果是空行，则跳过
            _lines.append(line)
    #如果有调优的，则添加
    if _tuning_md:
        for _tuning in _tuning_md.split('\n'):
            _lines.append(_tuning)
    #新的
    _nlist = [] 
    for i in range(len(_lines)):
        if i == 0 or i > len(_lines) - 2:
            _nlist.append(_lines[i])
            continue
        if _lines[i].strip() in ['.','·']:
            continue
        if re.findall(pattern_jing, _lines[i].strip()):
            continue
        if re.findall(pattern_xing, _lines[i].strip()):
            continue
        #判断上一行
        _linet = _lines[i-1]
        _linep = _lines[i+1]
        # print("[]",_linet,'~~~1~~',_linep,'~~2~~~',_lines[i],"{}")
        #上一个是链接，当前是空白
        if re.findall(pattern, _linet) and not _lines[i].strip() :
            continue
        #当前和上一个都是空白
        if not _linet.strip() and not _lines[i].strip() :
            continue
        #下一个是链接，当前是空白
        if re.findall(pattern, _linep) and not _lines[i].strip() :
            continue
        # print("结尾：",_lines[i])
        _nlist.append(_lines[i])

    return "".join(_nlist)

#定义微信链接的正则表达式模式
wx_url_pattern = r'\[?([^]]*)\] *\((http[s]?://mp.weixin.qq.com[^\)]+)\)'
pwx_url_pattern = r'^\] *\((http[s]?://[^\)]+)\)'
#定义微信链接的正则表达式模式
qz_url_pattern = r'\[([^]]*)\] *\((http[s]?://quanfile.obs.cn[^\)]+)\)'
# 使用正则表达式查找 ** 之间的内容并调用替换函数
xing_space_pattern  = r'\*\*[ ]+(.*?)[ ]+\*\*'
# 定义一个替换函数
def replace_spaces(match):
    # 将匹配到的字符串中的空格替换为空字符串
    return match.group(0).replace(' ', '')
#修复md文件
def fix_md(md_text,_props):
    #修复换行
    lines = md_text.split('\n')
    lines_1 = []
    #重新整理一下，链接会错行 
    # 第一行[1111
    #第二行]
    for i in range(len(lines)):
        if i == 0 or i > len(lines) - 2:
            lines_1.append(lines[i])
            continue
        #判断上一行
        _linet = lines[i-1]
        if _linet.strip().startswith('[') and (lines[i].strip() == "]" or re.match(pwx_url_pattern, lines[i].strip())):
            lines_1[-1] = _linet.strip() + lines[i]
            ner_logger.info(f"合并md的两行 {lines_1[-1]}")
            continue
        lines_1.append(lines[i])
        # print()
    #新的
    new_lines = []
    for line in lines_1:
        # ner_logger.info(f"修复md {line}")
        # 使用 re.search 函数进行匹配
        match = re.search(wx_url_pattern, line)
        if match:
            ner_logger.info(f"过滤无用的微信链接 {line}")
            continue
        #匹配全职
        match = re.search(qz_url_pattern, line)
        if match:
            ner_logger.info(f"优化了全职链接 {line}")
            new_lines.append(line.strip())
            continue
        # ner_logger.info(f"下222XXXXXXXX线  {line.strip()}")
        match = re.search(xing_space_pattern, line)
        if match:
            line = re.sub(xing_space_pattern, replace_spaces, line)
            # continue
        #移除找到的下面所有的垃圾
        _nospace_line = line.strip().replace(' ', '')
        _found = False
        for _blkre in blacklist_md_footer:
            if not _blkre.strip():
                continue 
            pattern = re.compile(_blkre.strip())
            if len(_nospace_line) < 30 and re.findall(pattern, _nospace_line):
                ner_logger.info(f"过滤向下所有无用的文本 {_nospace_line} —— {_blkre}")
                _found = True
                break
        if _found:
            break
        #移除垃圾
        _found = False 
        # ner_logger.info(f"下XXXXXXXX线  {line.strip()},{_nospace_line}")
        for _blkre in blacklist_md: 
            if not _blkre.strip():
                continue
            # ner_logger.info(f"开始过滤无用的文本_re {_blkre},{_nospace_line}")
            pattern = re.compile(_blkre.strip())
            if len(_nospace_line) < 30 and re.findall(pattern, _nospace_line):
                ner_logger.info(f"过滤无用的文本 {pattern},{line.strip()}")
                _found = True
                break
        if _found:
            continue
        #获取line里面的|的数量
        _p_count = line.count('|')
        if line.startswith('##') and (_p_count > 1 or _p_count > 0  and line.endswith('|')):
            line = line.replace('##','')
            new_lines.append(line.strip())
        elif line.startswith('**') and (_p_count > 1 or _p_count > 0  and line.endswith('|')):
            line = line.replace('**','')
            new_lines.append(line.strip())
            continue
        #处理尾部是空链接的情况
        if line.strip().endswith(']()'):
            line = line.strip()[:-2]
        new_lines.append(line.strip())
    # ner_logger.info(f'修复md {"\n".join(new_lines)}')
    #修复换行
    return "\n".join(new_lines)

def fix_md_after_gpt(md_text,_tuning_md):
    #针对markdown的\错误进行
      # 处理分隔符：将\后跟数字的情况转换为\\数字
    separator_pattern = r'\\(?=\d)'
    matches = re.findall(separator_pattern, md_text)
    if matches:
        ner_logger.info(f"修复markdown的\\错误 {matches}")
        md_text = re.sub(separator_pattern, r'\\\\', md_text)

    #修复换行
    lines = md_text.split('\n') 
    #新的
    new_lines = []
    for line in lines:    
        #匹配全职
        match = re.search(qz_url_pattern, line)
        if match:
            ner_logger.info(f"优化了全职链接_after {line}")
            new_lines.append(line.strip())
            continue    
        new_lines.append(line.strip())
    #如果有调优的，则添加
    if _tuning_md:
        new_lines.append("\n\n")
        for _tuning in _tuning_md.split('\n'):
            new_lines.append(_tuning)
    #修复换行
    return "\n".join(new_lines)

#获取html里面的微信链接
def find_wx_url(html_text,_search_text = 'N'):
    soup = BeautifulSoup(html_text, 'html.parser')
    links = soup.find_all('a')
    for link in links:
        url = link.get('href')
        if url and url.startswith('https://mp.weixin.qq.com/s'):
            return True,url
    # ner_logger.info(f"开始搜索微信链接{_search_text} {wx_url_pattern}{html_text}")
    #冲内容中找
    if str(_search_text) == 'Y':
        url_pattern = r'https://mp\.weixin\.qq\.com/s/[a-zA-Z0-9_]+'
        #使用正则在_text中查找微信链接
        match = re.search(url_pattern, html_text, re.UNICODE)
        if match:
            ner_logger.info(f"找到微信链接 {match.groups(0)}")
            return True,match.group(0)
    return False,None
