#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/2/9 16:00
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : urls.py
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
#     [技术架构]
# ----------------------------------------------------------------------------
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PayOrderViewSet, pay_page

# 初始化DRF路由器
router = DefaultRouter()
# 注册支付订单ViewSet（包含创建、查询、回调所有接口）
router.register(r'pay', PayOrderViewSet, basename='pay')

# 无需单独注册notify路由，由Router自动管理
urlpatterns = [
    path("api/v1/", include(router.urls)),
    path('pay/', pay_page, name='pay'),
]