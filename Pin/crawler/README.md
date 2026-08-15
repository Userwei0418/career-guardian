### 学校爬虫开始了
2024-12-16日

###安装检测二维码的图片
export DYLD_LIBRARY_PATH=$(brew --prefix zbar)/lib:$DYLD_LIBRARY_PATH

#支持二维码需要个程序
https://zbar.sourceforge.net/download.html
https://www.microsoft.com/zh-cn/download/details.aspx?id=40784


学校：https://www.hljbys.org.cn/school?mark=hhdu&target=_blank
     哈尔滨华德学院就业指导服务中心  18945101783

你好


vue的无法爬取

sch_00805 = [
           {
            "sch_name":"黑龙江省人力资源和社会保障厅",
            "sch_webname":"黑龙江省人力资源和社会保障厅",
            "urls":{
                    "k1":"http://gkzp.renshenet.org.cn/index?selected=zpxx"
            },
            "pre_open_url":"http://gkzp.renshenet.org.cn/home",
            "table_func_name":"click_00088",
            "click_type" : "current",
            "table_selector":"div.el-card__body",
            "table_selectors":"div.el-card__body",
            "detail_selector":"div.zpdetail",
            "detail_selectors":"div.zpdetail", 
            "func_name":"gen_00088",
            "detail_rm_classes":"",
            "detail_rm_ids":"",
            "json_domain":"http://gkzp.renshenet.org.cn"
           }
           ]