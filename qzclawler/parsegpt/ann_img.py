
from PIL import Image 
from utils import ner_logger
import os
import io
import re
import sys
sys.path.append('../')
import json

from utils import ner_logger,getMD5Bytes,download_file,get_file_extension,get_md5_clear_text,getMD5Str
from utils_img import check_transparency_ratio,read_image_object,average_hash
from api.ocr_api import Paddle_OCR
from api.hwcloud_api import upload_file_to_obs
from utils_html import recombine_url
from utils_img import detect_qr_code

# 初始化 OCR 解析器
ocr_parser = Paddle_OCR()
def url_to_base64(image_url,_cache_dir): 
    #先获取图片文件
    _ok,image_content,headers = download_file(image_url)
    if not _ok:
        ner_logger.info(f"get fetch Error {image_url}")
        return 0,0,'N',{},'','',''
    _ok,image = read_image_object(image_url,image_content)
    if not _ok:
        ner_logger.info(f"read_image_object Error {image_url}")
        return 0,0,'N',{},'','',''
    # 获取图片的宽度和高度
    width, height = image.size 
    #获取图片的md5
    img_md5 = getMD5Bytes(image_content)
    #文件后缀
    _ext = get_file_ext(image_url,image)
    #文件名
    _cache_filename = f'{img_md5}_pic{_ext}'
    _cachefile = f'{_cache_dir}/{_cache_filename}'
    #将image写入本地图片文件
    with open(_cachefile, 'wb') as f:
        f.write(image_content)
    # 打印图像的宽度和高度
    ner_logger.info(f"Image size: {width}x{height},{image_url}")
    # 检查图像模式是否为 RGBA
    if image.mode == 'RGBA':
        # 将 RGBA 图像转换为 RGB 图像
        image = image.convert('RGB')
    #侦测二维码
    _qrcode = 'N'
    _props = {} 
    try:
        #如果宽和高大于64 * 64才进行识别文字 文件后缀不能为gif
        if width * height > 64 * 64:
            _qrcode,_props = detect_qr_code(_cachefile,width, height)
    except Exception as e:
        ner_logger.info(f"detect_qr_code Error {image_url}: {e}")
    _props['img_width'] = width
    _props['img_height'] = height
    _props['img_md5'] = img_md5
    _props['img_similar_md5'] = average_hash(_cachefile)
    _props['img_count'] = 1
    #进行 OCR 解析
    _props['img_ocr'] = ''
    # _base64 = base64.b64encode(image_content).decode('utf-8')
    #保留 base64的md5
    # if _qrcode in ['H','Y']:
    ner_logger.info(f"detect_qr_code:{_qrcode} / {image_url}")
    # 如果不全是二维码，则需要 进行 OCR 解析
    if _qrcode != 'Y':
        try:
            #如果宽和高大于64 * 64才进行识别文字 文件后缀不能为gif
            if width * height > 64 * 64 : #and not _cache_filename.endswith('.gif')
                ner_logger.info(f"ocr_parser.ocr_txt_new {_cachefile}")
                _ocr_text = ocr_parser.ocr_txt_new(_cachefile,width, height)
                _props['img_ocr'] = _ocr_text
        except Exception as e:
            #打印错误的具体代码行
            import traceback
            error_info = traceback.format_exc()
            ner_logger.info(f"ocr_parser.ocr_txt_new Error {image_url}: {e}\n{error_info}")
        #如果里面含有二维码，则需要提取
        if _qrcode == 'H' and has_qrcode_from_img(_props['img_ocr']):
            #提取二维码
            set_qrcode_from_img(_cachefile,_props)
    #返回
    return width, height,_qrcode,_props,_cachefile,_cache_filename,headers

#获取是否存在提取的二维码
def has_qrcode_from_img(img_ocr):
    #20250225暂时移除掉
    # for _ftext in ['扫描','投递','应聘','链接','扫一扫']:
    #     if _ftext in img_ocr:
    return True
    # return False
#获取图片的url地址链接的文件后缀
def get_file_ext(image_url,image):
    # 提取文件后缀
    _filesuffix = get_file_extension(image_url)
    if _filesuffix:
        return _filesuffix 
    ner_logger.info(f"get_file_ext Error {image_url}: {image.format}")
    # 判断图片格式
    if image.format == "WEBP":
        return ".webp"
    if image.format == "PNG":
        return ".png"
    if image.format == "JPEG":
        return ".jpg"
    if image.format == "GIF":
        return ".gif"
    # 返回默认格式,暂时只能这样了，后续发现再看这个问题
    return '.png'

