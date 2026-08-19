def crawl_page(page):
    """
    翻页函数：针对 Ant Design (ant-pagination) 结构的下一页逻辑
    """
    try:
        # 1️⃣ 定位下一页 li 元素（包含 title="下一页"）
        next_li = page.locator('li[title="下一页"]')

        # 判断元素是否存在
        if not next_li.count():
            print("[警告] 未找到下一页按钮。")
            return False

        # 2️⃣ 检查是否禁用（aria-disabled='true' 表示不能点击）
        aria_disabled = next_li.get_attribute("aria-disabled")

        if aria_disabled == "true":
            print("[日志] 下一页按钮已禁用，爬取结束。")
            return False

        # 3️⃣ 定位内部按钮（Ant Design 实际点击的是 button）
        next_button = next_li.locator('button.ant-pagination-item-link')

        # 4️⃣ 执行点击，并等待页面加载
        next_button.click()
        page.wait_for_timeout(1500)  # 或改为 wait_for_selector()
        print("[日志] 成功点击下一页。")
        return True

    except Exception as e:
        print(f"[错误] 翻页时出现异常: {e}")
        return False
