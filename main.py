"""AI Agent 系统 (1号机) — 程序入口"""

from database import init_database
from auth import auth_flow
from models.session import create_session, get_user_sessions
from agent import agentloop


def session_menu(user: dict) -> dict | None:
    """会话选择菜单，返回选中的会话或 None（退出）"""
    sessions = get_user_sessions(user["id"])

    print("\n" + "-" * 40)
    print("会话管理")
    print("-" * 40)

    if sessions:
        print("\n历史会话:")
        for i, s in enumerate(sessions, 1):
            print(f"  {i}. {s['title']} ({s['updated_at']})")
        print(f"\n  n. 新建会话")
        print(f"  q. 退出系统")
        choice = input("\n请选择: ").strip().lower()

        if choice == "q":
            print("再见！")
            return None
        if choice == "n":
            return create_session(user["id"])
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                return sessions[idx]
        except ValueError:
            pass
        print("无效选择，默认创建新会话")
        return create_session(user["id"])
    else:
        print("\n暂无历史会话，创建新会话...")
        return create_session(user["id"])


def main():
    # 初始化数据库
    print("正在连接数据库...")
    try:
        init_database()
        print("数据库就绪")
    except Exception as e:
        print(f"数据库连接失败: {e}")
        print("将使用无持久化模式运行（退出即丢失数据）")
        return

    # 用户认证
    user = auth_flow()

    # 主循环：会话选择 → Agent 对话 → 返回会话选择
    while True:
        session = session_menu(user)
        if session is None:
            break

        result = agentloop(user, session)
        if result != "menu":
            break


if __name__ == "__main__":
    main()
