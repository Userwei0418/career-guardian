# -*- coding: utf-8 -*-
"""
TP-Link招聘页面解析与前置处理
包含：
1. 自动勾选所有招聘类型（校园/社会/实习生）
2. 累积数据解析（支持翻页）
3. 去重处理
"""
import json
import os
import time
from bs4 import BeautifulSoup


def click_all_recruitment_types(page):
    """
    前置函数：自动勾选所有招聘类型
    基于Ant Design Tree组件的准确选择器
    
    Args:
        page: Playwright page对象
    
    Returns:
        bool: 是否成功
    """
    try:
        print("\n" + "="*60)
        print("🎯 开始勾选所有招聘类型...")
        print("="*60)
        
        # 等待页面加载完成
        page.wait_for_timeout(2000)
        
        # 定义要勾选的招聘类型
        recruitment_types = ["社会招聘", "校园招聘", "实习生招聘"]
        success_count = 0
        
        for job_type in recruitment_types:
            try:
                # 精准选择器：找到对应标题的checkbox
                # 1. 先找到包含目标文本的 span.ant-tree-title
                # 2. 通过XPath向上找到父容器
                # 3. 在父容器中找到 span.ant-tree-checkbox
                
                # 方法1：使用XPath定位（推荐）
                checkbox_selector = f"//span[@class='ant-tree-title' and text()='{job_type}']/ancestor::div[contains(@class, 'ant-tree-treenode')]//span[contains(@class, 'ant-tree-checkbox')]"
                
                checkbox = page.locator(f"xpath={checkbox_selector}").first
                
                # 检查是否已经选中
                parent_div = page.locator(f"//span[@class='ant-tree-title' and text()='{job_type}']/ancestor::div[contains(@class, 'ant-tree-treenode')]").first
                
                is_checked = "ant-tree-treenode-checkbox-checked" in parent_div.get_attribute("class")
                
                if is_checked:
                    print(f"  ✓ 已经选中: {job_type}")
                    success_count += 1
                else:
                    # 点击checkbox勾选
                    checkbox.click()
                    print(f"  ✓ 成功勾选: {job_type}")
                    page.wait_for_timeout(1500)
                    
                    # 验证是否勾选成功
                    page.wait_for_timeout(500)
                    parent_div_after = page.locator(f"//span[@class='ant-tree-title' and text()='{job_type}']/ancestor::div[contains(@class, 'ant-tree-treenode')]").first
                    is_checked_after = "ant-tree-treenode-checkbox-checked" in parent_div_after.get_attribute("class")
                    
                    if is_checked_after:
                        print(f"       验证: 勾选成功 ✓")
                        success_count += 1
                    else:
                        print(f"       验证: 勾选可能失败 ✗")
                        
            except Exception as e:
                print(f"  ✗ 勾选 {job_type} 失败: {e}")
                
                # 备用方法：直接点击文本
                try:
                    print(f"     尝试备用方法...")
                    title_element = page.locator(f"span.ant-tree-title:has-text('{job_type}')").first
                    title_element.click()
                    print(f"  ✓ 备用方法成功: {job_type}")
                    page.wait_for_timeout(1500)
                    success_count += 1
                except Exception as e2:
                    print(f"  ✗ 备用方法也失败: {e2}")
        
        # 等待数据加载
        print(f"\n⏳ 等待数据刷新...")
        page.wait_for_timeout(3000)
        
        # 输出结果
        print(f"\n{'='*60}")
        if success_count == len(recruitment_types):
            print(f"✅ 成功勾选所有 {success_count} 个招聘类型")
            print(f"{'='*60}\n")
            return True
        elif success_count > 0:
            print(f"⚠️ 部分成功：勾选了 {success_count}/{len(recruitment_types)} 个类型")
            print(f"{'='*60}\n")
            return True
        else:
            print(f"❌ 未能勾选任何招聘类型")
            print(f"{'='*60}\n")
            return False
            
    except Exception as e:
        print(f"\n❌ 勾选招聘类型时发生严重错误: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        return False


def extract_table_from_html(htmlcontext, tempfile):
    """
    解析TP-Link招聘页面HTML，提取职位信息
    支持数据累积（多次调用自动合并去重）
    
    Args:
        htmlcontext: HTML内容字符串
        tempfile: 输出JSON文件路径
    
    Returns:
        bool: 是否成功解析
    """
    try:
        soup = BeautifulSoup(htmlcontext, 'html.parser')
        
        # === 1. 读取已有数据 ===
        existing_jobs = []
        existing_titles = set()  # 用于快速去重
        
        if os.path.exists(tempfile):
            try:
                with open(tempfile, 'r', encoding='utf-8') as f:
                    existing_jobs = json.load(f)
                    # 建立标题索引
                    existing_titles = {job['announcement_name'] for job in existing_jobs}
                print(f"📂 读取已有职位: {len(existing_jobs)} 个")
            except Exception as e:
                print(f"⚠️ 读取已有数据失败: {e}，将创建新文件")
                existing_jobs = []
                existing_titles = set()
        
        # === 2. 解析当前页面 ===
        expanded_items = soup.find_all("li", class_="ant-list-item")
        
        if not expanded_items:
            # 备用选择器
            expanded_items = soup.select("li[class*='ant-list-item']")
        
        if not expanded_items:
            print(f"❌ 当前页面未找到职位列表项")
            # 如果已有数据，不算失败
            if len(existing_jobs) > 0:
                print(f"ℹ️ 保留已有 {len(existing_jobs)} 个职位")
                return True
            return False
        
        print(f"🔍 找到 {len(expanded_items)} 个职位元素")
        
        # === 3. 检查页面统计信息 ===
        total_text = soup.find(string=lambda text: text and '共' in text and '岗位' in text)
        if total_text:
            import re
            match = re.search(r'共\s*(\d+)\s*岗位', total_text)
            if match:
                total_count = int(match.group(1))
                print(f"📊 页面显示共有 {total_count} 个岗位")
                
                if len(existing_jobs) >= total_count:
                    print(f"✅ 已收集 {len(existing_jobs)} 个职位，达到或超过总数")
        
        # === 4. 遍历解析职位 ===
        new_count = 0
        duplicate_count = 0
        error_count = 0
        
        for idx, item in enumerate(expanded_items, 1):
            try:
                # 提取职位标题（必需字段）
                title_elem = item.find("span", class_="acss-1r0003g")
                if not title_elem:
                    title_elem = item.select_one("span[class*='acss-1r0003g']")
                
                title = title_elem.get_text(strip=True) if title_elem else ""
                
                if not title:
                    print(f"  ⚠️ 第 {idx} 项：无标题，跳过")
                    error_count += 1
                    continue
                
                # 去重检查
                if title in existing_titles:
                    duplicate_count += 1
                    print(f"  ⏭️ 第 {idx} 项：重复职位 [{title}]")
                    continue
                
                # 提取标签信息
                labels = item.find_all("span", class_="acss-1afnczs")
                if not labels:
                    labels = item.select("span[class*='acss-1afnczs']")
                
                # 初始化字段
                recruit_type = ""
                location = ""
                category = ""
                education = ""
                num_people = ""
                job_type = ""
                publish_time = ""
                
                # 按顺序解析标签
                for i, label in enumerate(labels):
                    text = label.get_text(strip=True)
                    
                    if i == 0:
                        recruit_type = text      # 招聘类型
                    elif i == 1:
                        location = text          # 工作地点
                    elif i == 2:
                        category = text          # 职位类别
                    elif i == 3:
                        education = text         # 学历要求
                    elif i == 4:
                        num_people = text.replace("人", "").strip()  # 招聘人数
                    elif i == 5:
                        job_type = text          # 工作类型
                    elif i == 6:
                        publish_time = text.replace("发布", "").strip()  # 发布时间
                
                # 提取岗位职责（可能为空）
                responsibilities = ""
                resp_container = item.find("div", class_="acss-i5kjn8")
                if resp_container:
                    resp_title = resp_container.find("div", class_="acss-88l5jy", string="岗位职责")
                    if resp_title:
                        resp_content = resp_title.find_next_sibling("div", class_="acss-jnq6lx")
                        if resp_content:
                            responsibilities = resp_content.get_text(strip=True)
                
                # 提取任职资格（可能为空）
                qualifications = ""
                if resp_container:
                    qual_title = resp_container.find("div", class_="acss-88l5jy", string="任职资格")
                    if qual_title:
                        qual_content = qual_title.find_next_sibling("div", class_="acss-jnq6lx")
                        if qual_content:
                            qualifications = qual_content.get_text(strip=True)
                
                # 构建职位信息字典
                job_info = {
                    "announcement_name": title,
                    "publish_time": publish_time,
                    "link": "",
                    "hd_dept": "",
                    "hd_loc": location,
                    "hd_job_num": num_people,
                    "hd_job_category": category,
                    "recruit_type": recruit_type,
                    "education": education,
                    "job_type": job_type,
                    "responsibilities": responsibilities,
                    "qualifications": qualifications
                }
                
                # 添加到列表
                existing_jobs.append(job_info)
                existing_titles.add(title)
                new_count += 1
                
                # 显示解析状态
                detail_status = "📝完整" if responsibilities else "📋基础"
                print(f"  ✓ {detail_status}: {title}")
                print(f"       {recruit_type} | {location} | {category} | {num_people}人")
                
            except Exception as e:
                print(f"  ✗ 第 {idx} 项解析出错: {e}")
                error_count += 1
                continue
        
        # === 5. 保存合并后的数据 ===
        try:
            with open(tempfile, 'w', encoding='utf-8') as f:
                json.dump(existing_jobs, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"❌ 保存文件失败: {e}")
            return False
        
        # === 6. 输出统计信息 ===
        print(f"\n{'='*60}")
        print(f"📊 本次处理统计:")
        print(f"   ├─ 页面职位数: {len(expanded_items)} 个")
        print(f"   ├─ 新增职位数: {new_count} 个")
        print(f"   ├─ 重复跳过数: {duplicate_count} 个")
        print(f"   ├─ 解析错误数: {error_count} 个")
        print(f"   └─ 累计总数: {len(existing_jobs)} 个")
        print(f"💾 保存路径: {tempfile}")
        print(f"{'='*60}\n")
        
        return True
        
    except Exception as e:
        print(f"❌ 解析HTML时发生严重错误: {e}")
        import traceback
        traceback.print_exc()
        
        # 尝试保存已有数据，避免丢失
        try:
            if 'existing_jobs' in locals() and len(existing_jobs) > 0:
                with open(tempfile, 'w', encoding='utf-8') as f:
                    json.dump(existing_jobs, f, ensure_ascii=False, indent=4)
                print(f"✓ 已保存现有 {len(existing_jobs)} 个职位")
        except:
            pass
        
        return False


def gen_50431(htmlcontext, tempfile):
    """
    主函数入口（爬虫框架调用）
    
    Args:
        htmlcontext: HTML内容
        tempfile: 输出文件路径
    
    Returns:
        bool: 是否成功
    """
    return extract_table_from_html(htmlcontext, tempfile)