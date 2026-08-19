
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from PIL import Image
from io import BytesIO 
import cv2
import hashlib
import imageio
from PIL import Image
from io import BytesIO 
import numpy as np 
import zxingcpp
import base64

from utils import get_file_extension,ner_logger

default_hash_size = 8
#读取图片文件内容
def read_image_object(image_url,image_content):
    #读取图片文件内容
    try:
        #需要对svg的图进行特殊处理
        _fe = get_file_extension(image_url)
        if _fe == '.svg':
             return False,''
            # 将 SVG 转换为 PNG 图像数据
            # png_data = cairosvg.svg2png(url=image_url)
             # 将 SVG 内容编码为字节并放入 BytesIO 对象
            # svg_stream = io.BytesIO(image_content)
            # 从文件流中读取 SVG 数据并转换为 PNG 数据
            # png_data = cairosvg.svg2png(bytestring=image_content)
            #赋值到新的变量中
            # image_content = png_data
        # 将图片内容加载到 PIL 的 Image 对象中
        image = Image.open(BytesIO(image_content))
        return True,image
    except Exception as e:
        #打印错误行
        import traceback
        traceback.print_exc()
    
    return False,''
#获取图片的相似md5值
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

def check_transparency_ratio(image_path):
    try:
        # 打开图片
        image = Image.open(image_path)
        # 检查图片是否有 alpha 通道
        if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
            # 如果是调色板模式（'P'），将其转换为 RGBA 模式
            if image.mode == 'P':
                image = image.convert('RGBA')
            # 获取图片的像素数据
            pixels = image.getdata()
            # 初始化透明像素计数器和总像素数
            transparent_pixel_count = 0
            total_pixel_count = len(pixels)
            # 遍历像素数据，统计透明像素数量
            for pixel in pixels:
                if len(pixel) == 4 and pixel[3] < 255:
                    transparent_pixel_count += 1
            # 计算透明像素的比例
            transparency_ratio = transparent_pixel_count / total_pixel_count
            print(transparency_ratio)
            # 判断透明像素比例是否超过 30%
            return transparency_ratio > 0.3
        return False
    except Exception as e:
        print(f"处理图片时出错: {e}")
        return False
    
def convert_gif_png(gif_path,png_path): 
    try:
        # 直接打开本地的 GIF 文件
        image = Image.open(gif_path)
        frame = 0
        last_frame = None
        while True:
            try:
                # 移动到指定帧
                image.seek(frame)
                # 复制当前帧
                last_frame = image.copy()
                frame += 1
            except EOFError:
                # 遇到文件结束符，退出循环
                break
        if last_frame:
            # 保存最后一帧为 PNG 格式
            last_frame.save(png_path, 'PNG')
            print("The last frame has been saved as last_frame.png")
            return True
    except Exception as e:
        print(f"An error occurred: {e}")
    return False


def resize_image(image_path, scale_percent):
    # 读取图片
    image = cv2.imread(image_path)
    # 计算新的尺寸
    width = int(image.shape[1] * scale_percent / 100)
    height = int(image.shape[0] * scale_percent / 100)
    dim = (width, height)
    # 调整图片大小
    resized = cv2.resize(image, dim, interpolation=cv2.INTER_AREA)
    return resized
def detect_qr_code_scale(image_path,scale_percent):
    # 调整图片大小
    image = resize_image(image_path, scale_percent)
    decoded_objects = decode(image)
    if decoded_objects:
        return True,decoded_objects
    return False,None
#侦测二维码
def detect_qr_code_default(image_path):
    # 读取图像 
    # 打开图片
    image = Image.open(image_path)
    decoded_objects = decode(image)
    if decoded_objects:
        return True,decoded_objects
    return False,None
#zxingcpp侦测
def read_qr_with_zxing(image_path):
    image = Image.open(image_path)
    results = zxingcpp.read_barcodes(image)
    if results and len(results) > 0:
        return True,results
    return False,None
