"""用户认证模块 — 登录/注册 CLI 流程"""

from models.user import create_user, authenticate_user


def auth_flow() -> dict:
    """用户认证流程，返回登录成功的用户信息"""
    print("\n" + "=" * 50)
    print("欢迎使用 AI Agent 系统 (1号机)")
    print("=" * 50)

    while True:
        print("\n1. 登录")
        print("2. 注册")
        print("3. 退出")
        choice = input("\n请选择: ").strip()

        if choice == "1":
            user = _login()
            if user:
                return user
        elif choice == "2":
            _register()
        elif choice == "3":
            print("再见！")
            import sys
            sys.exit(0)
        else:
            print("无效选择，请重试")


def _login() -> dict | None:
    """登录流程"""
    print("\n--- 登录 ---")
    username = input("用户名: ").strip()
    if not username:
        print("用户名不能为空")
        return None
    password = input("密码: ").strip()
    if not password:
        print("密码不能为空")
        return None

    user = authenticate_user(username, password)
    if user:
        print(f"登录成功！欢迎回来，{user['username']}")
        return user
    else:
        print("用户名或密码错误")
        return None


def _register():
    """注册流程"""
    print("\n--- 注册 ---")
    username = input("用户名: ").strip()
    if not username:
        print("用户名不能为空")
        return
    password = input("密码: ").strip()
    if not password:
        print("密码不能为空")
        return
    confirm = input("确认密码: ").strip()
    if password != confirm:
        print("两次密码不一致")
        return

    user = create_user(username, password)
    if user:
        print(f"注册成功！欢迎，{user['username']}")
    else:
        print("用户名已存在，请换一个")
