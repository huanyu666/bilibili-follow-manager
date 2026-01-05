import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import json
import os
import sys
import time
import re
from datetime import datetime
from typing import List, Dict, Optional, Callable, Any
from bilibili_api import BilibiliAPI
from auto_login import auto_login_setup

def get_app_dir():
    """获取应用程序目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def get_data_dir():
    """获取数据存储目录"""
    data_dir = os.path.join(get_app_dir(), 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    return data_dir


class DataManager:
    """数据管理器 - 负责关注列表的获取、处理、存储和分发"""
    
    VERSION = "1.0"
    DATA_FILENAME = "following_data.json"
    BACKUP_PREFIX = "following_backup_"
    
    def __init__(self):
        self.data_dir = get_data_dir()
        self.data_file = os.path.join(self.data_dir, self.DATA_FILENAME)
        self.raw_data = []
        self.processed_data = {}
        self.observers = {}
        self.last_update = None
        self.update_count = 0
        self.load_local_data()
    
    def register_observer(self, name: str, callback: Callable):
        """注册数据观察者
        
        Args:
            name: 观察者名称
            callback: 回调函数，接收更新数据
        """
        self.observers[name] = callback
    
    def unregister_observer(self, name: str):
        """注销观察者"""
        if name in self.observers:
            del self.observers[name]
    
    def notify_observers(self, event: str, data: Any = None):
        """通知所有观察者
        
        Args:
            event: 事件类型 (data_updated, data_error, data_loading)
            data: 事件数据
        """
        for name, callback in self.observers.items():
            try:
                callback(event, data)
            except Exception as e:
                print(f"[DataManager] 观察者 {name} 处理事件失败: {e}")
    
    def process_data(self, raw_list: List[Dict]) -> Dict:
        """处理原始数据，提取各功能模块所需的结构化信息
        
        Args:
            raw_list: 原始关注列表数据
            
        Returns:
            处理后的数据结构
        """
        processed = {
            'version': self.VERSION,
            'update_time': datetime.now().isoformat(),
            'total_count': len(raw_list),
            'users': {},
            'index': {
                'by_name': {},
                'by_uid': {},
                'by_sign': {}
            },
            'statistics': {
                'name_length_stats': {},
                'sign_length_stats': {}
            }
        }
        
        for user in raw_list:
            uid = str(user.get('uid', '')) or str(user.get('mid', ''))
            uname = user.get('uname', '').strip()
            sign = user.get('sign', '').strip() if user.get('sign') else ''
            mtime = user.get('mtime', 0)
            mtime_str = user.get('mtime_str', '未知')
            
            if not uid:
                continue
            
            user_info = {
                'uid': uid,
                'uname': uname,
                'sign': sign,
                'mtime': mtime,
                'mtime_str': mtime_str,
                'face': user.get('face', ''),
                'vip': user.get('vip', {}),
                'official': user.get('official', {})
            }
            
            processed['users'][uid] = user_info
            
            name_lower = uname.lower()
            for i in range(1, min(len(name_lower) + 1, 20)):
                prefix = name_lower[:i]
                if prefix not in processed['index']['by_name']:
                    processed['index']['by_name'][prefix] = []
                processed['index']['by_name'][prefix].append(uid)
            
            uid_key = uid.lower()
            if len(uid_key) <= 20:
                for i in range(1, len(uid_key) + 1):
                    prefix = uid_key[:i]
                    if prefix not in processed['index']['by_uid']:
                        processed['index']['by_uid'][prefix] = []
                    processed['index']['by_uid'][prefix].append(uid)
            
            sign_lower = sign.lower()
            words = re.findall(r'\b\w+\b', sign_lower)
            unique_words = set(words)
            for word in unique_words:
                if len(word) >= 2:
                    if word not in processed['index']['by_sign']:
                        processed['index']['by_sign'][word] = []
                    if uid not in processed['index']['by_sign'][word]:
                        processed['index']['by_sign'][word].append(uid)
            
            name_len = len(uname)
            len_bucket = f"{name_len // 10 * 10}-{(name_len // 10 + 1) * 10 - 1}"
            if len_bucket not in processed['statistics']['name_length_stats']:
                processed['statistics']['name_length_stats'][len_bucket] = 0
            processed['statistics']['name_length_stats'][len_bucket] += 1
            
            sign_len = len(sign)
            len_bucket = f"{sign_len // 50 * 50}-{(sign_len // 50 + 1) * 50 - 1}"
            if len_bucket not in processed['statistics']['sign_length_stats']:
                processed['statistics']['sign_length_stats'][len_bucket] = 0
            processed['statistics']['sign_length_stats'][len_bucket] += 1
        
        processed['index']['by_name']['__total__'] = len(processed['index']['by_name'])
        processed['index']['by_uid']['__total__'] = len(processed['index']['by_uid'])
        processed['index']['by_sign']['__total__'] = len(processed['index']['by_sign'])
        
        return processed
    
    def save_data(self, data: Dict = None) -> bool:
        """保存数据到文件
        
        Args:
            data: 要保存的数据，如果为None则保存当前数据
            
        Returns:
            是否保存成功
        """
        try:
            save_data = data if data else self.processed_data
            
            self.create_backup()
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"[DataManager] 保存数据失败: {e}")
            return False
    
    def create_backup(self) -> bool:
        """创建数据备份
        
        Returns:
            是否备份成功
        """
        try:
            if os.path.exists(self.data_file):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_file = os.path.join(
                    self.data_dir, 
                    f"{self.BACKUP_PREFIX}{timestamp}.json"
                )
                
                with open(self.data_file, 'r', encoding='utf-8') as src:
                    with open(backup_file, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
                
                self.cleanup_old_backups(max_keep=5)
                return True
            return False
        except Exception as e:
            print(f"[DataManager] 创建备份失败: {e}")
            return False
    
    def cleanup_old_backups(self, max_keep: int = 5):
        """清理旧备份文件
        
        Args:
            max_keep: 保留的最大备份数量
        """
        try:
            backup_files = []
            for f in os.listdir(self.data_dir):
                if f.startswith(self.BACKUP_PREFIX) and f.endswith('.json'):
                    filepath = os.path.join(self.data_dir, f)
                    backup_files.append((filepath, os.path.getmtime(filepath)))
            
            backup_files.sort(key=lambda x: x[1], reverse=True)
            
            for filepath, _ in backup_files[max_keep:]:
                try:
                    os.remove(filepath)
                except:
                    pass
        except Exception as e:
            print(f"[DataManager] 清理旧备份失败: {e}")
    
    def load_local_data(self) -> bool:
        """加载本地保存的数据
        
        Returns:
            是否加载成功
        """
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.processed_data = json.load(f)
                
                self.raw_data = self.extract_raw_data()
                self.last_update = self.processed_data.get('update_time', '')
                self.update_count = self.processed_data.get('total_count', 0)
                return True
            return False
        except Exception as e:
            print(f"[DataManager] 加载本地数据失败: {e}")
            self.processed_data = {}
            self.raw_data = []
            return False
    
    def extract_raw_data(self) -> List[Dict]:
        """从处理后的数据中提取原始用户列表
        
        Returns:
            原始用户数据列表
        """
        if not self.processed_data:
            return []
        
        users = self.processed_data.get('users', {})
        return list(users.values())
    
    def get_user_by_uid(self, uid: str) -> Optional[Dict]:
        """根据UID获取用户信息
        
        Args:
            uid: 用户ID
            
        Returns:
            用户信息字典，不存在返回None
        """
        return self.processed_data.get('users', {}).get(str(uid))
    
    def search_index(self, keyword: str, search_type: str = 'name') -> List[str]:
        """使用索引快速搜索
        
        Args:
            keyword: 搜索关键词
            search_type: 搜索类型 (name, uid, sign)
            
        Returns:
            匹配的UID列表
        """
        keyword = keyword.lower().strip()
        index = self.processed_data.get('index', {}).get(f'by_{search_type}', {})
        
        if search_type == 'uid':
            if keyword in index:
                return index[keyword]
            results = []
            for prefix, uids in index.items():
                if prefix != '__total__' and keyword in prefix:
                    results.extend(uids)
            return list(set(results))
        else:
            return index.get(keyword, [])
    
    def get_statistics(self) -> Dict:
        """获取数据统计信息
        
        Returns:
            统计数据字典
        """
        return {
            'total_users': self.processed_data.get('total_count', 0),
            'last_update': self.last_update,
            'index_stats': {
                'name_prefixes': self.processed_data.get('index', {}).get('by_name', {}).get('__total__', 0),
                'uid_prefixes': self.processed_data.get('index', {}).get('by_uid', {}).get('__total__', 0),
                'sign_words': self.processed_data.get('index', {}).get('by_sign', {}).get('__total__', 0)
            },
            'name_length_dist': self.processed_data.get('statistics', {}).get('name_length_stats', {}),
            'sign_length_dist': self.processed_data.get('statistics', {}).get('sign_length_stats', {})
        }
    
    def save_following_list(self, following_list: List[Dict]) -> bool:
        """保存关注列表（用于批量操作后同步）
        
        Args:
            following_list: 关注用户列表
            
        Returns:
            是否保存成功
        """
        try:
            processed = self.process_data(following_list)
            return self.save_data(processed)
        except Exception as e:
            print(f"[DataManager] 保存关注列表失败: {e}")
            return False
    
    def clear_data(self):
        """清空所有数据"""
        try:
            self.raw_data = []
            self.processed_data = {}
            self.last_update = None
            self.update_count = 0
            
            if os.path.exists(self.data_file):
                os.remove(self.data_file)
            
            self.notify_observers('data_cleared', None)
            print("[DataManager] 数据已清空")
        except Exception as e:
            print(f"[DataManager] 清空数据失败: {e}")


class SearchService:
    """搜索服务类，提供高效的搜索功能"""
    
    def __init__(self):
        self.data = []
        self.search_history = []
        self.history_file = os.path.join(get_app_dir(), 'search_history.json')
        self.load_history()
    
    def set_data(self, data_list):
        """设置搜索数据"""
        self.data = data_list
    
    def load_history(self):
        """加载搜索历史"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.search_history = json.load(f)
        except:
            self.search_history = []
    
    def save_history(self):
        """保存搜索历史"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.search_history[-50:], f, ensure_ascii=False)
        except:
            pass
    
    def add_to_history(self, query):
        """添加搜索词到历史"""
        if query and query.strip():
            query = query.strip()
            if query in self.search_history:
                self.search_history.remove(query)
            self.search_history.insert(0, query)
            self.save_history()
    
    def get_history(self, limit=10):
        """获取搜索历史"""
        return self.search_history[:limit]
    
    def clear_history(self):
        """清空搜索历史"""
        self.search_history = []
        self.save_history()
    
    def _highlight_text(self, text, keyword, color='#FF6B6B'):
        """高亮显示关键词"""
        if not keyword or not text:
            return text
        
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        highlighted = pattern.sub(f'█{keyword}█', text)
        return highlighted
    
    def search(self, query, exact=False, page=1, page_size=20):
        """搜索用户
        
        Args:
            query: 搜索关键词
            exact: 是否精确匹配
            page: 页码
            page_size: 每页数量
            
        Returns:
            搜索结果和分页信息
        """
        if not query or not query.strip():
            return {
                'results': [],
                'total': 0,
                'page': 1,
                'page_size': page_size,
                'total_pages': 0,
                'query': ''
            }
        
        query = query.strip()
        keyword = query.lower()
        
        start_time = time.time()
        
        if exact:
            results = [
                user for user in self.data
                if (keyword in user.get('uname', '').lower() or 
                    keyword in str(user.get('uid', '')) or
                    keyword in user.get('sign', '').lower())
            ]
        else:
            keywords = keyword.split()
            results = []
            for user in self.data:
                uname = user.get('uname', '').lower()
                sign = user.get('sign', '').lower()
                uid = str(user.get('uid', ''))
                
                matched = False
                for kw in keywords:
                    if kw in uname or kw in sign or kw in uid:
                        matched = True
                        break
                
                if matched:
                    results.append(user)
        
        total = len(results)
        total_pages = (total + page_size - 1) // page_size
        page = min(page, max(1, total_pages))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_results = results[start_idx:end_idx]
        
        elapsed = (time.time() - start_time) * 1000
        
        self.add_to_history(query)
        
        return {
            'results': page_results,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'query': query,
            'elapsed': elapsed
        }


class BilibiliManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("B站关注管理器")
        self.root.geometry("968x732")
        self.root.minsize(800, 600)
    
        self.setup_theme()
        
        self.data_manager = DataManager()
        self.data_manager.register_observer('gui', self.on_data_changed)
        
        self.api = None
        self.following_list = []
        self.checked_items = {}
        self.item_data = {}
        
        self.search_service = SearchService()
        self.search_results = []
        self.current_page = 1
        self.page_size = 20
        self.is_search_mode = False
        self.search_timer = None
        
        self.update_status_var = tk.StringVar(value="就绪")
        self.loading = False
        
        self.create_widgets()
        self.setup_bindings()
        self.check_config()
        self.auto_import_data()
    
    def on_data_changed(self, event: str, data: Any):
        """数据变化回调
        
        Args:
            event: 事件类型
            data: 事件数据
        """
        if event == 'data_updated':
            self.root.after(0, lambda: self.on_following_data_updated(data))
        elif event == 'data_loading':
            self.root.after(0, lambda: self.update_status("🔄 正在加载关注列表..."))
        elif event == 'data_error':
            self.root.after(0, lambda: self.update_status(f"❌ {data}"))
        elif event == 'data_cleared':
            self.root.after(0, lambda: self.on_data_cleared())
    
    def on_data_cleared(self):
        """数据清空完成后的处理"""
        self.following_list = []
        self.search_service.set_data([])
        self.update_following_list([])
        self.update_status("✅ 所有关注已取消")
    
    def on_following_data_updated(self, processed_data: Dict):
        """关注列表数据更新完成后的处理"""
        self.following_list = self.data_manager.raw_data
        
        self.search_service.set_data(self.following_list)
        
        self.update_following_list(self.following_list)
        
        stats = self.data_manager.get_statistics()
        last_update = stats['last_update']
        if last_update:
            try:
                dt = datetime.fromisoformat(last_update)
                time_str = dt.strftime('%Y-%m-%d %H:%M')
                self.update_status(f"✅ 已加载 {stats['total_users']} 个关注用户 (更新时间: {time_str})")
            except:
                self.update_status(f"✅ 已加载 {stats['total_users']} 个关注用户")
        else:
            self.update_status("📋 已加载本地数据")
    
    def auto_import_data(self):
        """自动导入本地保存的关注列表数据"""
        if self.data_manager.processed_data:
            stats = self.data_manager.get_statistics()
            self.update_status(f"🔄 自动导入本地数据...")
            self.on_following_data_updated(self.data_manager.processed_data)
            self.update_status(f"✅ 已自动导入 {stats['total_users']} 个关注用户")
        else:
            self.update_status("📋 暂无本地数据，请点击「获取关注列表」按钮")
    
    def update_status(self, message: str):
        """更新状态栏显示
        
        Args:
            message: 状态消息
        """
        self.update_status_var.set(message)
        if hasattr(self, 'status_label'):
            pass
    
    def show_progress(self, show: bool, progress: float = 0, message: str = ""):
        """显示/隐藏进度条并更新进度
        
        Args:
            show: 是否显示进度条
            progress: 进度百分比 (0-100)
            message: 进度消息
        """
        if show:
            self.progress_var.set(progress)
            self.progress_label.config(text=message)
            self.progress_bar.pack(side=tk.RIGHT, padx=(0, 5))
            self.progress_label.pack(side=tk.RIGHT)
        else:
            self.progress_var.set(0)
            self.progress_label.config(text="")
            self.progress_bar.pack_forget()
            self.progress_label.pack_forget()
    
    def setup_bindings(self):
        """设置键盘快捷键"""
        self.root.bind('<Control-f>', lambda e: self.focus_search())
        self.root.bind('<Control-F>', lambda e: self.focus_search())
        self.root.bind('<Escape>', lambda e: self.clear_search())
        self.root.bind('<KeyPress-Delete>', lambda e: self.clear_search())
        
        self.search_entry.bind('<Return>', lambda e: self.perform_search())
        self.search_entry.bind('<Up>', self.on_history_up)
        self.search_entry.bind('<Down>', self.on_history_down)
        
        self.root.bind('<Control-l>', lambda e: self.clear_search())
    
    def setup_theme(self):
        style = ttk.Style()
        
        try:
            style.theme_use('vista')  # Windows现代主题
        except:
            style.theme_use('clam')   # 备用主题
        
        self.colors = {
            'primary': '#00A1D6',      
            'primary_dark': '#0084B4',
            'success': '#52C41A',
            'warning': '#FAAD14',
            'danger': '#FF4D4F',
            'bg_light': '#F8F9FA',
            'bg_dark': '#FFFFFF',
            'text_primary': '#262626',
            'text_secondary': '#8C8C8C',
            'border': '#D9D9D9'
        }
        
        # 配置按钮样式
        style.configure('Primary.TButton',
                       foreground='white',
                       padding=(20, 10),
                       font=('Microsoft YaHei UI', 10, 'bold'))
        
        style.map('Primary.TButton',
                 background=[('active', self.colors['primary_dark']),
                           ('!active', self.colors['primary']),
                           ('pressed', self.colors['primary_dark'])],
                 foreground=[('active', 'white'),
                           ('!active', 'white'),
                           ('pressed', 'white')])
        
        style.configure('Success.TButton',
                       padding=(15, 8),
                       font=('Microsoft YaHei UI', 9))
        
        style.configure('Danger.TButton',
                       padding=(15, 8),
                       font=('Microsoft YaHei UI', 9))
        
        # 设置根窗口背景
        self.root.configure(bg=self.colors['bg_light'])
    
    def create_widgets(self):
        # 主容器
        main_container = tk.Frame(self.root, bg=self.colors['bg_light'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 标题区域
        title_frame = tk.Frame(main_container, bg=self.colors['bg_light'])
        title_frame.pack(fill=tk.X, pady=(0, 25))
        
        title_label = tk.Label(title_frame, 
                              text="🎬 B站关注管理器", 
                              font=("Microsoft YaHei UI", 24, "bold"),
                              fg=self.colors['primary'],
                              bg=self.colors['bg_light'])
        title_label.pack()
        
        subtitle_label = tk.Label(title_frame,
                                 text="轻松管理你的B站关注列表",
                                 font=("Microsoft YaHei UI", 11),
                                 fg=self.colors['text_secondary'],
                                 bg=self.colors['bg_light'])
        subtitle_label.pack(pady=(5, 0))
        
        # 登录状态卡片
        login_card = ttk.LabelFrame(main_container, text="  登录状态  ", padding=20)
        login_card.pack(fill=tk.X, pady=(0, 20))
        
        status_frame = tk.Frame(login_card, bg=self.colors['bg_dark'])
        status_frame.pack(fill=tk.X)
        
        # 状态指示器
        self.status_indicator = tk.Label(status_frame, text="●", font=("Arial", 16), 
                                        fg=self.colors['danger'], bg=self.colors['bg_dark'])
        self.status_indicator.pack(side=tk.LEFT, padx=(0, 10))
        
        self.status_label = tk.Label(status_frame, text="未登录", 
                                    font=("Microsoft YaHei UI", 12, "bold"),
                                    fg=self.colors['text_primary'], bg=self.colors['bg_dark'])
        self.status_label.pack(side=tk.LEFT)
        
        self.login_button = tk.Button(status_frame, text="🔐 设置登录", 
                                     command=self.setup_login,
                                     bg=self.colors['primary'],
                                     fg='white',
                                     font=('Microsoft YaHei UI', 10, 'bold'),
                                     relief='flat',
                                     padx=20, pady=8,
                                     cursor='hand2',
                                     activebackground=self.colors['primary_dark'],
                                     activeforeground='white')
        self.login_button.pack(side=tk.RIGHT)
        
        self.user_info_label = tk.Label(login_card, text="", 
                                       font=("Microsoft YaHei UI", 10),
                                       fg=self.colors['text_secondary'], 
                                       bg=self.colors['bg_dark'])
        self.user_info_label.pack(anchor=tk.W, pady=(10, 0))
        
        # 操作按钮区域
        button_frame = tk.Frame(main_container, bg=self.colors['bg_light'])
        button_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.fetch_follow_button = tk.Button(button_frame, text="📥 更新关注列表", 
                                             command=self.fetch_following_async,
                                             state="disabled",
                                             bg='#1890FF',
                                             fg='white',
                                             font=('Microsoft YaHei UI', 9),
                                             relief='flat',
                                             padx=15, pady=8,
                                             cursor='hand2',
                                             activebackground='#0969CC',
                                             activeforeground='white',
                                             disabledforeground='lightgray')
        self.fetch_follow_button.pack(side=tk.LEFT, padx=(0, 15))
        
        self.batch_unfollow_button = tk.Button(button_frame, text="❌ 批量取消关注", 
                                               command=self.batch_unfollow, 
                                               state="disabled",
                                               bg=self.colors['danger'],
                                               fg='white',
                                               font=('Microsoft YaHei UI', 9),
                                               relief='flat',
                                               padx=15, pady=8,
                                               cursor='hand2',
                                               activebackground='#E6393C',
                                               activeforeground='white',
                                               disabledforeground='lightgray')
        self.batch_unfollow_button.pack(side=tk.LEFT, padx=(0, 15))
        
        self.export_button = tk.Button(button_frame, text="📥 导出所选用户", 
                                       command=self.export_list, 
                                       state="disabled",
                                       bg='#1890FF',
                                       fg='white',
                                       font=('Microsoft YaHei UI', 9),
                                       relief='flat',
                                       padx=15, pady=8,
                                       cursor='hand2',
                                       activebackground='#0969CC',
                                       activeforeground='white',
                                       disabledforeground='lightgray')
        self.export_button.pack(side=tk.LEFT, padx=(0, 15))
        
        self.import_follow_button = tk.Button(button_frame, text="📤 导入关注", 
                                             command=self.import_and_follow, 
                                             state="disabled",
                                             bg='#52C41A',
                                             fg='white',
                                             font=('Microsoft YaHei UI', 9),
                                             relief='flat',
                                             padx=15, pady=8,
                                             cursor='hand2',
                                             activebackground='#389E0D',
                                             activeforeground='white',
                                             disabledforeground='lightgray')
        self.import_follow_button.pack(side=tk.LEFT, padx=(0, 15))
        
        # 关于按钮
        self.about_button = tk.Button(button_frame, text="ℹ️ 关于", 
                                     command=self.show_about, 
                                     bg='#722ED1',
                                     fg='white',
                                     font=('Microsoft YaHei UI', 9),
                                     relief='flat',
                                     padx=15, pady=8,
                                     cursor='hand2',
                                     activebackground='#531DAB',
                                     activeforeground='white')
        self.about_button.pack(side=tk.LEFT)
        

        
        # 关注列表卡片
        list_card = ttk.LabelFrame(main_container, text="  关注列表  ", padding=15)
        list_card.pack(fill=tk.BOTH, expand=True)
        
        # 列表工具栏
        list_toolbar = tk.Frame(list_card, bg=self.colors['bg_dark'])
        list_toolbar.pack(fill=tk.X, pady=(0, 15))

                
        self.batch_check_button = tk.Button(list_toolbar, text="批量勾选", 
                                           command=self.batch_check_selected, state="disabled",
                                           bg='#F0F0F0',
                                           fg=self.colors['text_primary'],
                                           font=('Microsoft YaHei UI', 8),
                                           relief='flat',
                                           padx=12, pady=5,
                                           cursor='hand2',
                                           activebackground='#E0E0E0')
        self.batch_check_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.batch_uncheck_button = tk.Button(list_toolbar, text="批量取消勾选", 
                                           command=self.batch_uncheck_selected, state="disabled",
                                           bg='#F0F0F0',
                                           fg=self.colors['text_primary'],
                                           font=('Microsoft YaHei UI', 8),
                                           relief='flat',
                                           padx=12, pady=5,
                                           cursor='hand2',
                                           activebackground='#E0E0E0')
        self.batch_uncheck_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.select_all_button = tk.Button(list_toolbar, text="全选", 
                                           command=self.select_all, state="disabled",
                                           bg='#F0F0F0',
                                           fg=self.colors['text_primary'],
                                           font=('Microsoft YaHei UI', 8),
                                           relief='flat',
                                           padx=12, pady=5,
                                           cursor='hand2',
                                           activebackground='#E0E0E0')
        self.select_all_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.select_none_button = tk.Button(list_toolbar, text="取消全选", 
                                            command=self.select_none, state="disabled",
                                            bg='#F0F0F0',
                                            fg=self.colors['text_primary'],
                                            font=('Microsoft YaHei UI', 8),
                                            relief='flat',
                                            padx=12, pady=5,
                                            cursor='hand2',
                                            activebackground='#E0E0E0')
        self.select_none_button.pack(side=tk.LEFT)
        
        self.count_label = tk.Label(list_toolbar, text="共 0 个关注", 
                                   font=("Microsoft YaHei UI", 10),
                                   fg=self.colors['text_secondary'], 
                                   bg=self.colors['bg_dark'])
        self.count_label.pack(side=tk.RIGHT, padx=(0, 10))
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(list_toolbar, variable=self.progress_var, maximum=100, length=150)
        self.progress_label = tk.Label(list_toolbar, text="", font=("Microsoft YaHei UI", 9), fg=self.colors['text_secondary'], bg=self.colors['bg_dark'])
        
        # 搜索区域
        search_frame = tk.Frame(list_card, bg=self.colors['bg_dark'])
        search_frame.pack(fill=tk.X, pady=(0, 15))
        
        search_left = tk.Frame(search_frame, bg=self.colors['bg_dark'])
        search_left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(search_left, text="🔍 搜索:", 
                font=("Microsoft YaHei UI", 10),
                fg=self.colors['text_primary'],
                bg=self.colors['bg_dark']).pack(side=tk.LEFT, padx=(0, 5))
        
        self.search_entry = tk.Entry(search_left, 
                                    font=("Microsoft YaHei UI", 10),
                                    fg=self.colors['text_secondary'],
                                    bg='white',
                                    relief='flat',
                                    bd=2,
                                    highlightbackground=self.colors['border'],
                                    highlightthickness=1,
                                    width=35)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.search_entry.insert(0, "输入用户名、UID或签名...")
        self.search_entry.bind('<FocusIn>', self.on_search_focus_in)
        self.search_entry.bind('<FocusOut>', self.on_search_focus_out)
        
        self.search_button = tk.Button(search_left, text="搜索",
                                       command=self.perform_search,
                                       bg=self.colors['primary'],
                                       fg='white',
                                       font=('Microsoft YaHei UI', 9),
                                       relief='flat',
                                       padx=15, pady=4,
                                       cursor='hand2',
                                       activebackground=self.colors['primary_dark'])
        self.search_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.clear_search_button = tk.Button(search_left, text="清除",
                                              command=self.clear_search,
                                              bg='#F0F0F0',
                                              fg=self.colors['text_primary'],
                                              font=('Microsoft YaHei UI', 9),
                                              relief='flat',
                                              padx=12, pady=4,
                                              cursor='hand2',
                                              activebackground='#E0E0E0')
        self.clear_search_button.pack(side=tk.LEFT)
        
        # 搜索选项
        search_options = tk.Frame(search_frame, bg=self.colors['bg_dark'])
        search_options.pack(fill=tk.X, pady=(10, 0))
        
        tk.Label(search_options, text="匹配模式:", 
                font=("Microsoft YaHei UI", 9),
                fg=self.colors['text_secondary'],
                bg=self.colors['bg_dark']).pack(side=tk.LEFT, padx=(0, 5))
        
        self.match_mode = tk.StringVar(value="fuzzy")
        fuzzy_radio = tk.Radiobutton(search_options, text="模糊匹配", 
                                    variable=self.match_mode, value="fuzzy",
                                    font=("Microsoft YaHei UI", 9),
                                    fg=self.colors['text_primary'],
                                    bg=self.colors['bg_dark'],
                                    activebackground=self.colors['bg_dark'],
                                    selectcolor=self.colors['bg_dark'],
                                    command=self.perform_search)
        fuzzy_radio.pack(side=tk.LEFT, padx=(0, 15))
        
        exact_radio = tk.Radiobutton(search_options, text="精确匹配", 
                                    variable=self.match_mode, value="exact",
                                    font=("Microsoft YaHei UI", 9),
                                    fg=self.colors['text_primary'],
                                    bg=self.colors['bg_dark'],
                                    activebackground=self.colors['bg_dark'],
                                    selectcolor=self.colors['bg_dark'],
                                    command=self.perform_search)
        exact_radio.pack(side=tk.LEFT, padx=(0, 15))
        
        self.search_result_label = tk.Label(search_options, text="", 
                                           font=("Microsoft YaHei UI", 9),
                                           fg=self.colors['primary'],
                                           bg=self.colors['bg_dark'])
        self.search_result_label.pack(side=tk.RIGHT)
        
        # 分页控制
        pagination_frame = tk.Frame(search_frame, bg=self.colors['bg_dark'])
        pagination_frame.pack(fill=tk.X, pady=(10, 0))
        
        tk.Label(pagination_frame, text="每页显示:", 
                font=("Microsoft YaHei UI", 9),
                fg=self.colors['text_secondary'],
                bg=self.colors['bg_dark']).pack(side=tk.LEFT, padx=(0, 5))
        
        self.page_size_var = tk.IntVar(value=20)
        page_sizes = [10, 20, 50, 100]
        self.page_size_combo = ttk.Combobox(pagination_frame, 
                                            textvariable=self.page_size_var,
                                            values=page_sizes,
                                            width=5,
                                            state="readonly")
        self.page_size_combo.pack(side=tk.LEFT, padx=(0, 15))
        self.page_size_combo.bind('<<ComboboxSelected>>', self.on_page_size_change)
        
        self.prev_page_button = tk.Button(pagination_frame, text="◀ 上一页",
                                          command=self.prev_page,
                                          state="disabled",
                                          bg='#F0F0F0',
                                          fg=self.colors['text_primary'],
                                          font=('Microsoft YaHei UI', 9),
                                          relief='flat',
                                          padx=10, pady=3,
                                          cursor='hand2',
                                          activebackground='#E0E0E0')
        self.prev_page_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.page_label = tk.Label(pagination_frame, text="第 1 / 1 页",
                                  font=("Microsoft YaHei UI", 9),
                                  fg=self.colors['text_primary'],
                                  bg=self.colors['bg_dark'])
        self.page_label.pack(side=tk.LEFT, padx=(0, 5))
        
        self.next_page_button = tk.Button(pagination_frame, text="下一页 ▶",
                                          command=self.next_page,
                                          state="disabled",
                                          bg='#F0F0F0',
                                          fg=self.colors['text_primary'],
                                          font=('Microsoft YaHei UI', 9),
                                          relief='flat',
                                          padx=10, pady=3,
                                          cursor='hand2',
                                          activebackground='#E0E0E0')
        self.next_page_button.pack(side=tk.LEFT, padx=(0, 15))
        
        # 快捷键提示
        shortcut_text = "💡 快捷键: Ctrl+F 搜索 | Enter 确认 | Esc 清除 | Ctrl+L 清空"
        tk.Label(pagination_frame, text=shortcut_text,
                font=("Microsoft YaHei UI", 8),
                fg=self.colors['text_secondary'],
                bg=self.colors['bg_dark']).pack(side=tk.RIGHT)
        
        # 创建表格容器
        table_frame = tk.Frame(list_card, bg=self.colors['bg_dark'])
        table_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建Treeview
        columns = ("用户名", "UID", "关注时间", "签名")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="tree headings", height=15, selectmode="extended")
        
        # 设置列标题
        self.tree.heading("#0", text="✓")
        self.tree.heading("用户名", text="👤 用户名")
        self.tree.heading("UID", text="🆔 UID")
        self.tree.heading("关注时间", text="⏰ 关注时间")
        self.tree.heading("签名", text="📝 签名")
        
        # 设置列宽
        self.tree.column("#0", width=60, minwidth=60)
        self.tree.column("用户名", width=180, minwidth=150)
        self.tree.column("UID", width=120, minwidth=100)
        self.tree.column("签名", width=300, minwidth=200)
        self.tree.column("关注时间", width=160, minwidth=140)
        
        # 绑定点击事件
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)
        
        # 滚动条
        scrollbar_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar_y.set)
        
        # 布局
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 状态栏
        status_frame = tk.Frame(main_container, bg=self.colors['bg_light'], height=30)
        status_frame.pack(fill=tk.X, pady=(15, 0))
        status_frame.pack_propagate(False)
        
        self.status_bar = tk.Label(status_frame, textvariable=self.update_status_var, 
                                  font=("Microsoft YaHei UI", 10),
                                  fg=self.colors['text_secondary'],
                                  bg=self.colors['bg_light'], anchor=tk.W)
        self.status_bar.pack(fill=tk.BOTH, padx=10, pady=5)
    
    def check_config(self):
        config_path = os.path.join(get_app_dir(), 'config.json')
        if os.path.exists(config_path):
            try:
                self.api = BilibiliAPI()
                user_info = self.api.get_user_info()
                if user_info:
                    self.status_indicator.config(fg=self.colors['success'])
                    self.status_label.config(text="已登录", fg=self.colors['success'])
                    self.user_info_label.config(text=f"👋 欢迎回来，{user_info.get('uname', '未知')} (ID: {user_info.get('mid', '未知')})")
                    self.login_button.config(text="🚪 退出登录", command=self.logout, bg=self.colors['danger'])
                    self.enable_buttons()
                    self.update_status("✅ 登录成功，可以开始使用了")
                else:
                    self.status_indicator.config(fg=self.colors['warning'])
                    self.status_label.config(text="登录已过期", fg=self.colors['warning'])
                    self.login_button.config(text="🔐 设置登录", command=self.setup_login, bg=self.colors['primary'])
                    self.update_status("⚠️ 登录信息已过期，请重新设置")
            except Exception:
                self.status_indicator.config(fg=self.colors['danger'])
                self.status_label.config(text="配置错误", fg=self.colors['danger'])
                self.login_button.config(text="🔐 设置登录", command=self.setup_login, bg=self.colors['primary'])
                self.update_status("❌ 配置文件错误")
        else:
            self.login_button.config(text="🔐 设置登录", command=self.setup_login, bg=self.colors['primary'])
            self.update_status("💡 首次使用？点击\"设置登录\"开始吧")
    
    def setup_login(self):
        def login_thread():
            self.update_status("🔄 正在设置登录...")
            self.login_button.config(state="disabled")
            
            try:
                success = auto_login_setup()
                if success:
                    self.root.after(0, self.login_success)
                else:
                    self.root.after(0, self.login_failed)
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self.show_login_error(error_msg))
        
        thread = threading.Thread(target=login_thread)
        thread.daemon = True
        thread.start()
    
    def show_login_error(self, error_msg):
        self.login_button.config(state="normal")
        messagebox.showerror("❌ 登录失败", f"设置登录时出错：\n\n{error_msg}\n\n请检查：\n1. Chrome浏览器是否已安装\n2. 网络连接是否正常\n3. 是否有防火墙阻止Chrome启动")
        self.update_status("❌ 登录设置失败")
    
    def logout(self):
        """退出登录，删除配置文件"""
        # 确认退出
        if not messagebox.askyesno("🚪 确认退出", 
                                  "确定要退出登录吗？\n\n这将删除本地保存的登录信息，\n下次需要重新登录。", 
                                  icon="question"):
            return
        
        try:
            # 删除配置文件
            config_path = os.path.join(get_app_dir(), 'config.json')
            if os.path.exists(config_path):
                os.remove(config_path)
            
            # 重置API对象
            self.api = None
            
            # 重置UI状态
            self.status_indicator.config(fg=self.colors['danger'])
            self.status_label.config(text="未登录", fg=self.colors['text_primary'])
            self.user_info_label.config(text="")
            self.login_button.config(text="🔐 设置登录", command=self.setup_login, bg=self.colors['primary'])
            
            # 禁用所有功能按钮
            self.fetch_follow_button.config(state="disabled")
            self.batch_unfollow_button.config(state="disabled")
            self.export_button.config(state="disabled")
            self.import_follow_button.config(state="disabled")
            self.select_all_button.config(state="disabled")
            self.select_none_button.config(state="disabled")
            self.batch_check_button.config(state="disabled")
            self.batch_uncheck_button.config(state="disabled")
            
            # 清空关注列表
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.following_list = []
            self.count_label.config(text="共 0 个关注")
            
            # 更新状态
            self.update_status("🚪 已退出登录，点击\"设置登录\"重新开始")
            messagebox.showinfo("🎉 退出成功", "已成功退出登录！")
            
        except Exception as e:
            messagebox.showerror("❌ 错误", f"退出登录失败：{str(e)}")
            self.update_status("❌ 退出登录失败")

    def login_success(self):
        self.login_button.config(state="normal")
        messagebox.showinfo("🎉 成功", "登录设置成功！")
        self.check_config()  # 重新检查配置，更新按钮状态
    
    def login_failed(self):
        self.login_button.config(state="normal")
        messagebox.showerror("❌ 错误", "登录设置失败")
        self.update_status("❌ 登录设置失败")
    
    def enable_buttons(self):
        self.fetch_follow_button.config(state="normal")
        self.batch_unfollow_button.config(state="normal")
        self.export_button.config(state="normal")
        self.import_follow_button.config(state="normal")
        self.select_all_button.config(state="normal")
        self.select_none_button.config(state="normal")
        self.batch_check_button.config(state="normal")
        self.batch_uncheck_button.config(state="normal")
    
    def fetch_following_async(self):
        """异步获取关注列表 - 手动更新功能
        
        此方法在独立线程中执行，避免阻塞主界面
        获取完成后自动处理数据并通知所有观察者
        """
        def fetch_thread():
            if self.loading:
                self.root.after(0, lambda: messagebox.showwarning("⚠️ 提示", "数据正在加载中，请稍候..."))
                return
            
            self.loading = True
            self.root.after(0, lambda: self.fetch_follow_button.config(state="disabled"))
            self.root.after(0, lambda: self.update_status("🔄 正在获取关注列表..."))
            self.data_manager.notify_observers('data_loading', '正在从服务器获取关注列表...')
            
            try:
                if self.api is None:
                    error_msg = "请先登录以获取关注列表"
                    self.root.after(0, lambda: messagebox.showerror("❌ 错误", error_msg))
                    self.root.after(0, self.fetch_failed)
                    self.data_manager.notify_observers('data_error', error_msg)
                    return
                
                following_list = self.api.get_all_following()
                
                if not following_list:
                    self.root.after(0, lambda: messagebox.showwarning("⚠️ 提示", "关注列表为空或获取失败"))
                    self.root.after(0, self.fetch_completed)
                    return
                
                processed_data = self.data_manager.process_data(following_list)
                
                save_success = self.data_manager.save_data(processed_data)
                if save_success:
                    self.data_manager.processed_data = processed_data
                    self.data_manager.raw_data = following_list
                    self.data_manager.last_update = processed_data.get('update_time', '')
                    self.data_manager.update_count = processed_data.get('total_count', 0)
                    
                    self.root.after(0, self.fetch_success)
                    self.data_manager.notify_observers('data_updated', processed_data)
                else:
                    error_msg = "数据保存失败"
                    self.root.after(0, lambda: messagebox.showerror("❌ 错误", error_msg))
                    self.root.after(0, self.fetch_failed)
                    self.data_manager.notify_observers('data_error', error_msg)
                    
            except Exception as e:
                error_msg = f"获取关注列表失败：{str(e)}"
                self.root.after(0, lambda: messagebox.showerror("❌ 错误", error_msg))
                self.root.after(0, self.fetch_failed)
                self.data_manager.notify_observers('data_error', error_msg)
            finally:
                self.loading = False
        
        thread = threading.Thread(target=fetch_thread)
        thread.daemon = True
        thread.start()
    
    def fetch_success(self):
        """获取成功回调"""
        self.fetch_follow_button.config(state="normal")
        stats = self.data_manager.get_statistics()
        count = stats['total_users']
        self.update_status(f"✅ 成功获取 {count} 个关注用户")
        messagebox.showinfo("🎉 完成", f"成功获取 {count} 个关注用户！\n\n数据已自动保存到本地。")
    
    def fetch_failed(self):
        """获取失败回调"""
        self.fetch_follow_button.config(state="normal")
        self.update_status("❌ 获取关注列表失败")
    
    def fetch_completed(self):
        """获取完成回调（无数据）"""
        self.fetch_follow_button.config(state="normal")
        self.update_status("📋 关注列表为空")
    
    def update_following_list(self, following_list):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.following_list = following_list
        self.checked_items = {}  # 重置选中状态
        self.item_data = {}      # 重置数据映射
        
        for user in following_list:
            # 格式化时间显示
            mtime_str = user.get('mtime_str', '未知')
            
            # 获取签名，如果为空则显示默认值
            sign = user.get('sign', '').strip()
            if not sign:
                sign = '暂无签名'
            
            # 插入时设置默认为未选中
            item_id = self.tree.insert("", tk.END, text="☐", values=(
                user.get('uname', '未知'),
                user.get('uid', ''),
                mtime_str,
                sign
            ))
            self.checked_items[item_id] = False
            self.item_data[item_id] = user  # 保存完整的用户数据
        
        self.fetch_follow_button.config(state="normal")
        self.count_label.config(text=f"共 {len(following_list)} 个关注")
        self.update_status(f"✅ 已加载 {len(following_list)} 个关注用户")
    
    def select_all(self):
        for item in self.tree.get_children():
            self.checked_items[item] = True
            self.tree.item(item, text="☑")
            self.tree.selection_add(item)
    
    def select_none(self):
        for item in self.tree.get_children():
            self.checked_items[item] = False
            self.tree.item(item, text="☐")
        self.tree.selection_remove(self.tree.selection())
    
    def batch_check_selected(self):
        """批量勾选树视图中当前选中的项目"""
        selected_items = self.tree.selection()
        
        if not selected_items:
            messagebox.showinfo("提示", "请先用鼠标点击选择要勾选的行（可按住Ctrl或Shift多选）")
            return
            
        # 勾选所有选中的项
        for item in selected_items:
            self.checked_items[item] = True
            self.tree.item(item, text="☑")
        
        # 更新状态
        self.update_status(f"✅ 已批量勾选 {len(selected_items)} 个项目")
    
    def batch_uncheck_selected(self):
        """批量取消勾选树视图中当前选中的项目"""
        selected_items = self.tree.selection()
        
        if not selected_items:
            messagebox.showinfo("提示", "请先用鼠标点击选择要取消勾选的行（可按住Ctrl或Shift多选）")
            return
            
        # 取消勾选所有选中的项
        for item in selected_items:
            self.checked_items[item] = False
            self.tree.item(item, text="☐")
            # 同时从树的选择中移除（可选，根据需求决定）
            # self.tree.selection_remove(item)
        
        # 更新状态
        self.update_status(f"✅ 已批量取消勾选 {len(selected_items)} 个项目")
    
    def batch_unfollow(self):
        selected_items = [item for item, checked in self.checked_items.items() if checked]
        print(f"[DEBUG] 批量取消关注: checked_items数量={len(self.checked_items)}, 选中数量={len(selected_items)}")
        
        if not selected_items:
            messagebox.showwarning("⚠️ 警告", "请先选择要取消关注的用户")
            return
        
        count = len(selected_items)
        if not messagebox.askyesno("⚠️ 确认操作", 
                                  f"确定要取消关注 {count} 个用户吗？\n\n⚠️ 此操作不可撤销！", 
                                  icon="warning"):
            return
        
        def unfollow_thread():
            self.root.after(0, lambda: self.batch_unfollow_button.config(state="disabled"))
            self.root.after(0, lambda: self.show_progress(True, 0, f"准备取消关注 {count} 个用户..."))
            
            success_count = 0
            failed_count = 0
            removed_items = []
            
            for idx, item in enumerate(selected_items):
                try:
                    values = self.tree.item(item)['values']
                    uid_str = values[1]
                    
                    if not uid_str or uid_str == '':
                        print(f"[WARN] 用户 {values[0]} 的UID为空，跳过")
                        failed_count += 1
                        continue
                    
                    uid = int(uid_str)
                    username = values[0]
                    
                    progress_pct = (idx + 1) / count * 100
                    self.root.after(0, lambda p=progress_pct, u=username, c=idx+1, t=count: 
                                  self.show_progress(True, p, f"🔄 取消关注 ({c}/{t}): {u}"))
                    
                    if self.api and hasattr(self.api, "unfollow_user") and callable(getattr(self.api, "unfollow_user")):
                        if self.api.unfollow_user(uid):
                            success_count += 1
                            removed_items.append(item)
                        else:
                            failed_count += 1
                            print(f"[WARN] 取消关注失败: {username} (UID: {uid})")
                    else:
                        failed_count += 1
                        print("[ERROR] API对象未实现unfollow_user方法")
                
                except Exception as e:
                    failed_count += 1
                    print(f"[ERROR] 取消关注异常: {str(e)}")
            
            self.root.after(0, lambda: self.batch_unfollow_button.config(state="normal"))
            self.root.after(0, lambda: self.show_progress(False))

            if removed_items:
                remaining_users = []
                for item in self.item_data.keys():
                    if item not in removed_items:
                        user_data = self.item_data.get(item, {})
                        if user_data:
                            remaining_users.append(user_data)
                
                remaining_count = len(remaining_users)
                
                for item in removed_items:
                    current_item = item
                    self.root.after(0, lambda i=current_item: self.tree.delete(i))
                    self.root.after(0, lambda i=current_item: self.checked_items.pop(i, None))
                    self.root.after(0, lambda i=current_item: self.item_data.pop(i, None))

                self.root.after(0, lambda c=remaining_count: self.count_label.config(text=f"共 {c} 个关注"))

                if remaining_users:
                    self.root.after(0, lambda r=remaining_users: self.save_remaining_users(r))
                    self.root.after(0, lambda s=success_count, f=failed_count, c=remaining_count: 
                                  (self.update_status(f"✅ 完成！成功取消关注 {s} 个用户，失败 {f} 个，剩余 {c} 个"),
                                   self.update_following_list_local(r)))
                else:
                    self.root.after(0, lambda: self.data_manager.clear_data())
                    self.root.after(0, lambda: self.update_following_list([]))
                    self.root.after(0, lambda: self.update_status("✅ 所有关注已取消"))
            else:
                self.root.after(0, lambda: self.update_status(f"⚠️ 取关完成，但部分用户可能已在服务器端取消关注"))

            self.root.after(0, lambda s=success_count, f=failed_count: messagebox.showinfo("🎉 完成", f"成功取消关注 {s} 个用户\n失败 {f} 个用户"))
        
        thread = threading.Thread(target=unfollow_thread)
        thread.daemon = True
        thread.start()

    def save_remaining_users(self, remaining_users: list):
        """保存剩余用户数据（用于批量取关后同步）"""
        if remaining_users:
            self.data_manager.save_following_list(remaining_users)
            self.data_manager.raw_data = remaining_users
    
    def update_following_list_local(self, following_list: list):
        """本地更新关注列表（不重新从文件加载）"""
        self.following_list = following_list
        self.search_service.set_data(following_list)
    
    def export_list(self):
        selected_items = [item for item, checked in self.checked_items.items() if checked]
        if not selected_items:
            messagebox.showwarning("⚠️ 警告", "请先选择要导出的关注用户")
            return
        
        try:
            # 只导出重要的数据字段
            simplified_list = []
            for item_id in selected_items:
                # 从数据映射获取完整的用户数据
                user = self.item_data.get(item_id)
                if user:
                    simplified_user = {
                        '用户名': user.get('uname', '未知'),
                        'UID': user.get('mid', ''),
                        '关注时间': user.get('mtime_str', '未知'),
                        '关注时间戳': user.get('mtime', ''),
                        '签名': user.get('sign', '').strip() or '暂无签名',
                        '官方认证': user.get('official_verify', {}).get('desc', '') if user.get('official_verify') else '',
                        '头像链接': user.get('face', '')
                    }
                    simplified_list.append(simplified_user)
            
            localtime = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
            filename = f"bilibili_following_{localtime}_{len(simplified_list)}_users.json"
            # 将文件保存到应用程序目录
            file_path = os.path.join(get_app_dir(), filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(simplified_list, f, indent=2, ensure_ascii=False)
            
            messagebox.showinfo("🎉 成功", f"关注列表已导出到:\n{file_path}\n\n📊 已导出 {len(simplified_list)} 个用户的重要信息")
            self.update_status(f"📥 列表已导出到 {filename}")
        except Exception as e:
            messagebox.showerror("❌ 错误", f"导出失败：{str(e)}")
    
    def import_and_follow(self):
        """导入文件并显示选择界面"""
        # 选择文件
        file_path = filedialog.askopenfilename(
            title="选择要导入的关注列表文件",
            filetypes=[
                ("JSON文件", "*.json"),
                ("所有文件", "*.*")
            ],
            initialdir=get_app_dir()
        )
        
        if not file_path:
            return
        
        try:
            # 读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                user_list = json.load(f)
            
            if not isinstance(user_list, list):
                messagebox.showerror("❌ 错误", "文件格式不正确，应该是包含用户列表的JSON数组")
                return
            
            if not user_list:
                messagebox.showerror("❌ 错误", "文件中没有用户数据")
                return
            
            # 解析用户数据
            parsed_users = self.parse_user_data(user_list)
            
            if not parsed_users:
                messagebox.showerror("❌ 错误", "文件中没有找到有效的用户数据")
                return
            
            # 打开选择界面
            self.show_import_selection_window(parsed_users, file_path)
            
        except json.JSONDecodeError:
            messagebox.showerror("❌ 错误", "文件不是有效的JSON格式")
        except Exception as e:
            messagebox.showerror("❌ 错误", f"读取文件失败：{str(e)}")
    
    def parse_user_data(self, user_list):
        """解析用户数据，提取关键信息"""
        parsed_users = []
        
        for user in user_list:
            user_info = {}
            
            # 检查是否是简化版格式（中文字段名）
            if 'UID' in user:
                user_info['uid'] = user.get('UID')
                user_info['username'] = user.get('用户名', '未知用户')
                user_info['signature'] = user.get('签名', '')
                user_info['follow_time'] = user.get('关注时间', '')
            
            # 检查是否是原始格式（英文字段名）
            elif 'mid' in user:
                user_info['uid'] = user.get('mid')
                user_info['username'] = user.get('uname', '未知用户')
                user_info['signature'] = user.get('sign', '')
                user_info['follow_time'] = user.get('mtime_format', '')
            
            else:
                continue  # 跳过格式不正确的条目
            
            # 确保UID是整数
            try:
                user_info['uid'] = int(user_info['uid'])
                parsed_users.append(user_info)
            except (ValueError, TypeError):
                continue  # 跳过UID无效的条目
        
        return parsed_users
    
    def show_import_selection_window(self, users_data, file_path):
        """显示导入选择窗口"""
        # 创建新窗口
        selection_window = tk.Toplevel(self.root)
        selection_window.title("📤 选择要关注的UP主")
        selection_window.geometry("1000x800")
        selection_window.minsize(900, 700)
        selection_window.configure(bg=self.colors['bg_light'])
        
        # 设置窗口图标和居中
        selection_window.transient(self.root)
        selection_window.grab_set()
        
        # 居中显示
        selection_window.update_idletasks()
        x = (selection_window.winfo_screenwidth() // 2) - (1000 // 2)
        y = (selection_window.winfo_screenheight() // 2) - (800 // 2)
        selection_window.geometry(f"1000x800+{x}+{y}")
        
        # 主容器
        main_frame = tk.Frame(selection_window, bg=self.colors['bg_light'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 标题
        title_frame = tk.Frame(main_frame, bg=self.colors['bg_light'])
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = tk.Label(title_frame,
                              text="📤 选择要关注的UP主",
                              font=("Microsoft YaHei UI", 18, "bold"),
                              fg=self.colors['primary'],
                              bg=self.colors['bg_light'])
        title_label.pack()
        
        subtitle_label = tk.Label(title_frame,
                                 text=f"从文件 {os.path.basename(file_path)} 中找到 {len(users_data)} 个UP主",
                                 font=("Microsoft YaHei UI", 10),
                                 fg=self.colors['text_secondary'],
                                 bg=self.colors['bg_light'])
        subtitle_label.pack(pady=(5, 0))
        
        # 工具栏
        toolbar_frame = tk.Frame(main_frame, bg=self.colors['bg_light'])
        toolbar_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 左侧按钮
        left_buttons = tk.Frame(toolbar_frame, bg=self.colors['bg_light'])
        left_buttons.pack(side=tk.LEFT)
        
        select_all_btn = tk.Button(left_buttons, text="全选",
                                  command=lambda: self.selection_select_all(selection_tree, users_data),
                                  bg='#F0F0F0',
                                  fg=self.colors['text_primary'],
                                  font=('Microsoft YaHei UI', 9),
                                  relief='flat',
                                  padx=15, pady=6,
                                  cursor='hand2',
                                  activebackground='#E0E0E0')
        select_all_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        select_none_btn = tk.Button(left_buttons, text="取消全选",
                                   command=lambda: self.selection_select_none(selection_tree),
                                   bg='#F0F0F0',
                                   fg=self.colors['text_primary'],
                                   font=('Microsoft YaHei UI', 9),
                                   relief='flat',
                                   padx=15, pady=6,
                                   cursor='hand2',
                                   activebackground='#E0E0E0')
        select_none_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 统计信息
        stats_label = tk.Label(toolbar_frame,
                              text="已选择: 0 个",
                              font=("Microsoft YaHei UI", 10),
                              fg=self.colors['text_secondary'],
                              bg=self.colors['bg_light'])
        stats_label.pack(side=tk.RIGHT)
        
        # 列表框架
        list_frame = ttk.LabelFrame(main_frame, text="  UP主列表  ", padding=15)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # 创建Treeview
        tree_frame = tk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # 滚动条
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 树形视图
        selection_tree = ttk.Treeview(tree_frame,
                                     columns=("username", "uid", "signature", "follow_time"),
                                     show="tree headings",
                                     yscrollcommand=v_scrollbar.set,
                                     height=20)
        selection_tree.pack(fill=tk.BOTH, expand=True)
        
        v_scrollbar.config(command=selection_tree.yview)
        
        # 设置列标题和宽度
        selection_tree.heading("#0", text="选择", anchor=tk.W)
        selection_tree.heading("username", text="用户名", anchor=tk.W)
        selection_tree.heading("uid", text="UID", anchor=tk.W)
        selection_tree.heading("signature", text="签名", anchor=tk.W)
        selection_tree.heading("follow_time", text="关注时间", anchor=tk.W)
        
        selection_tree.column("#0", width=60, minwidth=60)
        selection_tree.column("username", width=150, minwidth=100)
        selection_tree.column("uid", width=100, minwidth=80)
        selection_tree.column("signature", width=300, minwidth=200)
        selection_tree.column("follow_time", width=150, minwidth=120)
        
        # 存储选中状态
        checked_users = {}
        
        # 填充数据
        for user in users_data:
            item_id = selection_tree.insert("", tk.END,
                                           text="☐",
                                           values=(user['username'],
                                                  user['uid'],
                                                  user['signature'][:50] + "..." if len(user['signature']) > 50 else user['signature'],
                                                  user['follow_time']))
            checked_users[item_id] = False
        
        # 点击事件处理
        def on_item_click(event):
            region = selection_tree.identify_region(event.x, event.y)
            item = selection_tree.identify_row(event.y)
            
            if item and region == "tree":
                # 切换选中状态
                checked_users[item] = not checked_users[item]
                
                if checked_users[item]:
                    selection_tree.item(item, text="☑")
                else:
                    selection_tree.item(item, text="☐")
                
                # 更新统计
                selected_count = sum(checked_users.values())
                stats_label.config(text=f"已选择: {selected_count} 个")
        
        selection_tree.bind("<Button-1>", on_item_click)
        
        # 底部按钮
        button_frame = tk.Frame(main_frame, bg=self.colors['bg_light'])
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        # 取消按钮
        cancel_btn = tk.Button(button_frame, text="❌ 取消",
                              command=selection_window.destroy,
                              bg='#F5F5F5',
                              fg=self.colors['text_primary'],
                              font=('Microsoft YaHei UI', 10),
                              relief='flat',
                              padx=20, pady=8,
                              cursor='hand2',
                              activebackground='#E8E8E8')
        cancel_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        # 确认关注按钮
        confirm_btn = tk.Button(button_frame, text="✅ 确认关注",
                               command=lambda: self.confirm_import_selection(
                                   selection_window, selection_tree, users_data, checked_users, file_path),
                               bg=self.colors['success'],
                               fg='white',
                               font=('Microsoft YaHei UI', 10, 'bold'),
                               relief='flat',
                               padx=20, pady=8,
                               cursor='hand2',
                               activebackground='#389E0D')
        confirm_btn.pack(side=tk.RIGHT)
        
        # 存储引用以便在其他方法中使用
        self.selection_tree = selection_tree
        self.selection_stats_label = stats_label
        self.selection_checked_users = checked_users
    
    def selection_select_all(self, tree, users_data):
        """全选所有用户"""
        for item in self.selection_checked_users:
            self.selection_checked_users[item] = True
            tree.item(item, text="☑")
        
        self.selection_stats_label.config(text=f"已选择: {len(users_data)} 个")
    
    def selection_select_none(self, tree):
        """取消全选"""
        for item in self.selection_checked_users:
            self.selection_checked_users[item] = False
            tree.item(item, text="☐")
        
        self.selection_stats_label.config(text="已选择: 0 个")
    
    def confirm_import_selection(self, window, tree, users_data, checked_users, file_path):
        """确认导入选择的用户"""
        # 获取选中的用户
        selected_users = []
        for i, (item_id, is_checked) in enumerate(checked_users.items()):
            if is_checked:
                selected_users.append(users_data[i])
        
        if not selected_users:
            messagebox.showwarning("⚠️ 提示", "请至少选择一个要关注的UP主")
            return
        
        # 确认操作
        if not messagebox.askyesno("🔔 确认批量关注", 
                                  f"确定要关注选中的 {len(selected_users)} 个UP主吗？\n\n"
                                  f"⚠️ 此操作将会逐个关注这些用户\n"
                                  f"⏱️ 预计需要 {len(selected_users)//10 + 1}-{len(selected_users)//5 + 1} 分钟",
                                  icon="question"):
            return
        
        # 关闭选择窗口
        window.destroy()
        
        # 提取UID列表
        uids_to_follow = [user['uid'] for user in selected_users]
        
        # 开始批量关注
        self.start_batch_follow(uids_to_follow, file_path)
    
    def start_batch_follow(self, uids_to_follow, file_path):
        """开始批量关注操作"""
        if not self.api:
            messagebox.showerror("❌ 错误", "API未初始化，请先设置登录")
            return
            
        def follow_thread():
            self.root.after(0, lambda: self.import_follow_button.config(state="disabled"))
            self.root.after(0, lambda: self.update_status("🔄 正在批量关注用户..."))
            
            success_count = 0
            failed_count = 0
            total = len(uids_to_follow)
            
            for i, uid in enumerate(uids_to_follow):
                try:
                    self.root.after(0, lambda current=i+1, total=total: 
                                  self.update_status(f"🔄 正在关注用户 ({current}/{total})..."))
                    
                    if self.api and hasattr(self.api, "follow_user") and callable(getattr(self.api, "follow_user")):
                        if self.api.follow_user(uid):
                            success_count += 1
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1
                    
                    # 避免操作过快
                    time.sleep(1.0)  # 固定延迟1秒
                    
                except Exception as e:
                    failed_count += 1
                    print(f"关注用户 {uid} 失败: {e}")  # 使用print替代logger
            
            self.root.after(0, lambda: self.import_follow_button.config(state="normal"))
            
            # 显示结果
            result_msg = f"🎉 批量关注完成！\n\n✅ 成功关注: {success_count} 个用户\n"
            if failed_count > 0:
                result_msg += f"❌ 失败: {failed_count} 个用户\n"
            result_msg += f"📁 源文件: {os.path.basename(file_path)}"
            
            self.root.after(0, lambda: messagebox.showinfo("🎉 完成", result_msg))
            self.root.after(0, lambda: self.update_status(f"✅ 批量关注完成！成功 {success_count} 个，失败 {failed_count} 个"))
            
            # 刷新关注列表
            if success_count > 0:
                self.root.after(2000, self.fetch_following_async)  # 2秒后自动刷新
        
        thread = threading.Thread(target=follow_thread)
        thread.daemon = True
        thread.start()
    
    def update_status(self, message):
        self.status_bar.config(text=message)
    
    def show_about(self):
        """显示关于对话框"""
        about_text = """
