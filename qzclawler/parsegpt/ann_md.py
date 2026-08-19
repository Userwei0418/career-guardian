import html2text
from bs4 import BeautifulSoup
import re
import sys
sys.path.append('../')
import markdown
import os
import base64


from parsegpt.ann_img import replace_img_urls_with_base64
from utils import ner_logger,getMD5Str,remove_brackets
from utils_html import fix_html_blacklist,fix_md,get_directory_from_url,get_directory_url
from api.hwcloud_api import upload_file_to_obs
from utils_img import save_base64_img

#将md文件转换成html
def md_to_html(md_file_path, html_file_path):
    try:
        with open(md_file_path, 'r', encoding='utf-8') as md_file:
            md_content = md_file.read() #convert_markdown_images(md_file.read())
            html_content = markdown.markdown(md_content)
            # print(html_content)
            # raise(Exception("测试异常"))
        with open(html_file_path, 'w', encoding='utf-8') as html_file:
            html_file.write(html_content)
        return True
    except FileNotFoundError:
        print(f"文件 {md_file_path} 未找到，请检查文件路径是否正确。")
    except Exception as e:
        print(f"转换过程中出现错误: {e}")
    return False
#传入的html内容进行markdown处理
def html2md_with_fix(spider_data,_data,_fix_file,_md_file,_html,sch_info,_cache_dir,_hfile):
    #设置属性
    _props = {}
    _ok,_fix_html = fix_html(spider_data,_data,_html,sch_info,_props,_cache_dir,_hfile)
    if not _ok:
        return False,"",""
    #把_props 转成json
    # _jprops = json.dumps(_props,ensure_ascii=False) 
    # ner_logger.info(f"处理修复html {_fix_html} - \n{_props}\n")
    _data['props'] = _props 
    #写入文件
    with open(_fix_file,"w",encoding="utf-8") as f:
        f.write(_fix_html)
    #处理md文件
    _ok,md_text = html2md_table(spider_data,_fix_html,_fix_file,_data)
    if not _ok:
        return False,"",""
    #修复md文件
    md_text = fix_md(md_text,_props)
    #再次对格式进行优化
    md_text = common_process_sch_98534(_data,md_text)
    #写入md文件
    with open(_md_file,"w",encoding="utf-8") as f:
        f.write(md_text)
    # ner_logger.info(f"处理md文件 {_md_file} - \n{md_text}\n")
    #获取整个html全文文本内容,写入全文字段
    _full_text = get_html_content(_fix_html,_props)
    #返回属性文件
    return True,_data,_full_text

#处理转换到md文件
def html2md_table(spider_data,_fix_html,_fix_file,_data):
    #默认没有
    _data["has_table"]  = ""
    # 创建 BeautifulSoup 对象
    soup = BeautifulSoup(_fix_html, 'html.parser')
    # 找到表格元素
    tables = soup.find_all('table')
    #是否有合并单元格
    _has_colspan = False
    _has_table = ""
    # 获取表格的行数
    if tables:
        for table in tables:
            rows = table.find_all('tr')
            row_count = len(rows)
            if row_count > 3:
                _has_table = "OK"
            for row in rows:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    if 'rowspan' in cell.attrs or 'colspan' in cell.attrs:
                        _has_colspan = True
                        break
                    #如果单元格的内容为空
                    if not cell.text.strip():
                        _has_colspan = True
                        break
                if _has_colspan:
                    break
            if _has_colspan:
                break
    #没有合并单元格，则直接处理
    if not _has_colspan:
        _htmlfile = _fix_file
        _htmlfile_md = f"{_htmlfile}.md"
        spider_data.proc_html_md(_htmlfile,_htmlfile_md)
        if os.path.exists(_htmlfile_md):
            with open(_htmlfile_md,"r",encoding="utf-8") as f:
                _full_text = f.read()
            #如果处理完成则清除掉
            if os.path.exists(_htmlfile_md):
                os.remove(_htmlfile_md)
            #返回全文
            return True, _full_text
    else:
        _data["colspan"]  = "OK"
    #有表格
    _data["has_table"]  = _has_table
    
    return True,html2md(_fix_html)

