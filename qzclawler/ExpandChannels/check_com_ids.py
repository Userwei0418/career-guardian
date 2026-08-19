import os
import re
from pathlib import Path
from collections import defaultdict
import datetime

def extract_com_numbers(directory):
    """
    从指定目录下的所有ini文件中提取com编号
    
    Args:
        directory: ini文件所在目录路径
    
    Returns:
        sorted_numbers: 排序后的com编号列表
        number_files: com编号与文件名的映射字典
    """
    
    # 存储所有找到的com编号
    com_numbers = set()
    # 存储编号与文件的映射关系
    number_files = defaultdict(list)
    
    # 正则表达式匹配 com_xxxxx 格式
    pattern = re.compile(r'com_(\d+)\s*=')
    
    # 遍历目录下所有ini文件
    ini_files = list(Path(directory).glob('*.ini'))
    
    if not ini_files:
        print(f"警告: 在 {directory} 目录下没有找到ini文件")
        return [], {}
    
    print(f"找到 {len(ini_files)} 个ini文件\n")
    
    for ini_file in ini_files:
        try:
            with open(ini_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                matches = pattern.findall(content)
                
                for match in matches:
                    com_num = int(match)
                    com_numbers.add(com_num)
                    number_files[com_num].append(ini_file.name)
        
        except Exception as e:
            print(f"读取文件 {ini_file} 时出错: {e}")
    
    # 排序
    sorted_numbers = sorted(com_numbers)
    
    return sorted_numbers, dict(number_files)


def find_available_intervals(used_ids):
    """
    通过区间合并算法，找出已用编号中的"断层（可用区间）"和"下一个安全编号"
    
    Args:
        used_ids: 已使用的编号列表
    
    Returns:
        merged_used: 已使用的连续区间列表
        available_intervals: 可用的空隙区间列表
        next_safe_id: 下一个安全的编号
    """
    if not used_ids:
        return [], [], 1

    sorted_ids = sorted(list(set(used_ids)))
    
    # 合并连续的已使用编号区间
    merged_used = []
    start = sorted_ids[0]
    end = sorted_ids[0]
    
    for num in sorted_ids[1:]:
        if num == end + 1:
            end = num
        else:
            merged_used.append((start, end))
            start = num
            end = num
    merged_used.append((start, end))
    
    # 找出可用的空隙区间
    available_intervals = []
    for i in range(len(merged_used) - 1):
        gap_start = merged_used[i][1] + 1
        gap_end = merged_used[i+1][0] - 1
        if gap_start <= gap_end:
            available_intervals.append((gap_start, gap_end))
    
    # 下一个安全的编号
    next_safe_id = merged_used[-1][1] + 1
    
    return merged_used, available_intervals, next_safe_id


def main():
    # 目录路径
    data_dir = r"D:\code\python\chu\qzclawler\data"
    
    if not os.path.exists(data_dir):
        print(f"错误: 找不到目录 {data_dir}，请检查路径。")
        return
    
    print("=" * 80)
    print("公司编号(com_xxxxx)使用情况分析")
    print("=" * 80)
    print()
    
    # 提取编号
    used_numbers, number_files = extract_com_numbers(data_dir)
    
    if not used_numbers:
        print("没有找到任何com编号")
        return
    
    # 统计信息
    print(f"已使用的编号总数: {len(used_numbers)}")
    print(f"编号范围: com_{used_numbers[0]:05d} - com_{used_numbers[-1]:05d}")
    print()
    
    # 使用区间合并算法分析
    merged_used, available_intervals, next_safe_id = find_available_intervals(used_numbers)
    
    # 显示已使用的编号段
    print("-" * 80)
    print("已使用的编号段:")
    print("-" * 80)
    
    for start, end in merged_used:
        if start == end:
            print(f"  com_{start:05d}")
        else:
            count = end - start + 1
            print(f"  com_{start:05d} - com_{end:05d}  (共 {count} 个)")
    
    print()
    
    # 显示可用范围（中间的空隙）
    print("-" * 80)
    print("🟢 中间闲置可用的编号区间:")
    print("-" * 80)
    
    if not available_intervals:
        print("  (没有断层，前面的编号是完全连续使用的)")
    else:
        for gap_start, gap_end in available_intervals:
            count = gap_end - gap_start + 1
            if gap_start == gap_end:
                print(f"  com_{gap_start:05d}")
            else:
                if count <= 20:  # 小范围详细显示
                    print(f"  com_{gap_start:05d} - com_{gap_end:05d}  (共 {count} 个) ⭐ 小间隙")
                else:
                    print(f"  com_{gap_start:05d} - com_{gap_end:05d}  (共 {count} 个)")
    
    print()
    
    # 建议下一批编号
    print("-" * 80)
    print("🚀 新加站点推荐编号（永远不冲突）:")
    print("-" * 80)
    
    print(f"  从 com_{next_safe_id:05d} 开始")
    
    # 显示接下来10个可用编号
    suggested_count = 10
    suggested = list(range(next_safe_id, next_safe_id + suggested_count))
    print(f"  建议编号: {', '.join([f'com_{num:05d}' for num in suggested])}")
    
    print()
    
    # 检查重复
    print("-" * 80)
    print("⚠️  重复使用检查:")
    print("-" * 80)
    
    duplicates_found = False
    for num, files in sorted(number_files.items()):
        if len(files) > 1:
            duplicates_found = True
            print(f"  ⚠️  com_{num:05d} 在多个文件中出现:")
            for file in files:
                print(f"      - {file}")
    
    if not duplicates_found:
        print("  ✓ 没有发现重复使用的编号")
    
    print()
    
    # 保存详细报告到文件
    report_file = os.path.join(data_dir, "com_numbers_report.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("公司编号使用详细报告\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"统计时间: {datetime.datetime.now()}\n")
        f.write(f"已使用编号总数: {len(used_numbers)}\n")
        f.write(f"编号范围: com_{used_numbers[0]:05d} - com_{used_numbers[-1]:05d}\n\n")
        
        # 已使用的区间
        f.write("已使用的编号段:\n")
        f.write("-" * 80 + "\n")
        for start, end in merged_used:
            if start == end:
                f.write(f"com_{start:05d}\n")
            else:
                count = end - start + 1
                f.write(f"com_{start:05d} - com_{end:05d}  (共 {count} 个)\n")
        f.write("\n")
        
        # 可用的区间
        f.write("中间闲置可用的编号区间:\n")
        f.write("-" * 80 + "\n")
        if not available_intervals:
            f.write("(没有断层，前面的编号是完全连续使用的)\n")
        else:
            for gap_start, gap_end in available_intervals:
                count = gap_end - gap_start + 1
                if gap_start == gap_end:
                    f.write(f"com_{gap_start:05d}\n")
                else:
                    f.write(f"com_{gap_start:05d} - com_{gap_end:05d}  (共 {count} 个)\n")
        f.write("\n")
        
        # 推荐编号
        f.write("新加站点推荐编号:\n")
        f.write("-" * 80 + "\n")
        f.write(f"从 com_{next_safe_id:05d} 开始\n\n")
        
        # 所有已使用的编号
        f.write("所有已使用的编号:\n")
        f.write("-" * 80 + "\n")
        for i, num in enumerate(used_numbers, 1):
            f.write(f"com_{num:05d}  ")
            if i % 10 == 0:
                f.write("\n")
        f.write("\n\n")
        
        # 编号与文件映射
        f.write("编号与文件映射:\n")
        f.write("-" * 80 + "\n")
        for num in sorted(number_files.keys()):
            f.write(f"com_{num:05d}: {', '.join(number_files[num])}\n")
    
    print(f"📄 详细报告已保存到: {report_file}")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()