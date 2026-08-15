


#重新整理学历，目前的学历有错误
def fix_diploma(_list):
    nlist = []
    
    for item in _list:
        #处理部分歧义的
        if "博士研究生" in item: 
            item = item.replace("博士研究生","博士")     
             
        if "大专" in item:
            nlist.append("大专")
        if '大专' in item and  "以上" in item:
            nlist.append("大专")
            nlist.append("本科")
        if '本科' in item and  "以上" in item:
            nlist.append("本科")
            nlist.append("硕士")
        if "本科" in item:
            nlist.append("本科")
        if '硕士' in item and  "以上" in item:
            nlist.append("硕士")
            nlist.append("博士")
        elif "硕士" in item:
            nlist.append("硕士")
        
        if "MBA" in item:
            nlist.append("硕士")

        if '研究生' in item and  "以上" in item:
            nlist.append("硕士")
            nlist.append("博士")

        if "博士" in item:
            nlist.append("博士")
        if "研究生" in item:
            nlist.append("硕士")
            
        if "中专" in item :
            nlist.append("中专")
    #去除list中的重复项目
    nlist = list(set(nlist))
    return nlist

#先清除掉公告名称的特殊词语
def remove_announcement_word(_title):
    for _key in ['培训生','培训中心','培训学校']:
        _title = _title.replace(_key,'')
    return _title

# print(fix_diploma(['本科','本科以上']))
# 修复学位数据映射
def fix_diploma_data_map(item):
    if 'Degree' in item:
        need_fix = item['Degree']
        item['Degree'] = fix_diploma(need_fix)

