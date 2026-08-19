import os
import json
import pandas as pd
from collections import defaultdict

# ================= 配置项 =================
# 配置需要扫描的根目录及其对应的状态标签
DIR_CONFIG = {
    r"D:\work\data\data": "未处理(data)",
    r"D:\edu1": "入库成功(edu1)",
    r"D:\edu0": "入库失败(edu0)"
}

# 输出的 Excel 文件保存路径
OUTPUT_FILE = r"D:\work\data\student_statistics.xlsx"
# =========================================

def main():
    stats = {}
    
    # 核心改动：不再只记数量，而是记录该公司对应的所有来源文件
    # 格式: company_sources[公司名] = ["目录/学校/专业/xxx.json", ...]
    company_sources = defaultdict(list)
    total_parsed_jsons = 0

    print("🔍 开始扫描目录...")

    # 1. 遍历配置的多个根目录
    for base_dir, status_label in DIR_CONFIG.items():
        if not os.path.exists(base_dir):
            print(f"⚠️ 警告: 找不到目录 {base_dir}，跳过该状态的扫描。")
            continue
            
        print(f"   📂 正在扫描 [{status_label}]: {base_dir}")

        for school_name in os.listdir(base_dir):
            school_path = os.path.join(base_dir, school_name)
            if not os.path.isdir(school_path):
                continue
                
            if school_name not in stats:
                stats[school_name] = {}

            for major_name in os.listdir(school_path):
                major_path = os.path.join(school_path, major_name)
                if not os.path.isdir(major_path):
                    continue

                student_files = [f for f in os.listdir(major_path) if f.endswith('.json')]
                count = len(student_files)

                if major_name not in stats[school_name]:
                    stats[school_name][major_name] = {label: 0 for label in DIR_CONFIG.values()}
                
                stats[school_name][major_name][status_label] += count

                # ================= 读取 JSON 分析内容 =================
                for file_name in student_files:
                    file_path = os.path.join(major_path, file_name)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            total_parsed_jsons += 1
                            
                            experiences = data.get("workExperiences") or []
                            
                            # 简历内去重
                            unique_companies = set()
                            for exp in experiences:
                                company_name = exp.get("companyName")
                                if company_name:
                                    unique_companies.add(company_name.strip())
                            
                            # 记录溯源信息：构建当前简历的唯一标识符
                            source_trace = f"[{status_label}] {school_name}/{major_name}/{file_name}"
                            
                            # 将该简历的标识符追加到对应的公司下
                            for company in unique_companies:
                                company_sources[company].append(source_trace)
                                
                    except json.JSONDecodeError:
                        print(f"  ❌ JSON解析失败(文件损坏): {file_path}")
                    except Exception as e:
                        print(f"  ❌ 读取文件发生错误 {file_path}: {e}")
                # =========================================================

    # 2. 组装数据并扁平化为列表 (原逻辑)
    data = []
    if not stats:
        print("⚠️ 未在任何目录下找到数据，请检查路径配置！")
        return

    for school, majors_dict in stats.items():
        major_count = len(majors_dict)
        for major, counts in majors_dict.items():
            total_students = sum(counts.values())
            row = {"学校": school, "该校专业总数": major_count, "专业": major}
            row.update(counts)
            row["专业总人数"] = total_students
            if total_students > 0:
                data.append(row)

    # 3. 转换为 DataFrame 准备导出
    try:
        # 表1：专业统计数据
        df_stats = pd.DataFrame(data)
        if not df_stats.empty:
            df_stats.sort_values(by=["学校", "专业"], inplace=True)
            
        # 表2：公司统计数据 (加入溯源字段)
        company_data = []
        for company, sources in company_sources.items():
            company_data.append({
                "公司名称": company,
                "出现总人数": len(sources),
                # 将来源列表用换行符拼起来，方便在 Excel 里查看
                "数据源溯源 (按 Alt+Enter 换行查看)": "\n".join(sources) 
            })
            
        df_companies = pd.DataFrame(company_data)
        if not df_companies.empty:
            df_companies.sort_values(by="出现总人数", ascending=False, inplace=True)
            
        # 表3：全局数据
        df_summary = pd.DataFrame([{"总解析JSON数(总人数)": total_parsed_jsons}])

        with pd.ExcelWriter(OUTPUT_FILE) as writer:
            if not df_stats.empty:
                df_stats.to_excel(writer, sheet_name="专业统计", index=False)
            if not df_companies.empty:
                df_companies.to_excel(writer, sheet_name="公司分布", index=False)
            df_summary.to_excel(writer, sheet_name="全局汇总", index=False)
        
        print("\n✅ 统计完成！")
        print(f"📄 成功解析 JSON: {total_parsed_jsons} 份")
        print(f"🏢 提取到不重复的公司数量: {len(company_sources)} 家")
        print(f"📁 结果已保存至: {OUTPUT_FILE} (请去'公司分布'表查看苏州大学的数据源)")
        
    except PermissionError:
        print(f"\n❌ 保存失败！文件可能被占用了，请关闭 Excel 后重试。")
    except Exception as e:
        print(f"\n❌ 导出 Excel 时发生错误: {e}")

if __name__ == "__main__":
    main()