#加载网页图片的实际显示大小
def get_img_real_size_config(_data):
    #获取图片的url地址链接
    if 'wx_code_file_config' in _data:
        _config_file = _data['wx_code_file_config']
        #加载json
        if os.path.exists(_config_file):
            with open(_config_file, 'r', encoding='utf-8') as f:
                _config = json.load(f)
                # ner_logger.info(f"加载图片实际大小配置文件 {_config}")
                return _config
    return {}
#获取大小
def get_img_size(_rendered_img,_url):
    _combiled_url = recombine_url(_url)
    #获取图片的url地址链接
    for kurl , size in _rendered_img.items():
        _combiled_kurl = recombine_url(kurl)
        if kurl in _url or _url in kurl or _combiled_kurl == _combiled_url:
            return True,int(float(size['rendered_width'])), int(float(size['rendered_height']))
    return False,0,0
def replace_img_urls_with_base64(spider_data,_data,soup,_props,_cache_dir):
    _props_imgs = {}
    #是否有大图文字的标记
    # has_big_img = 'N'
    #实际图片的显示大小
    _rendered_imgs = get_img_real_size_config(_data)
    #记录没有文字的图，如果多张，则移除掉，肯定是垃圾
    _multipics = {}
    #循环所有图片
    for img_tag in soup.find_all('img'):
        img_url = img_tag.get('src')
        if img_url and img_url.startswith(('http://', 'https://')):
            ner_logger.info(f"img_url: {img_url}")
            #获取图片信息
            width, height,_qrcode,_iprops,_cachefile,_cache_filename,headers = url_to_base64(img_url,_cache_dir)
            #如果图片下载错误，则返回错误
            if width *  height == 0:
                img_tag.decompose()
                continue
            intrinsic_width = width
            intrinsic_height = height
            _ok,rendered_width,rendered_height = get_img_size(_rendered_imgs,img_url)
            if _ok: 
                width = rendered_width
                height = rendered_height
                if width * height != intrinsic_width * intrinsic_height:
                    ner_logger.info(f"渲染大小: {width}x{height},图片实际大小{intrinsic_width}x{intrinsic_height},{img_url}")
            #如果这个图片的内容md5值是黑名单，则移除掉
            if spider_data.check_url_in_blacklist(_iprops['img_md5']):
                img_tag.decompose()
                ner_logger.info(f"内容检测到图片黑名单，已移除{img_url}")
                continue
            #项目的图片黑名单
            if spider_data.check_url_in_blacklist(_iprops['img_similar_md5']):
                img_tag.decompose()
                ner_logger.info(f"内容检测到图片相似的黑名单，已移除{img_url},{_iprops['img_similar_md5']}")
                continue
            #项目的图片黑名单的文本相似
            if len(_iprops['img_ocr']) > 30:
                _md5txt =  get_md5_clear_text(_iprops['img_ocr'])
                _mdtv = getMD5Str(_md5txt)
                ner_logger.info(f"内容检测到图片识别的内容相似的md5 {_mdtv}")
                if spider_data.check_md5_txt_in_blacklist(_mdtv):
                    img_tag.decompose()
                    ner_logger.info(f"内容检测到图片识别的内容相似的黑名单，已移除{img_url}")
                    continue
            #如果图片的宽和高都小于64，则移除掉
            if _qrcode == 'N' and len(_iprops['img_ocr']) < 5 and (width * height < 120 * 120 or  width < 40 and height < 500 or width < 500 and height < 40):
                img_tag.decompose()
                ner_logger.info(f"图片小于100*100,40*500,500*40,并且没有文字，移除掉{img_url}")
                continue
            #检测就业指导中心
            if _qrcode in ['H'] and width * height < 300 * 700 and probe_school_blackimg(_iprops['img_ocr']):
                img_tag.decompose()
                ner_logger.info(f"检测就业指导中心,并且文字小于30个,尺寸小于300*700，移除掉{img_url}")
                continue   
            #检测透明度超过30%，并且没有字，则移除
            if _qrcode in ['N'] and len(_iprops['img_ocr']) < 5  and check_transparency_ratio(_cachefile) :
                img_tag.decompose()
                ner_logger.info(f"检测透明度超过30%，移除掉{img_url}")
                continue
            #如果没有字，则添加
            if _qrcode == 'N' and len(_iprops['img_ocr']) < 20:
                _multipics[img_tag] = img_url         
            img_tag['q_width'] = width
            img_tag['q_height'] = height
            img_tag['q_qrcode'] = _qrcode
            img_tag['q_url'] = img_url
            #上传图片到obs
            _ok,_url = upload_file_to_obs(_cache_filename,_cachefile,headers)
            if _ok:
                # 替换 src 属性为 Base64 编码的图片
                img_tag['src'] = f"{_url}"
                #如果是二维码，增加了华为云的图片的显示大小
                if _qrcode == 'Y' and width > 100:
                    img_tag['src'] = f"{_url}?x-image-process=image/resize,m_fixed,w_{width},h_{height}"
                _iprops['qz_img_url'] = _url
                _iprops['rendered_width'] = width
                _iprops['rendered_height'] = height
                #移除文件
                #os.remove(_cachefile)
            else:
                # img_tag['src'] = f"{img_url}"
                ner_logger.info(f"使用默认的链接，上传obs失败了: {width}x{height},{img_url}")
                return False
            #设置html标签
            if img_url in _props_imgs:
                _props_imgs[img_url]['img_count'] += 1
            else:
                #循环找相似的图片
                for _k,_v in _props_imgs.items():
                    if _v['img_similar_md5'] == _iprops['img_similar_md5']:
                        _v['img_count'] += 1
                        _iprops['img_count'] += 1
                        break
                #添加图片
                _props_imgs[img_url] = _iprops
            #增加是否有最大图片的标记
            if width > 500 and height > 3000:
                _data["is_large_image"] = 'OK'
            #检查是否有大的图
            # if _qrcode in ['H','N'] and width * height > 500 * 500:
            #     has_big_img = 'Y'
    #去除没有文字的图片并且重复的
    for img_tag,img_url in _multipics.items():
        if img_url in _props_imgs and _props_imgs[img_url]['img_count'] > 1:
            img_tag.decompose()
            ner_logger.info(f"图片字小于20个，并且重复了,移除掉{img_url}")
    #设置图片
    _props["img_urls"] = _props_imgs
    #返回正确
    return True
    # _props["has_big_img"] = has_big_img