B站关注管理器 v1.0
Bilibili Follow Manager

🎬 现代化的B站关注管理工具

作者: 一懒众衫小 (Noeky)
GitHub: https://github.com/Noeky/bilibili-follow-manager
许可证: MIT License - 完全免费开源

Copyright © 2025 一懒众衫小 (Noeky)

✨ 功能特色:
• 自动登录和凭据保存
• 智能展示关注用户信息
• 批量取消关注操作
• 数据导出和导入功能

💝 如果这个项目对您有帮助，
请在GitHub上给个Star支持一下！
        """
        messagebox.showinfo("关于 B站关注管理器", about_text.strip())
        
    def on_tree_click(self, event):
        """处理树形视图的点击事件"""
        region = self.tree.identify_region(event.x, event.y)
        item = self.tree.identify_row(event.y)
        
        if not item:
            return
            
        if region == "tree":  # 只有点击在图标区域时才切换勾选状态
            # 切换选中状态
            self.toggle_check(item)
        # 其他区域的点击不处理，让Treeview默认的选择机制生效
    
    def toggle_check(self, item):
        """切换选中状态"""
        # 获取当前状态并切换
        is_checked = self.checked_items.get(item, False)
        self.checked_items[item] = not is_checked
        
        # 更新显示
        if self.checked_items[item]:
            self.tree.item(item, text="☑")
            # 如果点击选中，也添加到 Treeview 的 selection
            self.tree.selection_add(item)
        else:
            self.tree.item(item, text="☐")
            # 如果取消选中，从 selection 中移除
            self.tree.selection_remove(item)
    
    def on_search_focus_in(self, event):
        """搜索框获得焦点"""
        if self.search_entry.get() == "输入用户名、UID或签名...":
            self.search_entry.delete(0, tk.END)
            self.search_entry.config(fg=self.colors['text_primary'])
    
    def on_search_focus_out(self, event):
        """搜索框失去焦点"""
        if not self.search_entry.get().strip():
            self.search_entry.insert(0, "输入用户名、UID或签名...")
            self.search_entry.config(fg=self.colors['text_secondary'])
    
    def perform_search(self):
        """执行搜索"""
        query = self.search_entry.get().strip()
        
        if query == "输入用户名、UID或签名...":
            query = ""
        
        if not query:
            self.clear_search()
            return
        
        self.current_page = 1
        self.is_search_mode = True
        
        exact = (self.match_mode.get() == "exact")
        
        self.search_service.set_data(self.following_list)
        result = self.search_service.search(query, exact=exact, page=self.current_page, page_size=self.page_size)
        
        self.search_results = result['results']
        
        self.update_search_results(result)
        
        self.update_status(f"🔍 搜索完成: 找到 {result['total']} 个匹配结果 (耗时 {result['elapsed']:.1f}ms)")
    
    def update_search_results(self, result):
        """更新搜索结果展示"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        results = result['results']
        query = result.get('query', '').lower()
        
        for user in results:
            uname = user.get('uname', '未知')
            uid = user.get('uid', '') or user.get('mid', '')
            mtime_str = user.get('mtime_str', '未知')
            sign = user.get('sign', '').strip()
            if not sign:
                sign = '暂无签名'
            
            item_id = self.tree.insert("", tk.END, text="☐", values=(
                uname,
                uid,
                mtime_str,
                sign
            ))
            self.checked_items[item_id] = False
            self.item_data[item_id] = user
        
        self.count_label.config(text=f"搜索结果: {result['total']} 个 (第 {result['page']}/{result['total_pages']} 页)")
        
        self.page_label.config(text=f"第 {result['page']} / {result['total_pages']} 页")
        
        self.prev_page_button.config(state="normal" if result['page'] > 1 else "disabled")
        self.next_page_button.config(state="normal" if result['page'] < result['total_pages'] else "disabled")
        
        self.search_result_label.config(text=f"找到 {result['total']} 个结果")
    
    def clear_search(self):
        """清除搜索状态，恢复显示所有关注列表"""
        self.is_search_mode = False
        self.search_results = []
        self.search_entry.delete(0, tk.END)
        self.search_entry.insert(0, "输入用户名、UID或签名...")
        self.search_entry.config(fg=self.colors['text_secondary'])
        
        self.current_page = 1
        self.search_result_label.config(text="")
        
        self.update_following_list(self.following_list)
        
        self.prev_page_button.config(state="disabled")
        self.next_page_button.config(state="disabled")
        self.page_label.config(text="第 1 / 1 页")
        
        self.update_status("🔍 搜索已清除，显示所有关注")
    
    def focus_search(self):
        """聚焦到搜索框"""
        self.search_entry.focus_set()
        if self.search_entry.get() == "输入用户名、UID或签名...":
            self.search_entry.select_range(0, tk.END)
    
    history_index = -1
    
    def on_history_up(self, event):
        """历史记录向上导航"""
        if not hasattr(self, 'history_index'):
            self.history_index = -1
        
        history = self.search_service.get_history()
        if not history:
            return
        
        self.history_index = min(self.history_index + 1, len(history) - 1)
        
        if self.history_index >= 0:
            query = history[self.history_index]
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, query)
            self.search_entry.config(fg=self.colors['text_primary'])
    
    def on_history_down(self, event):
        """历史记录向下导航"""
        if not hasattr(self, 'history_index'):
            self.history_index = -1
        
        history = self.search_service.get_history()
        if not history:
            return
        
        self.history_index = max(self.history_index - 1, -1)
        
        if self.history_index >= 0:
            query = history[self.history_index]
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, query)
            self.search_entry.config(fg=self.colors['text_primary'])
        else:
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, "输入用户名、UID或签名...")
            self.search_entry.config(fg=self.colors['text_secondary'])
    
    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page -= 1
            self.execute_paged_search()
    
    def next_page(self):
        """下一页"""
        if self.is_search_mode and self.search_results:
            total = len(self.search_results) + (self.current_page - 1) * self.page_size
            if self.current_page * self.page_size < len(self.following_list) + 1000:
                self.current_page += 1
                self.execute_paged_search()
    
    def execute_paged_search(self):
        """执行分页搜索"""
        query = self.search_entry.get().strip()
        if query == "输入用户名、UID或签名...":
            query = ""
        
        if not query:
            return
        
        exact = (self.match_mode.get() == "exact")
        
        result = self.search_service.search(query, exact=exact, page=self.current_page, page_size=self.page_size)
        self.search_results = result['results']
        
        self.update_search_results(result)
        
        self.update_status(f"🔍 搜索: 第 {self.current_page} 页 (共 {result['total']} 个结果)")
    
    def on_page_size_change(self, event):
        """每页数量变化"""
        self.page_size = self.page_size_var.get()
        self.current_page = 1
        
        if self.is_search_mode:
            self.execute_paged_search()
        else:
            self.update_following_list(self.following_list)

def main():
    root = tk.Tk()
    app = BilibiliManagerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
