#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2025/12/26 21:46
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : utils.py
# @Version : 0.0.1 (SemVer规范：主版本.次版本.修订号)
# @Project : comuni_backend
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
# users/utils.py
import os
import uuid
from datetime import datetime
from django.conf import settings


def rename_avatar(instance, filename):
    """
    自定义头像重命名函数（按用户ID分文件夹）
    :param instance: User模型实例
    :param filename: 原始文件名
    :return: 新的文件路径（如avatars/47acff2d-1234-5678-90ab-cdef12345678/47acff2d_20251226_abc123.png）
    """
    # 1. 获取文件扩展名（保留原格式：png/jpg/jpeg等）
    ext = os.path.splitext(filename)[1].lower()  # 转小写，统一格式

    # 2. 生成新头像文件名（保留你的原有规则）
    id_short = str(instance.id)[:8]  # 取UUID前8位，缩短头像文件名长度
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')  # 时间戳
    random_str = str(uuid.uuid4())[:6]  # 6位随机字符串
    new_filename = f"{id_short}_{timestamp}_{random_str}{ext}"

    # 3. 构建最终路径：avatars/用户完整UUID/新文件名
    # instance.id 是用户的UUID主键，作为子文件夹名
    user_folder = str(instance.id)  # 用户专属文件夹（完整UUID，避免重复）
    final_path = os.path.join('avatars', user_folder, new_filename)

    # 可选：显式确保用户文件夹存在（Django的ImageField也会自动创建，但显式处理更稳妥）
    full_folder_path = os.path.join(settings.MEDIA_ROOT, 'avatars', user_folder)
    os.makedirs(full_folder_path, exist_ok=True)  # 不存在则创建，存在则不报错

    return final_path


# ====================== 独立的头像URL拼接函数（可复用） ======================
# 头像url拼接 用于登录接口 WeChatMiniLoginAPIView 和
# userinfo 接口 UserInfoView
def get_user_avatar_full_url(user, request=None):
    """
    安全获取用户头像的完整可访问URL
    :param user: User模型实例（当前登录用户）
    :param request: HttpRequest对象（用于自动提取站点域名，可选）
    :return: 完整头像URL（空字符串/完整HTTP URL）
    """
    # 初始化返回空字符串
    avatar_url = ""

    # 三重安全校验：有avatar字段 + avatar有值 + avatar有url属性（Django FileField/ImageField特性）
    if hasattr(user, 'avatar') and user.avatar and hasattr(user.avatar, 'url'):
        # 1. 获取站点基础URL（双重容错）
        # 方式1：优先使用settings配置的SITE_URL（推荐，统一域名）
        base_url = getattr(settings, 'SITE_URL', '')

        # 方式2：未配置SITE_URL时，从request提取（需传入request参数）
        if not base_url and request:
            base_url = f"{request.scheme}://{request.get_host()}"

        # 3. 仅当获取到base_url时才拼接，避免拼接出无效URL
        if base_url:
            avatar_url = f"{base_url}{user.avatar.url}"

    return avatar_url