#针对mdfile的优化，指定学校
def common_process_sch_98534(_data,md_text): 
    if _data['channel'] in ['sch_98534']: 
        try:
            block_re = re.compile(r'(### 岗位信息.*?)(?=### 岗位要求)', re.S)
            def _repl(m: re.Match) -> str:
                s = m.group(1)
                # 补齐格式
                # 1. 值前面拼接**
                s = re.sub(r'\n-\s+', '\n\n- **', s)
                # 2. 值后面拼接**
                s = re.sub(r'：\n\n', '：**\n\n', s)
                # 3. 多个*合并成2个，保持格式
                s = re.sub(r'\*{3,}', '**', s)
                # 4. 多个换行合并成2个，保持格式
                s = re.sub(r'\n{3,}', '\n\n', s)
                # 统一格式化
                # 1. 去行首 "- **"
                s = re.sub(r'(?m)^-\s*\*\*', '**', s)
                # 2. 有值的字段：把 "**\n\n值" 合并成 "**值"
                s = re.sub(r'(?<=\*\*)\n\n([^\*\*\n-].*)', r'\1', s)
                # 3. 空值字段：把 "**\n\n**" 压成 "**\n"
                s = re.sub(r'\*\*\n\*\*', '**\n\n**', s)
                return s
            #正则
            _md_text =  block_re.sub(_repl, md_text)
            md_text = _md_text
            ner_logger.info(f"针对mdfile的优化，指定学校98534{md_text}")
        except Exception as e:
            ner_logger.error(f"针对mdfile的优化，指定学校98534 Error:\n{e}")
    return md_text

#传入的html内容进行markdown处理
def html2md(htmltext):
    text_maker = html2text.HTML2Text()
    # text_maker = CustomHTML2Text()
    # 尝试关闭可能导致换行的选项，例如设置不使用软换行
    text_maker.soft_break = ''
    # text_maker.body_width = 0  #这个会导致大批文本在一行
    # text_maker.emphasis_mark = '#'
    # text_maker.ignore_emphasis = True
    # text_maker.strong_mark = '##'
    result = text_maker.handle(htmltext)
    result = re.sub(r'-\n', '-', result)
    return result

def fix_html(spider_data,_data,htmltext,sch_info,_props,_cache_dir,_hfile):
    #设置是否是外部链接
    _is_external_link = ""
    #使用soup加载html文件
    soup = BeautifulSoup(htmltext, 'html.parser')
    #检查文件是否是完整的html，如果是则不能处理暂时
    if soup.find('body'): 
        _data['is_external_link'] = "OK"
    #处理原生获取的信息
    find_hardcode_tag(soup,sch_info,_data,_hfile)
    #清理html里面的文字垃圾
    fix_html_blacklist(spider_data,soup,sch_info)
    #修复div
    fix_html_div(spider_data,soup,sch_info,_data)
    #修复相对路径
    fix_html_a(spider_data,soup,sch_info,_props,_data)
    #修复图片src
    fix_html_img_src(spider_data,soup,sch_info,_data,_cache_dir)
    #清理黑名单url这些
    rm_html_blacklist(spider_data,soup,sch_info)
    #转换成base64
    _ok = replace_img_urls_with_base64(spider_data,_data,soup,_props,_cache_dir)
    #返回
    return _ok,soup.prettify() 
#获取原生标记数据
def find_hardcode_tag(soup,sch_info,_data,_hfile):
    _hardcode_tag = []
    if 'detail_hd_company' in sch_info:
        _hardcode_tag = sch_info['detail_hd_company'].split('|')
    # ner_logger.info(f"原生获取的信息 {_hardcode_tag}")
    #获取原生标记数据
    for _tagstr in _hardcode_tag:
        _tag = _tagstr.split("#")
        company_tag = soup.find(_tag[0], class_=_tag[1])
        if company_tag and len(company_tag.text.strip()) > 2:
            _data['hd_company'] = remove_brackets(company_tag.text.strip()) 
    #处理全文中的获取
    fix_full_html_extract(sch_info,_data,_hfile,'detail_hd_ann_full','hd_ann')
    #处理全文中的获取
    fix_full_html_extract(sch_info,_data,_hfile,'detail_hd_company_full','hd_company')
    #处理tuning文本
    fix_full_html_extract(sch_info,_data,_hfile,'detail_tuning_classes_full','tuning_content')
