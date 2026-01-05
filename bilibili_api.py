import requests
import json
import time
import os
import sys
import random
import threading
from typing import List, Dict, Optional
from datetime import datetime
import logging

def get_app_dir():
    """获取应用程序目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

class AntiAntiControl:
    """反风控管理器 - 模拟真实用户行为模式"""
    
    _lock = threading.Lock()
    _last_request_time = {}
    
    def __init__(self):
        self.min_delay_ms = 1000
        self.max_delay_ms = 2000
        self.max_retries = 3
        self.base_backoff_ms = 1000
        self.request_interval_lock = threading.Lock()
        self.last_request_timestamp = 0
    
    def get_random_delay(self) -> float:
        """获取随机延迟时间（毫秒）
        
        Returns:
            延迟时间（秒）
        """
        return random.uniform(self.min_delay_ms / 1000, self.max_delay_ms / 1000)
    
    def get_jitter(self) -> float:
        """获取随机抖动时间
        
        Returns:
            抖动时间（秒）
        """
        return random.uniform(0, 0.5)
    
    def get_exponential_backoff(self, attempt: int) -> float:
        """获取指数退避延迟
        
        Args:
            attempt: 重试次数
            
        Returns:
            退避时间（秒）
        """
        backoff = self.base_backoff_ms * (2 ** attempt) / 1000
        jitter = random.uniform(0, backoff * 0.3)
        return backoff + jitter
    
    def check_request_interval(self) -> float:
        """检查请求间隔，确保不超过频率限制
        
        Returns:
            需要等待的时间（秒）
        """
        with self.request_interval_lock:
            current_time = time.time()
            min_interval = self.min_delay_ms / 1000
            elapsed = current_time - self.last_request_timestamp
            
            if elapsed < min_interval:
                wait_time = min_interval - elapsed + random.uniform(0, 0.3)
                return wait_time
            
            return 0
    
    def before_request(self):
        """请求前处理：确保请求间隔和随机延迟"""
        wait_time = self.check_request_interval()
        if wait_time > 0:
            time.sleep(wait_time)
        
        delay = self.get_random_delay()
        time.sleep(delay)
        
        with self.request_interval_lock:
            self.last_request_timestamp = time.time()
    
    def after_request(self):
        """请求后处理：添加随机抖动"""
        jitter = self.get_jitter()
        time.sleep(jitter)
    
    def should_retry(self, attempt: int, error_code: int = None) -> bool:
        """判断是否应该重试
        
        Args:
            attempt: 当前重试次数
            error_code: 错误代码
            
        Returns:
            是否应该重试
        """
        if attempt >= self.max_retries:
            return False
        
        if error_code in [-352, 412, 500, 502, 503, 504]:
            return True
        
        return error_code is not None
    
    def get_retry_delay(self, attempt: int, error_code: int = None) -> float:
        """获取重试延迟时间
        
        Args:
            attempt: 当前重试次数
            error_code: 错误代码
            
        Returns:
            延迟时间（秒）
        """
        if error_code in [-352, 412]:
            return self.get_exponential_backoff(attempt) * 1.5
        
        return self.get_exponential_backoff(attempt)


class BilibiliAPI:
    """Bilibili API 客户端 - 集成反风控策略"""
    
    def __init__(self, config_path: str = "config.json"):
        """初始化 API 客户端
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = os.path.join(get_app_dir(), config_path)
        self.session = requests.Session()
        self.config = self._load_config(self.config_path)
        self._setup_session()
        self.anti_control = AntiAntiControl()
        
        logging.basicConfig(
            level=logging.INFO, 
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('app.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
                if 'anti_control' not in config:
                    config['anti_control'] = {
                        'enabled': True,
                        'min_delay_ms': 2000,
                        'max_delay_ms': 5000,
                        'max_retries': 3,
                        'base_backoff_ms': 1000
                    }
                
                return config
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件 {config_path} 不存在，请先设置登录")
        except json.JSONDecodeError:
            raise ValueError(f"配置文件 {config_path} 格式错误")
    
    def _setup_session(self):
        """设置会话"""
        self.session.cookies.update(self.config['cookies'])
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        })
    
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """发送请求并处理重试 - 集成反风控策略
        
        Args:
            method: HTTP方法
            url: 请求URL
            **kwargs: 其他请求参数
            
        Returns:
            响应对象
        """
        if not self.config.get('anti_control', {}).get('enabled', True):
            return self.session.request(method, url, **kwargs)
        
        anti_control = self.anti_control
        max_retries = self.config['anti_control'].get('max_retries', 3)
        
        for attempt in range(max_retries + 1):
            try:
                anti_control.before_request()
                response = self.session.request(method, url, **kwargs)
                anti_control.after_request()
                
                if response.status_code == 200:
                    data = response.json()
                    code = data.get('code', -1)
                    
                    if code == 0:
                        return response
                    elif code in [-352, 412]:
                        self.logger.warning(f"请求被限制 (错误码: {code})，尝试重试...")
                        if anti_control.should_retry(attempt + 1, code):
                            delay = anti_control.get_retry_delay(attempt, code)
                            self.logger.info(f"等待 {delay:.2f} 秒后重试...")
                            time.sleep(delay)
                            continue
                    elif code == 22013:
                        return response
                    else:
                        self.logger.warning(f"请求返回错误 (code: {code}): {data.get('message', '未知错误')}")
                        
                elif response.status_code in [412, 429]:
                    self.logger.warning(f"请求被限制 (HTTP {response.status_code})，等待更长时间...")
                    delay = anti_control.get_exponential_backoff(attempt) * 2
                    time.sleep(delay)
                    continue
                else:
                    self.logger.warning(f"请求失败，状态码: {response.status_code}")
                    
            except requests.RequestException as e:
                self.logger.warning(f"请求异常: {e}")
                if attempt < max_retries:
                    delay = anti_control.get_retry_delay(attempt)
                    self.logger.info(f"等待 {delay:.2f} 秒后重试...")
                    time.sleep(delay)
                    continue
            
            if attempt < max_retries:
                delay = anti_control.get_retry_delay(attempt)
                self.logger.info(f"重试第 {attempt + 1} 次，等待 {delay:.2f} 秒...")
                time.sleep(delay)
        
        raise Exception(f"请求失败，已重试 {max_retries} 次")
    
    def get_following_list(self, pn: int = 1, ps: int = 50) -> Dict:
        """获取关注列表
        
        Args:
            pn: 页码
            ps: 每页数量
            
        Returns:
            关注列表数据
        """
        url = "https://api.bilibili.com/x/relation/followings"
        params = {
            'vmid': self.config['cookies']['DedeUserID'],
            'pn': pn,
            'ps': ps,
            'order': 'desc'
        }
        
        response = self._make_request('GET', url, params=params)
        data = response.json()
        
        if data['code'] != 0:
            raise Exception(f"获取关注列表失败: {data['message']}")
        
        return data['data']
    

    def get_all_following(self) -> List[Dict]:
        """获取所有关注用户
        
        Returns:
            所有关注用户列表
        """
        if not self.config.get('anti_control', {}).get('enabled', True):
            return self._get_all_following_legacy()
        
        all_following = []
        pn = 1
        ps = min(self.config['settings']['batch_size'], 50)
        
        self.logger.info("开始获取关注列表（反风控模式）...")
        
        while True:
            try:
                data = self.get_following_list(pn, ps)
                following_list = data.get('list', [])
                
                if not following_list:
                    break
                
                for user in following_list:
                    if 'mtime' in user and user['mtime']:
                        try:
                            import datetime
                            mtime = datetime.datetime.fromtimestamp(user['mtime'])
                            user['mtime_str'] = mtime.strftime('%Y-%m-%d %H:%M')
                        except:
                            user['mtime_str'] = '未知'
                    else:
                        user['mtime_str'] = '未知'
                
                all_following.extend(following_list)
                self.logger.info(f"已获取 {len(all_following)} 个关注用户")
                
                if len(following_list) < ps:
                    break
                
                pn += 1
                
                delay = self.anti_control.get_random_delay()
                jitter = self.anti_control.get_jitter()
                total_delay = delay + jitter
                self.logger.debug(f"页间延迟: {total_delay:.2f} 秒")
                time.sleep(total_delay)
                
            except Exception as e:
                self.logger.error(f"获取关注列表失败: {e}")
                break
        
        self.logger.info(f"总共获取到 {len(all_following)} 个关注用户")
        return all_following
    
    def _get_all_following_legacy(self) -> List[Dict]:
        """旧版获取所有关注用户（无反风控）"""
        all_following = []
        pn = 1
        ps = self.config['settings']['batch_size']
        
        while True:
            data = self.get_following_list(pn, ps)
            following_list = data.get('list', [])
            if not following_list:
                break
            all_following.extend(following_list)
            if len(following_list) < ps:
                break
            pn += 1
            time.sleep(self.config['settings']['delay_between_requests'])
        
        return all_following
    
    def follow_user(self, fid: int) -> bool:
        """关注用户
        
        Args:
            fid: 用户ID
            
        Returns:
            是否成功
        """
        if self.config['settings'].get('test_mode', False):
            time.sleep(random.uniform(0.1, 0.3))
            return True
        
        url = "https://api.bilibili.com/x/relation/modify"
        data = {
            'fid': fid,
            'act': 1,
            'csrf': self.config['cookies']['bili_jct']
        }
        
        try:
            self.anti_control.before_request()
            response = self.session.post(url, data=data)
            self.anti_control.after_request()
            
            result = response.json()
            
            if result['code'] == 0:
                return True
            elif result['code'] == 22013:
                self.logger.warning(f"用户已关注 (用户ID: {fid})")
                return True
            else:
                self.logger.error(f"关注失败 (用户ID: {fid}): {result['message']}")
                return False
                
        except Exception as e:
            self.logger.error(f"关注异常 (用户ID: {fid}): {e}")
            return False

    def unfollow_user(self, fid: int) -> bool:
        """取消关注用户
        
        Args:
            fid: 用户ID
            
        Returns:
            是否成功
        """
        if self.config['settings'].get('test_mode', False):
            time.sleep(random.uniform(0.1, 0.3))
            return True
        
        url = "https://api.bilibili.com/x/relation/modify"
        data = {
            'fid': fid,
            'act': 2,
            'csrf': self.config['cookies']['bili_jct']
        }
        
        try:
            self.anti_control.before_request()
            response = self.session.post(url, data=data)
            self.anti_control.after_request()
            
            result = response.json()
            code = result.get('code', -1)
            
            if code == 0:
                return True
            elif code == 22015:
                return True
            elif code in [-352, 22016]:
                self.logger.warning(f"请求被限制 (code: {code})，尝试重试...")
                for attempt in range(self.anti_control.max_retries):
                    delay = self.anti_control.get_retry_delay(attempt + 1, code)
                    self.logger.info(f"等待 {delay:.2f} 秒后重试...")
                    time.sleep(delay)
                    
                    self.anti_control.before_request()
                    response = self.session.post(url, data=data)
                    self.anti_control.after_request()
                    
                    result = response.json()
                    code = result.get('code', -1)
                    
                    if code == 0:
                        return True
                    elif code == 22015:
                        return True
                
                self.logger.error(f"取消关注失败 (用户ID: {fid}): 重试次数耗尽")
                return False
            else:
                self.logger.error(f"取消关注失败 (用户ID: {fid}): {result.get('message', '未知错误')}")
                return False
                
        except Exception as e:
            self.logger.error(f"取消关注异常 (用户ID: {fid}): {e}")
            return False
    
    def batch_unfollow_all(self, confirm_callback=None) -> Dict:
        """批量取消所有关注
        
        Args:
            confirm_callback: 确认回调函数
            
        Returns:
            操作结果统计
        """
        all_following = self.get_all_following()
        
        if not all_following:
            return {'total': 0, 'success': 0, 'failed': 0}
        
        total_count = len(all_following)
        is_test_mode = self.config['settings'].get('test_mode', False)
        max_test_ops = self.config['settings'].get('max_test_operations', 5)
        
        if is_test_mode:
            original_count = total_count
            total_count = min(total_count, max_test_ops)
            all_following = all_following[:total_count]
            self.logger.debug(f"测试模式：限制操作数量为 {total_count}")
        
        if confirm_callback and not confirm_callback(total_count):
            self.logger.info("用户取消操作")
            return {'total': total_count, 'success': 0, 'failed': 0, 'cancelled': True}
        
        self.logger.info(f"开始批量取消关注，共 {total_count} 个用户（反风控模式）")
        
        success_count = 0
        failed_count = 0
        
        for i, user in enumerate(all_following, 1):
            fid = user['mid']
            uname = user['uname']
            
            self.logger.info(f"[{i}/{total_count}] 正在取消关注: {uname} (ID: {fid})")
            
            if self.unfollow_user(fid):
                success_count += 1
                self.logger.info(f"✓ 成功取消关注: {uname}")
            else:
                failed_count += 1
                self.logger.error(f"✗ 取消关注失败: {uname}")
            
            if i < total_count:
                delay = self.anti_control.get_random_delay()
                jitter = self.anti_control.get_jitter()
                total_delay = delay + jitter
                self.logger.debug(f"操作间延迟: {total_delay:.2f} 秒")
                time.sleep(total_delay)
        
        result = {
            'total': total_count,
            'success': success_count,
            'failed': failed_count,
            'test_mode': is_test_mode
        }
        
        self.logger.info(f"批量取消关注完成! 总计: {total_count}, 成功: {success_count}, 失败: {failed_count}")
        return result
    
    def get_user_info(self) -> Dict:
        """获取当前用户信息"""
        url = "https://api.bilibili.com/x/web-interface/nav"
        
        try:
            if self.config.get('anti_control', {}).get('enabled', True):
                self.anti_control.before_request()
                response = self._make_request('GET', url)
                self.anti_control.after_request()
            else:
                response = self._make_request('GET', url)
            
            data = response.json()
            
            if data['code'] == 0:
                return data['data']
            else:
                raise Exception(f"获取用户信息失败: {data['message']}")
                
        except Exception as e:
            self.logger.error(f"获取用户信息异常: {e}")
            return {}
