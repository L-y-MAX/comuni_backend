#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/2/22 0:58
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : tasks.py
# @Version : 0.0.1 (SemVer规范：主版本.次版本.修订号)
# @Project : KnowledgeBase
# @IDE     : PyCharm 
# ----------------------------------------------------------------------------
# 协作规范区
# @Dependencies: 
#     - requests>=2.25.1 (通过`requirements.txt`管理)
#     - package<version (版本冲突规避说明将在此写明，如无则通过`requirements.txt`配置)
# @finish      : 
#     - [高优先级] 示例：实现多线程优化 (负责人: @Skixkk)
#     - [待评审] 示例：重构数据验证逻辑XXX (截止日期: 2025-0X-XX)
# ----------------------------------------------------------------------------
# 法律声明区
# @License     : MIT
# @SPDX-License-Identifier: MIT
# @Copyright   : Copyright (c) 2025 by Skixkk , All Rights Reserved
# @Description : [Functional description of the file]
#     [功能描述] 把调用阿里云的逻辑封装为 Celery 异步任务：
#     [技术架构] 
# ----------------------------------------------------------------------------
import json
import logging
import requests
from celery import shared_task
from django.conf import settings

# 1. 创建模块级别的日志器（核心修复：替代 Celery 任务实例的 logger）
logger = logging.getLogger('ai_chat.tasks')  # 明确指定日志器名称，方便日志配置


@shared_task(bind=True, max_retries=3)
def call_qwen_api(self, current_article, history_messages, user_message):
    """
    调用通义千问API的异步任务
    最终修复：
    1. 完全移除 self.get_logger()，改用 Python 标准 logging 模块
    2. 保留 bind=True 用于重试逻辑，仅移除 logger 相关的 self 调用
    3. 继续修复通义千问 API 400 错误的参数格式
    """
    try:
        # 0. 配置校验：Key 为空时直接返回可读错误，避免 None/空字符串引发底层异常
        if not settings.DASHSCOPE_API_KEY:
            return {
                "status": "FAILURE",
                "error": "未配置 DASHSCOPE_API_KEY，请在服务器 .env 中填写阿里云百炼 API Key",
                "error_type": "ConfigError",
            }

        # 接口地址兼容两种写法：base URL 或完整的 /chat/completions
        api_url = (settings.DASHSCOPE_API_URL or "").rstrip("/")
        if not api_url.endswith("/chat/completions"):
            api_url = f"{api_url}/chat/completions"

        # 1. 参数预处理：确保所有数据可序列化，避免编码问题
        article_content = ""
        if isinstance(current_article, dict):
            article_content = current_article.get('content', '') or current_article.get('text', '')
        elif isinstance(current_article, str):
            article_content = current_article
        article_content = article_content[:8000] if article_content else "无参考文章"

        # 2. 构建符合通义千问兼容模式的请求参数（修复400错误核心）
        request_data = {
            "model": "qwen-turbo",  # 确认模型名称正确
            "messages": [
                {
                    "role": "system",
                    "content": f"请基于以下文章内容回答用户问题，仅使用文章中的信息，不要编造：\n{article_content}"
                },
                *[msg for msg in history_messages if isinstance(msg, dict) and msg.get('role') and msg.get('content')],
                {"role": "user", "content": user_message.strip()}
            ],
            "temperature": 0.7,
            "top_p": 0.8,
            "max_tokens": 2000,
            "stream": False
        }

        #  改用模块级别的 logger，不再依赖 self
        logger.info(f"调用通义千问API，参数（截断）：{json.dumps(request_data, ensure_ascii=False)[:500]}...")

        # 3. 调用通义千问API
        response = requests.post(
            url=api_url,
            headers={
                "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                "Content-Type": "application/json; charset=utf-8"
            },
            json=request_data,
            timeout=60
        )

        # 4. 处理响应
        logger.info(f"API响应状态码：{response.status_code}")
        if response.status_code != 200:
            logger.error(f"API返回错误内容：{response.text}")
        response.raise_for_status()

        # 5. 解析响应结果
        result = response.json()
        logger.info(f"API响应结果（截断）：{json.dumps(result, ensure_ascii=False)[:500]}...")

        if result.get("choices") and len(result["choices"]) > 0:
            answer = result["choices"][0]["message"]["content"].strip()
            return {
                "status": "SUCCESS",
                "answer": answer
            }
        else:
            raise Exception(f"API返回无有效内容：{json.dumps(result, ensure_ascii=False)}")

    except requests.exceptions.HTTPError as e:
        #  改用模块级别的 logger
        error_msg = f"API调用失败：{str(e)}，响应内容：{e.response.text if e.response else '无响应'}"
        logger.error(error_msg, exc_info=True)

        # 重试逻辑（保留 self 用于重试，bind=True 仍需要）
        if self.request.retries < self.max_retries and e.response.status_code not in [400, 401]:
            logger.warning(f"重试任务（第{self.request.retries + 1}次）...")
            self.retry(exc=Exception(error_msg), countdown=5)

        return {
            "status": "FAILURE",
            "error": error_msg,
            "error_type": "HTTPError"
        }

    except Exception as e:
        #  改用模块级别的 logger
        error_msg = f"任务执行失败：{str(e)}"
        logger.error(error_msg, exc_info=True)

        # 重试逻辑
        if self.request.retries < self.max_retries:
            logger.warning(f"重试任务（第{self.request.retries + 1}次）...")
            self.retry(exc=e, countdown=5)

        return {
            "status": "FAILURE",
            "error": error_msg,
            "error_type": type(e).__name__
        }