def fix_full_html_extract(sch_info,_data,_hfile,_tag ,_tk ):
    if _tag in sch_info:
        _full_file = f'{_hfile}.full'
        ner_logger.info(f"{_tag} {_full_file}")
        #是否存在,完整的页面中获取某个元素
        if os.path.exists(_full_file):
            with open(_full_file,"r",encoding="utf-8") as f:
                _full_text = f.read()
                soup_full = BeautifulSoup(_full_text, 'html.parser')
                _hardcode_ann = []
                _hardcode_ann = sch_info[f'{_tag}'].split('|')
                ner_logger.info(f"原生信息 {_hardcode_ann}")
                for _tagstr in _hardcode_ann:
                    _tag = _tagstr.split("!")
                    if "#" in _tag[1]: 
                        _tag1 = _tag[1].split("#")    
                        ann_tag = soup_full.find(_tag[0], class_=_tag1[0])
                        if ann_tag:
                            _data[f'{_tk}'] = ann_tag.get(_tag1[1]) 
                    else:
                        ann_tag = soup_full.find(_tag[0], class_=_tag[1])
                        if ann_tag and len(ann_tag.text.strip()) > 2:
                            _data[f'{_tk}'] = remove_brackets(ann_tag.text.strip())
#清理黑名单
def rm_html_blacklist(spider_data,soup,sch_info):
    _domain_url = sch_info['json_domain']
    #查找所有的链接
    for img_tag in soup.find_all('img'):
        _href = img_tag.get('src')
        if _href is None:
            continue
        _md5 = getMD5Str(_href)

        ner_logger.info(f"图片 {_href},{_md5}")
        if spider_data.check_url_in_blacklist(_md5):
            img_tag.decompose()
            ner_logger.info(f"图片在黑名单里面,已经移除掉 {_href}")
#清除掉部分不用的html标签
def fix_html_div(spider_data,soup,sch_info,_data):
    # 需要清除的div的class
    _all_div_class = []
    if 'detail_rm_classes' in sch_info and len(sch_info['detail_rm_classes']) > 2:
        _all_div_class = sch_info['detail_rm_classes'].split('|')
    _all_div_id = []
    if 'detail_rm_ids' in sch_info and len(sch_info['detail_rm_ids']) > 2:
        _all_div_id = sch_info['detail_rm_ids'].split('|')
    #清除掉不需要的div
    _rmlist = []
    #记录顺序
    _index = []
    for div in soup.find_all('div'):
        _clist = div.get('class')
        if _clist != None: 
            for _class in _all_div_class:
                if '^' in _class:
                    _sclass = _class.split('^')
                    # ner_logger.info(f"div ^ { ".".join(_clist)} {_sclass} {len(_index)}")
                    if ".".join(_clist) == _sclass[0] and int(_sclass[1]) == len(_index):
                        _rmlist.append(div)
                        # ner_logger.info(f"需要移除的div ^ {_class} {_sclass} {len(_index)}")
                    if ".".join(_clist) == _sclass[0] and not div in _index:
                        _index.append(div)
                # print(div.get('class'))
                elif ".".join(_clist) == _class:
                    _rmlist.append(div)
        #处理ids
        for _id in _all_div_id:
            if div.get('id') == _id:
                _rmlist.append(div)

    #清除不必要的其他标签
    _all_oth_class = []
    if 'detail_rm_oth_classes' in sch_info and len(sch_info['detail_rm_oth_classes']) > 2:
        _all_oth_class = sch_info['detail_rm_oth_classes'].split('|')
        for _oclass in _all_oth_class:
            _h,_c = _oclass.split('!')
            # ner_logger.info(f"不需要的div,other detail_rm_oth_classes 检测 {_h} {_c}")
            o_tags = soup.find_all(_h, class_=_c)
            # 移除找到的标签
            for tag in o_tags:
                _rmlist.append(tag)
                #打印html
                # ner_logger.info(f"移除掉不需要的div,other detail_rm_oth_classes {str(tag)}")
    # 移除找到优化的标签
    _all_tuning_content = []
    if 'detail_tuning_classes' in sch_info and len(sch_info['detail_tuning_classes']) > 2:
        _all_tuning_class = sch_info['detail_tuning_classes'].split('|')
        for _oclass in _all_tuning_class:
            _h,_c = _oclass.split('!')
            ner_logger.info(f"需要优化的div,other 检测 {_h} {_c}")
            o_tags = soup.find_all(_h, class_=_c)
            if not o_tags:
                o_tags = soup.find_all(_h, id=_c)
            # 移除找到的标签
            for tag in o_tags: 
                _all_tuning_content.append(tag.get_text(separator='\n', strip=True))
                ner_logger.info(f"需要优化的div,other 添加 {_h} {_c}")
                _rmlist.append(tag)
        _data['tuning_content'] = _all_tuning_content
    #移除
    for div in _rmlist:
        # ner_logger.info(f"移除掉不需要的div,other {str(div)}")
        div.decompose()         
