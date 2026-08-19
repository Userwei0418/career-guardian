def crawl_page(page):
    try:
        # 查找分页容器 - 根据新的HTML结构
        paging = page.query_selector('li a[rel="next"]')
        if not paging:
            print("未找到下一页链接")
            return False

        # 检查是否是最后一页（元素是否存在且可点击）
        href = paging.get_attribute('href')
        if not href:
            print("已到最后一页")
            return False

        # 获取当前页信息（如果有的话）
        cur_page_elements = page.query_selector_all('li a[rel="next"]')
        cur_page = "unknown"

        # 尝试获取当前页码（如果页面有显示当前页的元素）
        current_page_element = page.query_selector('li a.current')  # 或其他表示当前页的选择器
        if current_page_element:
            cur_page = current_page_element.inner_text().strip()
        else:
            # 如果无法获取当前页，使用默认值
            cur_page = "current"

        print(f"当前页 {cur_page} → 尝试翻页")

        # 点击下一页链接
        paging.click()

        # 等待页面加载完成
        page.wait_for_load_state('networkidle', timeout=10000)

        # 等待页面更新 - 检查URL变化或页面内容更新
        try:
            page.wait_for_function(
                """() => {
                    // 检查页面是否已更新，例如检查新的分页元素或内容变化
                    return document.querySelector('li a[rel="next"]') !== null;
                }""",
                timeout=8000
            )
        except:
            # 如果等待超时，检查是否到达最后一页
            next_link = page.query_selector('li a[rel="next"]')
            if not next_link:
                print("已到最后一页")
                return False
            pass

        # 获取新页面的页码（如果有显示）
        new_page_element = page.query_selector('li a.current')  # 或其他表示当前页的选择器
        if new_page_element:
            new_page = new_page_element.inner_text().strip()
        else:
            # 从URL中获取页码信息
            import re
            match = re.search(r'-(\d+)\.html', page.url)
            if match:
                new_page = match.group(1)
            else:
                new_page = "new"

        print(f"翻页成功 → 当前页 {new_page}")
        return True

    except Exception as e:
        print(f"已到最后一页或翻页失败: {e}")
        return False