#检测图片类型是否是二维码
def detect_qr_code(image_path,width, height):
    #是否全部是二维码
    _full_qrcode = 'N'
    _props = {}
    _scale = 1
    #特殊处理gif，使用最后一帧
    _ocr_path = image_path
    if image_path.lower().endswith(".gif"): 
        _tmp_ocr_file = image_path[:-4]+"_gif.png"
        _ok = convert_gif_png(image_path,_tmp_ocr_file)
        # ner_logger.info(f'启用GIF-PNG处理{_ocr_path}{_ok}')
        if _ok:
            _ocr_path = _tmp_ocr_file
            ner_logger.info(f'完成GIF-PNG处理{_ocr_path}')
    # 将二进制内容转换为 NumPy 数组
    _ok,decoded_objects = detect_qr_code_default(_ocr_path)
    if not _ok and width * height > 1000*2000:
        ner_logger.info(f'detect_qr_code_default 没找到,启用放大2倍进行查询{_ocr_path}')
        _ok,decoded_objects = detect_qr_code_scale(_ocr_path,200)
        if _ok :
            _scale = 2
    if not _ok and width * height < 1000*1000:
        ner_logger.info(f'detect_qr_code_default 没找到,启用缩小1倍进行查询{_ocr_path}')
        _ok,decoded_objects = detect_qr_code_scale(_ocr_path,50)
        if _ok :
            _scale = 0.5
    # 判断是否检测到二维码
    if decoded_objects:
        # print("QR Code detected!")
        for obj in decoded_objects:
            qr_code_rect = obj.rect
            rect_width = qr_code_rect.width / _scale
            rect_height = qr_code_rect.height / _scale
            rect_top = qr_code_rect.top / _scale
            rect_left = qr_code_rect.left / _scale
            #QR Code data:Rect(left=25, top=25, width=294, height=294) 
            if abs(rect_width - width)/ width < 0.3 and abs(rect_height - height) / height < 0.3:
                _full_qrcode = 'Y' #整个都是
            elif _full_qrcode == 'N': 
                _full_qrcode = 'H'#部分
            _props[obj.data.decode('utf-8')] = f"{rect_left}, {rect_top}, {rect_width}, {rect_height}"
            _props['full_qr'] = f"{_full_qrcode}"
        #找到之后直接返回
        return _full_qrcode,_props
    #增加一层处理
    _ok,results =  read_qr_with_zxing(_ocr_path)
    if _ok:
        for result in results:
            # print(f"Type: {result.format}")
            # print(f"Data: {result.text}")
            # 获取二维码的边界点
            point = result.position
            if point:
                # 打印边界点坐标
                rect_left = point.top_left.x
                rect_top = point.top_left.y
                rect_width = point.top_right.x-point.top_left.x
                rect_height = point.bottom_left.y- point.top_left.y 
                if abs(rect_width - width)/ width < 0.3 and abs(rect_height - height) / height < 0.3:
                    _full_qrcode = 'Y' #整个都是
                elif _full_qrcode == 'N': 
                    _full_qrcode = 'H'#部分
                _props[obj.data.decode('utf-8')] = f"{rect_left}, {rect_top}, {rect_width}, {rect_height}"
                _props['full_qr'] = f"{_full_qrcode}"
        #找到之后直接返回
        return _full_qrcode,_props        

    # print("No QR Code detected.")
    _full_qrcode = 'N'
    #返回
    return _full_qrcode,_props

#b保存文件
def save_base64_img(_cache_file,_href):
    try:
        #保存图片到本地 
        _img_data = base64.b64decode(_href.split(",")[1])
        with open(_cache_file, 'wb') as f:
            f.write(_img_data)
            _href = f"{_cache_file}"
        ner_logger.info(f"base64的保存图片到本地 {_cache_file}")
        return True
    except Exception as e:
        ner_logger.info(f"base64的保存图片到本地 {_cache_file} 失败 {e}")
    return False