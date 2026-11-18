#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2025/12/9 23:43
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : signals.py
# @Version : 0.0.1 (SemVer规范：主版本.次版本.修订号)
# @Project : comuni_backend
# @IDE     : PyCharm 
# ----------------------------------------------------------------------------
# 协作规范区
# @Dependencies: 
#     - requests>=2.25.1 (通过`requirements.txt`管理)
#     - package<version (版本冲突规避说明将在此写明，如无则通过`requirements.txt`配置)
# ----------------------------------------------------------------------------
# 法律声明区
# @License     : MIT
# @SPDX-License-Identifier: MIT
# @Copyright   : Copyright (c) 2025 by Skixkk , All Rights Reserved
# @Description : [Functional description of the file]
#     [功能描述] hook 钩住 signals 发送欢迎邮件
#     [技术架构]
# ----------------------------------------------------------------------------
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from .models import User
from dotenv import load_dotenv
import os

load_dotenv()


@receiver(post_save, sender=User)
def handle_user_registration(instance, created, **kwargs):
    """用户注册后触发的信号处理函数"""
    if created:  # 仅在用户首次创建（注册）时执行
        # 示例：发送欢迎邮件（需在 settings.py 配置邮件服务器）
        subject = "欢迎注册用户, 感谢您使用我们的产品"
        message = f"亲爱的 {instance.username}，感谢您的注册！"
        EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')  # 发送者用户名（邮箱地址）
        send_mail(
            subject=subject,
            message=message,
            from_email=EMAIL_HOST_USER,  # 发件人邮箱
            recipient_list=[instance.email],  # 收件人邮箱（注册时填写的邮箱）
            fail_silently=False,
        )
