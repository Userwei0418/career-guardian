import cv2
import imageio
import hashlib
import numpy as np
default_hash_size = 8

from api.ocr_api import Paddle_OCR
from utils import getMD5Str,get_md5_clear_text

def average_hash(_img_file):
    try:
        #处理gif
        if _img_file.endswith('.gif'):
            return average_hash_gif(_img_file)
        #处理其他格式
        image1 = cv2.imread(_img_file)
        return average_hash_core(image1)
    except Exception as e: 
        #打印错误行
        import traceback
        traceback.print_exc()
        return ''
def average_hash_core(image1): 
    resized = cv2.resize(image1, (default_hash_size, default_hash_size))
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    avg = np.mean(gray)
    hash_value = (gray > avg).astype(int)
    # 将哈希值转换为字符串
    hash_str = ''.join(str(i) for i in hash_value.flatten())
    md5_1 = hashlib.md5(hash_str.encode()).hexdigest()
    #返回md5值
    return md5_1         

def average_hash_gif(_img_file):    
    gif = imageio.get_reader(_img_file)
    for frame in gif:
        return average_hash_core(frame)
    return ''
import os

bb = '/Users/ziguangchu/source/python/qzclawler/data/black_img_md5.txt'
with open(bb,encoding="utf-8") as f:
    black_img_md5_list = f.read().splitlines()
cc = '/Users/ziguangchu/source/python/qzclawler/data/black_img_md5_content.txt'
with open(cc,encoding="utf-8") as f:
    black_img_md5_list_c = f.read().splitlines()

#新的md5
new_md5_list = []
new_md5_list_text = []
new_md5_list_multi = []
#循环目录
aa = "/Users/ziguangchu/Downloads/gj"
for root, dirs, files in os.walk(aa):
    for file in files:
        #获取文件的最后目录
        _dir = os.path.basename(root)
        if _dir.endswith('_pic'):
            print(f"跳过目录：{file_path}")
            continue
        #获取文件extension
        file_ext = os.path.splitext(file)[1]
        print(file_ext)  
        if file_ext in ['.png','.webp','.jpg','.jpeg','.gif']:
            file_path = os.path.join(root, file)
            txt_file_path = f"{file_path}.txt"
            print(file_path)
            md5_1 = average_hash(file_path)
            #处理md5
            if md5_1 in black_img_md5_list:
                print(f"已存在[{file_path}]{md5_1}")
            else:
                new_md5_list.append(md5_1)
                print(f"图片md5新增：{file}{md5_1}")
            
            #是否存在文件
            _ntext  = '' 
            if os.path.exists(txt_file_path):
                #获取内容
                with open(txt_file_path, 'r', encoding='utf-8') as f:
                    _nntext = f.read()
                    if len(_nntext) > 30: 
                        _ntext = _nntext
            #处理识别
            if not _ntext:
                try:
                    pd = Paddle_OCR()
                    _text  = pd.ocr_txt_new(file_path,1080,3043)
                    _nntext = _text
                    if len(_nntext) > 30: 
                        print(_ntext)
                        #写入文件
                        with open(txt_file_path, 'w', encoding='utf-8') as f:
                            f.write(_text)
                        _ntext = _nntext
                except Exception as e:
                    print("err:",e,file_path)
            #获取文本的md5 
            _ntext = get_md5_clear_text(_ntext)
            md5_2 = getMD5Str(_ntext)
            if md5_2 in black_img_md5_list_c:
                print(f"已存在文本md5：[{file_path}]：{md5_2} {_ntext}")
            else:
                new_md5_list_text.append(md5_2)
                print(f"文本md5新增：{file}  {_ntext}")

#打印输出***
print("新的md5:")
for md5_1 in list(set(new_md5_list)):
    print(md5_1)

print("新的md5 text:")
for md5_1 in list(set(new_md5_list_text)):
    print(md5_1)
