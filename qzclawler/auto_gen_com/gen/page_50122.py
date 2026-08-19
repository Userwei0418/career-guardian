def crawl_page(page):
    try:
        # 查找分页容器
        paging = page.query_selector('div.flex.w-full.justify-center.py-10')
        if not paging:
            print("未找到分页区域")
            return False

        # 检查是否有可点击的下一页按钮
        next_btn = paging.query_selector('svg.lucide-chevron-right')
        if not next_btn:
            print("未找到下一页按钮")
            return False

        # 检查下一页按钮是否被禁用（到最后一页）
        parent_span = next_btn.query_selector('..')  # 获取父元素
        if parent_span and 'cursor-not-allowed' in parent_span.get_attribute('class'):
            print("已到最后一页")
            return False

        # 获取当前页码
        current_span = paging.query_selector('span.cursor-default.bg-primary')
        if current_span:
            cur_page = current_span.inner_text().strip()
        else:
            cur_page = "unknown"

        print(f"当前页 {cur_page} → 尝试翻页")

        # 点击下一页按钮
        next_btn.click()

        # 等待页面更新
        page.wait_for_timeout(1000)  # 等待1秒让页面有时间更新

        # 检查是否成功翻页 - 查找新的当前页码元素
        try:
            page.wait_for_function(
                """() => {
                    const newCurrent = document.querySelector('span.cursor-default.bg-primary');
                    return newCurrent;
                }""",
                timeout=5000
            )

            # 获取新的当前页码
            new_current_span = page.query_selector('span.cursor-default.bg-primary')
            if new_current_span:
                new_page = new_current_span.inner_text().strip()
                print(f"翻页成功 → 当前页 {new_page}")

                # 再次检查是否是最后一页（下一页按钮是否被禁用）
                next_btn_after = page.query_selector('svg.lucide-chevron-right')
                if next_btn_after:
                    parent_span_after = next_btn_after.query_selector('..')
                    if parent_span_after and 'cursor-not-allowed' in parent_span_after.get_attribute('class'):
                        print("已翻到最后一页")

                return True
        except:
            print("翻页后页面更新超时")
            return False

    except Exception as e:
        print(f"翻页失败: {e}")
        return False