#修复链接
def fix_html_a(spider_data,soup,sch_info,_props,_data): 
    #链接
    _props_hrefs = {}
    _domain_url = sch_info['json_domain']
    #查找所有的链接
    for a in soup.find_all('a'):
        _href = a.get('href')
        if _href is None:
            continue
        #清除脚本
        if _href.startswith('javascript'):
            a.decompose()
            continue
        #http开头
        if _href.startswith('http'):
            _props_hrefs[_href] = ""
            continue 
        #相对路径
        if _href.startswith('/'):
            _href = _domain_url + _href 
            a['href'] = _href
            _props_hrefs[_href] = ""
        #如果是绝对路径
        if _href.startswith('./'):
            httpdir  = get_directory_from_url(_data['full_url'])
            _href = httpdir + _href[2:]
            a['href'] = _href
            _props_hrefs[_href] = ""        
    _props['hrefs'] = _props_hrefs
#修复链接
def fix_html_img_src(spider_data,soup,sch_info,_data,_cache_dir):
    _domain_url = sch_info['json_domain']
    #增加前置
    _pre_http = "https:"
    if _domain_url and _domain_url.startswith('http:'):
        _pre_http = "http:"
    #查找所有的链接
    for img_tag in soup.find_all('img'):
        _href = img_tag.get('src')
        if _href is None:
            continue
        if _href.startswith('http'):
            continue 
        if _href.startswith('//'):
            _href = _pre_http + _href 
        elif _href.startswith('/'):
            _href = _domain_url + _href 
        elif _href.startswith('../'):
            # ner_logger.info(f"_data {_data}")
            _lasturl = _data['full_url']
            if 'last_url' in _data and len(_data['last_url']) > 10:
                _lasturl = _data['last_url']
            httpdir  = get_directory_url(_lasturl) 
            _href = httpdir + _href[3:]
        elif re.match(r'^[a-zA-Z0-9]{1,30}/',_href):
             _href = f"{_domain_url}/{_href}"
        elif _href.startswith("file://"):
            _href = ""
        elif _href.startswith("data:image/png;base64"):
            _md5 = getMD5Str(_href)
            _cache_file = f"{_cache_dir}/{_md5}.png"
            _ok = save_base64_img(_cache_file,_href)
            if _ok:
                ner_logger.info(f"base64的保存图片到本地 {_cache_file}")
                _href=  upload_obs(f"{_md5}.png",_cache_file,{'Content-Type':'image/png'})#
            else:
                _href = ""
        elif _href.startswith("data:image/jpeg;base64"):
            _md5 = getMD5Str(_href)
            _cache_file = f"{_cache_dir}/{_md5}.jpeg"
            _ok = save_base64_img(_cache_file,_href)     
            if _ok:
                ner_logger.info(f"base64的保存图片到本地 {_cache_file}")   
                _href=  upload_obs(f"{_md5}.jpeg",_cache_file,{'Content-Type':'image/jpeg'})
            else:
                _href = ""
        img_tag['src'] = _href  

#上传到obs
def upload_obs(_cache_filename,_cachefile,headers):
     _ok,_url = upload_file_to_obs(_cache_filename,_cachefile,headers)
     if _ok:
         return _url
     return _cachefile

#获取html的全部内容
def get_html_content(htmltext,_props):
    #使用soup加载html文件
    soup = BeautifulSoup(htmltext, 'html.parser')
    #查找所有的链接
    for img_tag in soup.find_all('img'):
        _href = img_tag.get('src')
        _ohref = img_tag.get('q_url')
        if _ohref:
            #从属性中招
            if 'img_urls' in _props:
                for _url,imgmap in _props['img_urls'].items():
                    if _url == _ohref and 'img_ocr' in imgmap: 
                        img_tag.insert_after(imgmap['img_ocr'])
        elif _href and _href.startswith('http'):
            #从属性中招
            if 'img_urls' in _props:
                for _url,imgmap in _props['img_urls'].items():
                    if _url == _href and 'img_ocr' in imgmap: 
                        img_tag.insert_after(imgmap['img_ocr'])
    #写入html文件a.html
    # with open('a.html', 'w', encoding='utf-8') as f:
    #     f.write(soup.prettify())
    #获取全部内容
    return soup.get_text()