#通过写死代码方式，过滤学校就业中心的图片
def intit_blacklist():
    _blacklist = [] 
    #读取black列表
    with open("data/black_img_text.txt",encoding="utf-8") as f:
        for _line in f.read().splitlines():
            _line = _line.strip()
            if _line:
                _blacklist.append(_line.strip())
    return _blacklist 
sch_blacklist = intit_blacklist()
def probe_school_blackimg(_text):
    if len(_text) > 50:
        return False
    for _blkre in sch_blacklist:
        pattern = re.compile(_blkre)
        if re.findall(pattern, _text):
            return True
    return False

#获取图片中的二维码
def set_qrcode_from_img(_cache_file,_props): 
    _qk = None
    _qr = None
    _all_qr = {}
    for _k,_v in _props.items():
        if _k.startswith('http') and len(_props[_k]) > 0 and len(_props[_k].split(',')) == 4:
            try:
                ner_logger.info(f"set_qrcode_from_img qrcode: {_cache_file}")
                left,top,width,height = _props[_k].split(',')
                #转换为int
                left,top,width,height = int(float(left)),int(float(top)),int(float(width)),int(float(height))
                ner_logger.info(f"set_qrcode_from_img qrcode: {_props[_k]}")
                image = Image.open(_cache_file)
                # 定义截取区域的左上角坐标 (left, top) 和截取的宽度、高度 (width, height)
                # 截取图片的一部分
                cropped_image = image.crop((left, top, left + width, top + height))
                # 将截取的图片保存到字节流
                byte_arr = io.BytesIO()
                cropped_image.save(byte_arr, format='PNG')  # 可以根据需要选择不同的格式，如 JPEG
                #获取文件的pathext
                _filename = os.path.splitext(_cache_file)
                _nfilename = _filename[0] + '_qr.png'
                #byte_arr的io写入图片文件
                with open(_nfilename, 'wb') as f:
                    f.write(byte_arr.getvalue())
                #获取byte_arr的md5
                _md5 = getMD5Bytes(byte_arr.getvalue())
                _qrfilename  = f'{_md5}_qr.png'
                #上传到obs
                _ok,url = upload_file_to_obs(_qrfilename,_nfilename)
                if _ok:
                    if not _qr:
                        _qk = _k
                        _qr = url
                    _all_qr[_k] = url
                    #删除临时文件
                    os.remove(_nfilename)
                    # break
            except Exception as e:
                ner_logger.info(f"set_qrcode_from_img qrcode error: {e}")
    #赋值
    if _qk:
        _props['inside_qr_link'] = _qk 
        _props['inside_qr_pic'] = _qr 
        _props['all_qr_pics'] = _all_qr
                



