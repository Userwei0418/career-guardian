# -*- coding: utf-8 -*-
# @Time    : 2024/12/17 15:33
# @Author  : chang
from obs import ObsClient
import os

endpoint = 'http://obs.cn-north-4.myhuaweicloud.com'
obs_client = ObsClient(
    access_key_id="DTU7ZXZJBFUCO7K274JL",
    secret_access_key="vPXWwWoug8y2CKkQPtXjir9OpwA1TH965qXFSQuU",
    server=endpoint
)
#默认桶
DEFAULT_BUCKET = "quanfile"
#默认路径
DEFAULT_PATH = 'ann/test'
#默认域名
DEFAULT_URL = f'https://quanfile.obs.cn-north-4.myhuaweicloud.com/{DEFAULT_PATH}'

def upload_file_to_obs(filename, local_file_path,headers={},bucket_name=DEFAULT_BUCKET):
    try:
        obs_file_name = f'{DEFAULT_PATH}/{filename}'
        print(f"Uploading {local_file_path} to {obs_file_name} in bucket {bucket_name}")
        # 执行文件上传
        #local_file_path本地文件
        r=obs_client.putFile(bucket_name, obs_file_name, local_file_path,{},headers)
        if r.status < 300:
            print("文件上传成功！",local_file_path)
            return True,f'{DEFAULT_URL}/{filename}'
        else:
            print(r.reason,local_file_path,"上传失败")
            return False,r.reason
    except Exception as e:
        print("文件上传失败：", e)
        return False,str(e)
def upload_stream_to_obs(objectKey, content, metadata={},headers={},bucket_name=DEFAULT_BUCKET):
    try:
        # 按流执行文件上传,content 二进制流
        r=obs_client.putObject(bucket_name,objectKey,content,metadata,headers)
        if r.status <=300:
            # pass
            print("文件上传成功！",objectKey)
    except Exception as e:
        print("文件上传失败：", e,objectKey)
        return False,str(e)
    
    return True,f'{DEFAULT_URL}/{metadata["filename"]}'

if __name__ == '__main__':
    filepath = "/Users/ziguangchu/Downloads/1111.jpeg"
    #读取文件内容
    # with open(filepath,"rb") as f:
    #     content=f.read()
    #     filename = os.path.basename(filepath)
    #     _ok,url = upload_stream_to_obs(DEFAULT_PATH, f"{DEFAULT_PATH}/{filename}", content, metadata={"filename": filename})
    #     print(_ok,url)
    headers = {
        "Content-Type": "image/jpeg",
        "x-obs-acl": "public-read"
    }
    #获取文件名
    filename = os.path.basename(filepath)
    _ok,_s = upload_file_to_obs(filename,filepath,headers)
    print(_ok,_s)

    # download_file_from_obs('quanfile', f'file/{filename}')
    # with open(filename,"rb") as f:
    #     content=f.read()
    #     upload_stream_to_obs("quanfile", f"file/{filename}", content, metadata={"filename": filename})
