#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2025/12/9 23:49
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : forms.py
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
#     [功能描述] 注册表单
#     [技术架构]
# ----------------------------------------------------------------------------
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


class RegisterForm(UserCreationForm):
    """
    用户注册表单

    继承了 Django 内置的用户创建表单：
    """
    email = forms.EmailField(required=True, label="邮箱")
    gender = forms.ChoiceField(choices=User.GENDER_CHOICES, label="性别")

    class Meta:
        model = User
        fields = ('username', 'email', 'gender', 'password1', 'password2')
