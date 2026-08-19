import requests
from bs4 import BeautifulSoup


#根据html内容获取节点内容
def get_node_text(url, node_name):
    rsp  = requests.get(url, timeout=15)
    rsp.raise_for_status()
    soup = BeautifulSoup(rsp.text, "html.parser")
    tag  = soup.find(id=node_name)
    if tag:
        return str(tag)          # 保留完整标签 
    else: 
        return rsp.text