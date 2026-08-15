
import re 
import os
import time
from utils import ner_logger
import dateparser
import datetime

#这个包有bug，某些情况下运行极其慢，请谨慎使用
def parser_date(_text):
	try: 
		_text = re.sub('[年月日初末底中]',' ',_text)
		_date = dateparser.parse(_text,settings={'PREFER_DAY_OF_MONTH': 'first'})
		if _date:
			return True,_date
	except Exception as e:
		ner_logger.error('~~~data parser error~~~ %s %s' % (e,_text))

	return False,''
#写个日期函数，输入日期，返回是否是近两个月的区间
def is_near_month(date,_days = 180):
    now = datetime.datetime.now()
    _ok,date_time = parser_date(date)
    if not _ok:
        return False
    #进行解析处理
    try : 
        return (now - date_time).days < _days #正常4周内的职位
    except:
        print(f"日期格式不正确{date}")
    return False

dates_P_4_2_2    = re.compile(r'(?:19[3-9][0-9]|20[0-2][0-9])[年\_\.\-/ ]+(?:[0-9]{1,2})(?:[月\_\.\-/ ]+)(?:[0-9]{1,2})[日]?') 
def fix_data_format(_datestr):
    if not _datestr or _datestr == '':
        return _datestr
    #尝试使用正则表达式
    match = dates_P_4_2_2.findall(_datestr)
    # ner_logger.debug(f"fix_data_format:{_datestr}->{match}")
    if match:
        _datestr = match[0]
    #尝试使用日期解析器
    _ok, pd = parser_date(_datestr)
    ner_logger.debug(f"fix_data_format:{_datestr}->{_ok}->{pd}")
    if _ok:
        return f'{pd.year}年{pd.month}月{pd.day}日 {pd.hour}:{pd.minute}'    
    return _datestr

def fix_data_format_large(_datestr):
    if not _datestr or _datestr == '':
        return _datestr
    #尝试使用正则表达式
    match = dates_P_4_2_2.findall(_datestr)
    # ner_logger.debug(f"fix_data_format:{_datestr}->{match}")
    if match:
        _datestr = match[0]
    #尝试使用日期解析器
    _ok, pd = parser_date(_datestr)
    ner_logger.debug(f"fix_data_format:{_datestr}->{_ok}->{pd}")
    if _ok and pd.year > 2030:
        ner_logger.error(f"日期格式错误{_datestr}")
        return ""
    elif _ok:
        return f'{pd.year}年{pd.month}月{pd.day}日 {pd.hour}:{pd.minute}'    
    return _datestr

#获取aa变量文件的修改时间，跟当前时间对比，小于2分钟的返回false
def check_file_modification_time(file_path, threshold_seconds=10):
    file_time = os.path.getctime(file_path)
    #当前时间
    current_time = time.time()
    time_difference = current_time - file_time
    if time_difference < threshold_seconds:
        return True
    return False

def check_file_modification_time_old(file_path, threshold_seconds=60*60*24*10):
    file_time = os.path.getctime(file_path)
    #当前时间
    current_time = time.time()
    time_difference = current_time - file_time
    if time_difference > threshold_seconds:
        return True
    return False

#获取当前时间的字符串  y-m-d h:m:s
def get_current_time_string():
    current_time = datetime.datetime.now()
    time_string = current_time.strftime("%Y-%m-%d %H:%M:%S")
    return time_string
#获取当前时间的字符串  y-m-d h:m:s
def get_current_data():
    current_time = datetime.datetime.now()
    time_string = current_time.strftime("%Y-%m-%d")
    return time_string