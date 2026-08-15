import os
import socket
import hashlib
import datetime
import requests
import logging
import re 
from urllib.parse import urlparse, parse_qs
import time
import random
from urllib.parse import urljoin 
import hashlib 

#设置程序版本号
QZ_VERISON = '0.2.0, 2025-02-19'
#获取文件或者url的文件后缀
def get_file_extension(image_url): 
    # 提取文件名
    filename = os.path.splitext(image_url)[1]
    if filename in ['.png','.jpg','.gif','.webp','.jpeg','.svg']:
        return filename 
    # 解析链接
    parsed_url = urlparse(image_url)
    # 提取查询参数
    query_params = parse_qs(parsed_url.query)
    # 打印参数,获取文件后缀
    for key, value in query_params.items():
        if key in ['wx_fmt','tp'] and value[0] in ['png','jpg','gif','webp','jpeg','svg']:
            return f'.{value[0]}'
    return ''

#所有全部中文
def all_zh(keyword):
	for ch in keyword:
		if u'\u4e00' > ch or ch > u'\u9fff':
			return False
	return True

#获取os信息
def get_os_info(): 
	if os.name == 'posix' and os.uname().sysname == 'Darwin':
		return 'mac'
	return 'windows'
#工程的路径
def project_path(sub_path):
	current_path = os.path.dirname(os.path.realpath(__file__))
	return current_path+'/'+sub_path

def getMD5Str(content):
    hash = hashlib.md5()
    hash.update(content.encode("utf-8"))
    md5 = hash.hexdigest()
    return md5
#获取清除文本的统一规则，用于md5的值
def get_md5_clear_text(text):
     return text.replace('\n','').replace(' ','').replace('\r','').replace('\t','')
# print(getMD5Str("123456"))
def getMD5Bytes(content):
    import hashlib
    md5 = hashlib.md5()
    md5.update(content)  # 直接使用 bytes 类型的数据进行 MD5 计算
    return md5.hexdigest()
def get_final_url(url):
    #特殊情况，如果是微信文章，则直接返回，不需要再次获取明细
    if is_wechat_url(url):
        return url

    session = requests.Session()
    try:
        #增加头部信息
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        })
        #获取url的域名
        domain = urlparse(url).netloc
        #增加reference
        session.headers.update({
            'Referer': domain
        })
        resp = session.get(url, allow_redirects=False)
		# 如果有重定向，获取最终的URL
        if 300 <= resp.status_code < 400:
            final_url = resp.headers['Location']
            _newurl =  urljoin(url, final_url)
            #打印新的url
            ner_logger.info(f"重定向url{_newurl}")
            return get_final_url(_newurl)
    except:
          ner_logger.error(f"获取url失败{url}")
    #返回原始的url
    return url
#联系方式关键字
CONTACT_KEYS = ["手机","邮箱","电话","联系人"]
#检查是否找到了联系方式
def check_contact(_context_outtext):
    for _key in CONTACT_KEYS:
        if _key in _context_outtext:
            return "有"
    return "无" 

#检查url的类型
def check_url_type(_url,_last_url = ""):
    if is_wechat_url(_url):
        return "wxwz"
    elif is_wechat_url(_last_url):
        return "wxwz"
    return ""
#检查是否是微信的url
def is_wechat_url(_url):
    if _url.startswith("https://mp.weixin.qq.com"):
        return True
    if _url.startswith("http://mp.weixin.qq.com"):
        return True
    return False

      


#提取手机号
def extract_phone_number(text):
      phone_number_pattern = r"1[3-9]\d{9}"
      phone_numbers = re.findall(phone_number_pattern, text)
      if phone_numbers:
            phone_numbers = list(set(phone_numbers))
            return phone_numbers
      return []


#提取邮箱
def extract_email(text):
      email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
      emails = re.findall(email_pattern, text)
      if emails:
            emails = list(set(emails))
            return emails
      return []

