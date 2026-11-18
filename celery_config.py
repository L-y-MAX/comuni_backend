#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/2/22 0:52
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : celery.py
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
#     [功能描述] 
#     [技术架构] 要实现 前端→Django→阿里云 全链路异步，核心是让 Django
#               接收前端请求后立即返回任务标识，释放请求线程，
#               然后通过「异步任务队列 + 前端轮询 / 实时推送」获取最终结果，
#               而非让前端一直等待响应。
# ----------------------------------------------------------------------------
import os
from celery import Celery
from django.conf import settings

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setsite.settings')

app = Celery('KnowledgeBase')
# 从Django配置中读取Celery配置
app.config_from_object('django.conf:settings', namespace='CELERY')
# 自动发现所有app中的tasks.py
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)