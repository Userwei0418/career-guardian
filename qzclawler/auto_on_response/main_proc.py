import time
import hashlib
import os 
import requests
from urllib.parse import urlencode 
import sys
sys.path.append('../')
import json
from utils import ner_logger
import re
from .xingye_proc import xingye_proc

#执行api处理
def on_response_proc(spider_com,page,_key, com_info,k,url,_stat):
    if _key == "com_91000":
        #打印
        # ner_logger.info("com_91000:{}".format(com_info))
        #处理
        xingye_proc(spider_com,page,_key, com_info,k,url,_stat)
    #默认返回
    return True
