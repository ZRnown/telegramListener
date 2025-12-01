# main.py - 主入口程序
import asyncio
import json
import logging
from modules.bot_manager import BotManager
from modules.listener import ListenerManager
from modules.data_manager import load_data

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """主函数"""
    # 读取基础配置
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    api_id = config['api_id']
    api_hash = config['api_hash']
    bot_token = config['bot_token']
    
    # 加载数据配置
    data = load_data()
    bot_username = data.get("bot_username")
    
    # 初始化监听管理器（暂时不传 bot_client，等机器人初始化后再设置）
    listener_manager = ListenerManager(api_id, api_hash, bot_entity=None, bot_client=None)
    
    # 初始化管理机器人
    bot_manager = BotManager(api_id, api_hash, bot_token, listener_manager)
    await bot_manager.init()
    
    # 设置机器人实体和客户端
    if bot_username:
        try:
            bot_entity = await bot_manager.client.get_entity(bot_username)
            listener_manager.bot_entity = bot_entity
            listener_manager.bot_client = bot_manager.client  # 传递机器人客户端给 ListenerManager
            # logger.info(f"已设置管理机器人: {bot_username}")
        except Exception as e:
            logger.warning(f"设置管理机器人失败: {e}")
    
    # 设置机器人事件处理器
    await bot_manager.setup_handlers()
    
    # 启动所有已配置的监听
    # logger.info("正在启动已配置的监听账号...")
    await listener_manager.reload_all()
    
    logger.info("🚀 系统已启动")
    
    # 在后台运行所有监听任务
    listener_tasks = []
    for session_name, listener in listener_manager.listeners.items():
        task = asyncio.create_task(listener.run())
        listener_tasks.append(task)
        listener_manager.tasks[session_name] = task
    
    # 并发运行管理机器人（主任务）和所有监听任务
    try:
        await asyncio.gather(
            bot_manager.run(),
            *listener_tasks,
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"运行错误: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n正在关闭系统...")
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

