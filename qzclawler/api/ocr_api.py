# -*- coding: utf-8 -*-
# @Time    : 2023/10/23 15:40
# @Author  : chang
'''飞将ocr识别 https://github.com/PaddlePaddle/PaddleOCR/blob/release/2.7/doc/doc_ch/quickstart.md'''

from paddleocr import PaddleOCR
from PIL import Image
import os
import time
import cv2
import numpy as np

import sys
sys.path.append('../')

from utils_img import convert_gif_png
from utils import ner_logger

# Paddleocr目前支持的多语言语种可以通过修改lang参数进行切换
# 例如`ch`, `en`, `fr`, `german`, `korean`, `japan`
class Paddle_OCR():
    def __init__(self):
        self.OCR = PaddleOCR(use_angle_cls=True, lang="ch")  # need to run only once to download and load model into memory
        self.TIMENUMS=lambda :int(time.time()*1000)

    def img_cut(self,img_path,img_savepath=None,part_height=1000):#640
        '''切图，如果图比较长的话，识别会很差，切图'''
        # 打开图片
        img_text =os.path.splitext(img_path)[1] 
        if os.path.exists(img_path) :
            img = Image.open(img_path)
            # 检查图像是否为RGBA模式
            if img.mode == 'RGBA':
                # 将RGBA模式转换为RGB模式
                img = img.convert('RGB')
            # 获取图片的宽度和高度
            width, height = img.size
            if not img_savepath:
                filepath,filename=os.path.split(img_path)
                img_savepath=os.path.join(filepath,os.path.splitext(filename)[0])
                # if os.path.exists(img_savepath):
                #     img_savepath=os.path.join(filepath,os.path.splitext(filename)[0]+str(self.TIMENUMS()))
            if not os.path.exists(img_savepath):
                os.makedirs(img_savepath)
            # 分割图片
            print ("图片的总高:",height,img_savepath)
            i=0
            height_head=0
            _height=part_height
            # print("图片的总高:",_height,height,img_text)
            while  _height <= height:
                while 1:
                    # print(f"while 大小:{_height},{height}")
                    '''判断截图的地点有没有文字，判断逻辑是
                        查找图像中的连通组件 有相同的特征值或属性的像素区域，在二值化图像中，像素值只有0和1，那么就可以通过0和1的组合来确定连通组件，如果一个像素的值为0，那么和它相连的所有像素值也为0，那么这个区域就是一个连通组件
                        判断连通组件的数量是否大于3（暂定3），如果大于3，则表示该位置包含文字或其他图形'''
                    part=img.crop((0, _height-2, width,_height))#截取点向上取两个像素 (两个坐标，左上角，右下角)
                    # 修改后20250227
                    chu_img_array = np.asarray(part)
                    if chu_img_array.ndim == 2:  # 已经是灰度图
                        gray = chu_img_array
                    else:  # 彩色图才进行转换
                        gray = cv2.cvtColor(chu_img_array, cv2.COLOR_BGR2GRAY)
                    #储完成 
                    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
                    num_labels, labels = cv2.connectedComponents(thresh)
                    if num_labels <=3:
                        break
                    else:
                        _height += 4 # 向下移动2像素，暂定一个字默认32像素高度
                        if _height >= height:
                            _height =height
                            break
                        #如果三次都找不到就切了
                        if _height >= part_height + 4*20:
                            break
                #截图
                part = img.crop((0, height_head, width,_height))
                _save_path = os.path.join(img_savepath, f"{i}{img_text}")
                # print(f"截取图的大小:{_save_path},{height_head},{_height},{width}")
                part.save(_save_path)
                i +=1
                height_head = _height
                if _height ==height:
                    break
                _height +=part_height
                _height =_height  if _height < height else height
            return img_savepath,img_text
        else:
            raise Exception("file no exists")
    #判断图的大小执行不同的处理
    def ocr_txt_new(self,img_path,width = 100, height = 100): 
        #缓存的内容
        _cache_img_content = f"{img_path}.txt"
        if os.path.exists(_cache_img_content):
            with open(_cache_img_content,"r",encoding="utf-8") as f:
                return f.read()
        #特殊处理gif，使用最后一帧
        _ocr_path = img_path
        if img_path.endswith(".gif"): 
            _tmp_ocr_file = img_path[:-4]+"_gif.png"
            _ok = convert_gif_png(img_path,_tmp_ocr_file)
            if _ok:
                _ocr_path = _tmp_ocr_file
        _content = ""
        if height > 1010 and not _ocr_path.endswith(".gif"):
            _content = self.ocr_txt_1(_ocr_path)
        else:
            _content =  self.ocr_txt_one(_ocr_path)
        #写入缓存文件 
        with open(_cache_img_content,"w",encoding="utf-8") as f:
            f.write(_content)
        return _content
    #处理单个图片
    def ocr_txt_one(self,img_path):
        '''pdf或图片文字识别'''
        result = self.OCR.ocr(img_path, cls=True)
        if not result:
            return ""
        _textlist = []
        for res in result:   
            if not res:
                continue
            for line in res:
                # print(line[0],line[1][0])
                coordinate=line[0]
                # print(coordinate)
                txt=line[1][0]
                _textlist.append(txt)
        return "\n".join(_textlist)
    def ocr_txt_1(self,img_path):
        #处理有些不能处理的文件后缀
        # if img_path.endswith(".gif"):
        #     # ner_logger.info(f"OCR识别文字：跳过{img_path}")
        #     return ""

        # ner_logger.info(f"开始ocr识别{img_path}")
        '''pdf或图片文字识别'''
        filemain,_text=os.path.splitext(img_path)
        print(f"imgcut:{img_path},{_text}")
        filedir,_text=self.img_cut(img_path)
        filelist=list(os.listdir(filedir))
        filelist.sort()
        dir_list = sorted(filelist, key=lambda x: os.path.getctime(os.path.join(filedir, x)))
        filelist=[os.path.join(filedir,_f) for _f in dir_list]
        #如果为空的话，就只识别一个图片
        if len(filelist)==0:
            filelist=[img_path]
        print("imgcut列表:",filelist)
        height=0
        coordinatelist=[]
        txts=[]
        for ind,imgfile in enumerate(filelist):
            result = self.OCR.ocr(imgfile, cls=True)
            if not result:
                continue
            for res in result:
                if not res:
                    continue
                for line in res:
                    # print(line,type(line))
                    # print (line[0],line[1][0])
                    coordinate=line[0]
                    # print(coordinate)
                    txt=line[1][0]
                    if height:
                        coordinatelist.append([[i[0], i[1] + height] for i in coordinate])
                    else:
                        coordinatelist.append(coordinate)
                    txts.append(str(ind)+"###"+txt)
            if len(coordinatelist) > 0:
                height +=(coordinatelist[-1][2][1]+16)
            else:
                height += 1000 + 16
        #增加一个逻辑如果啥都没有则返回无
        if len(coordinatelist)==0 and len(txts)==0:
            return ""
        arr=np.array(coordinatelist)
        #取第二个元素转为二维数组
        # 将三维数组转换为二维数组，去每个元素里的第二个
        # print(arr)
        # print(txts)
        arr_2d = arr[:, :, 1]
        row_height= min(arr_2d[:,3]-arr_2d[:,0])#最小的行高
        # print (row_height)
        sortcoordinatelist=sorted(coordinatelist,key=lambda x:(x[0][1],x[0][0]))
        textlist=[]
        ts=[]
        lastheight=0
        for t in sortcoordinatelist:
            _txt=txts[coordinatelist.index(t)]
            # print(_txt)
            if lastheight==0:
                ts.append(((t[0][0],t[2][0]),_txt)) #把每句话横坐标的开始坐标和结束的横坐标
                lastheight=t[0][1] #每句话的高度
            elif t[0][1]-lastheight > row_height:
                ts.sort(key=lambda x:x[0][0])
                textlist.append(ts)
                ts=[((t[0][0],t[2][0]),_txt)]
                lastheight = t[0][1]
            else:
                ts.append(((t[0][0],t[2][0]),_txt))
        textlist.append(ts)        
        # head_x=min([ t[0][0] for t in textlist])
        # print(textlist)
        textall = ""
        for ind,l in enumerate(textlist):
            # print("\t".join([t[1] for t in l]))
            text = "\t".join([t[1] for t in l])
            k = text.split("###")[0]
            v = text.replace(str(k)+"###","")
            # if textall.get(k):
            #     textall[k] = textall.get(k)+v+"\n"
            # else:
            textall += v+"\n"
        #清除产生的文件
        if len(filelist) > 1:
            #获取第一个元素的文件目录
            filedir = os.path.dirname(filelist[0])
            # ner_logger.info(f"清除产生的文件{filedir} {filemain}")
            if os.path.exists(filedir):
                for f in filelist:
                    os.remove(f)
                os.rmdir(filedir)
        # print(textall)
        return textall


if __name__ == '__main__':
    img_path = r'/Users/ziguangchu/Downloads/tbc.jpeg'
    pd = Paddle_OCR()
    print (pd.ocr_txt_new(img_path,1080,3043))