#提取网址
def extract_url(text):
      url_pattern = r"(?:https?://)(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
      urls = re.findall(url_pattern, text)
      if urls:
            urls = list(set(urls))
            return urls
      return []
#获取长的url明细地址的带有http或者https的域名
def get_long_url_domain(url):
    url_pattern = r"(?:https?://)(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    urls = re.findall(url_pattern, url)
    if urls:
        urls = list(set(urls))
        # print(urls)
        return urls
    return []

#返回一个数字，是随机的，在3-10之间
def get_random_number():
    return random.randint(3, 10)

#获取当前日期，装换成字符创yyyymmdd 格式
def get_current_date():
    return datetime.datetime.now().strftime("%Y%m%d")   

def remove_brackets(text):
    pattern = r'^[【\[\()](.*)[\]】\)]$'
    match = re.match(pattern, text)
    if match:
        return match.group(1)
    return text

def download_file(url, max_retries=3):
    retries = 0
    while retries < max_retries:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
            }
            response = requests.get(url, stream=True, headers=headers)
            response.raise_for_status()
            headers = response.headers
            content_type = headers.get('Content-Type')
            chunks = None 
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    #二进制数据相加
                    chunks = chunk if chunks is None else chunks + chunk
            return True,chunks,{'Content-Type':content_type}
        except Exception as e:
            print(f"Download failed due to {e}. Retrying in 3 seconds...")
            retries += 1
            time.sleep(3)
    else:
        return False,None,{}
    

#获取本机的的ip地址

def get_local_ip():
    local_ips = ['127.0.0.1']
    try:
        hostname = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(hostname)[2]
        # 过滤出以 192.168 开头的IP地址
        local_ips = [ip for ip in ip_addresses if not ip.startswith("127.0")]
    except Exception as e:
        print(f"Error getting local IP: {e}")
    return " / ".join(local_ips) 

#这是日志输出
def get_logger(log_level = logging.INFO,_file = "99"):
	logpath = project_path("log")
	if not os.path.exists(logpath):
		os.mkdir(logpath)
    #按日期获取strftime("%Y%m%d")
	log_date = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    #写入文件模式
	mode = 'a'
	if get_os_info() == 'mac':
		mode = 'w'
		log_date = datetime.datetime.now().strftime("%Y%m%d")
          
	log_file = os.path.join(logpath , f'log_{str(log_level)}_{_file}_{log_date}.txt')

	logger = logging.getLogger(log_file)
	logger.setLevel(log_level)

    #追加写入日志文件
	fh = logging.FileHandler(log_file,mode=mode,encoding='UTF-8')
	#'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
	fh.setLevel(log_level)
	ch = logging.StreamHandler()
	ch.setLevel(log_level)
	formatter = logging.Formatter("%(asctime)s - %(message)s","%H:%M:%S") #- %(levelname)s
	ch.setFormatter(formatter)
	fh.setFormatter(formatter)
	logger.addHandler(ch)
	logger.addHandler(fh)
	return logger,fh,ch
#对字符串除重
def deduplicate_strings(text):
    # 按逗号分割文本
    array = re.split(r'[;，、,]', text)
    # 去除空元素
    _newstr = []
    for _r in array:
        _rr =  _r.strip()
        if _rr and not _rr in _newstr:
            _newstr.append(_rr)
    # 重新组合成文本
    return ','.join(_newstr) 
#设置为debug
def logger_debug_level():
	return ner_logger.getEffectiveLevel() == logging.DEBUG
#设置级别
def set_logger_debug(_file):
	global ner_logger,logger_fh,logger_ch
	ner_logger.setLevel(logging.DEBUG) 
	logger_fh.setLevel(logging.DEBUG)
	logger_ch.setLevel(logging.DEBUG)
	ner_logger,logger_fh,logger_ch = get_logger(logging.DEBUG,_file)
 
     
ner_logger,logger_fh,logger_ch = get_logger(logging.ERROR)
