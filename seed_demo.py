# -*- coding: utf-8 -*-
"""
职引星途演示数据种子脚本

用法（在服务器 /root/comuni_backend 下）：
    source venv/bin/activate
    python manage.py shell -c "exec(open('seed_demo.py', encoding='utf-8').read())"

特点：
- 可重复执行，已存在的数据不会重复创建；
- 只创建演示数据，不删除任何现有数据；
- 演示账号密码统一为 Demo@123456。
"""

from datetime import date, timedelta

from django.utils import timezone

from users.models import User, VipInfo, UserFollow
from knowledge.models import (
    KnowledgeBase,
    KnowledgeNode,
    NodeTag,
    KnowledgeShare,
    NodeComment,
    UserFollowKnowledgeBase,
)
from employment.models import RecruitmentInfo

DEMO_PASSWORD = 'Demo@123456'


def ensure_user(username, email, **extra):
    user = User.objects.filter(username=username).first()
    if user:
        return user, False
    user = User.objects.create_user(
        username=username,
        email=email,
        password=DEMO_PASSWORD,
        **extra,
    )
    return user, True


def ensure_kb(creator, name, description, is_public):
    kb, created = KnowledgeBase.objects.get_or_create(
        creator=creator,
        name=name,
        defaults={'description': description, 'is_public': is_public},
    )
    if not created:
        # 演示库保持脚本里的可见性，避免之前建过私有库导致搜不到
        changed = False
        if kb.is_public != is_public:
            kb.is_public = is_public
            changed = True
        if description and kb.description != description:
            kb.description = description
            changed = True
        if changed:
            kb.save()
    return kb, created


def ensure_node(kb, creator, name, content, sort_order):
    node, created = KnowledgeNode.objects.get_or_create(
        knowledge_base=kb,
        parent_node=None,
        name=name,
        defaults={
            'creator': creator,
            'content': content,
            'node_type': KnowledgeNode.NodeType.MARKDOWN,
            'editor_mode': 'markdown',
            'sort_order': sort_order,
        },
    )
    return node, created


def main():
    u1, created1 = ensure_user(
        'demo_user',
        'demo_user@example.com',
        gender='male',
        bio='聊城大学计算机专业，准备 2026 届校招。',
    )
    u2, created2 = ensure_user(
        'demo_user2',
        'demo_user2@example.com',
        gender='female',
        bio='关注产品与运营岗位，正在整理作品集。',
    )

    # 会员：给第一个演示账号开一年会员，方便看会员标识
    VipInfo.objects.update_or_create(
        user=u1,
        defaults={
            'is_vip': True,
            'expire_date': timezone.now() + timedelta(days=365),
        },
    )

    # 公开知识库：另一个账号能搜到、能查看
    kb_public, kb_public_created = ensure_kb(
        u1,
        '校招面试笔记',
        '简历、面试、岗位分析相关的求职笔记，公开可查看。',
        True,
    )

    # 私有知识库
    kb_private, kb_private_created = ensure_kb(
        u1,
        '我的求职资料',
        '个人简历草稿和投递记录，仅自己可见。',
        False,
    )

    article_contents = [
        (
            '简历怎么写：一页纸的结构',
            """## 一页纸简历的基本结构

校招简历建议控制在一页，按下面的顺序排：

1. **基本信息**：姓名、电话、邮箱、求职意向。
2. **教育背景**：学校、专业、GPA/排名、主修课程。
3. **项目/实习经历**：每段写清楚「做了什么、怎么做、结果如何」。
4. **技能与证书**：只写和岗位相关的。
5. **自我评价**：两三行，不要空话。

## 每条经历怎么写

用 STAR 结构压缩成两到三行：

- **背景**：项目是做什么的；
- **任务**：你负责哪一块；
- **行动**：用了什么方法、工具；
- **结果**：尽量量化，比如「接口耗时降低 40%」。

## 常见问题

- 不要放与岗位无关的证书；
- 不要写「精通」除非真能被追问；
- 简历文件用 PDF，命名成「姓名-岗位-学校」。
""",
        ),
        (
            '校招面试常见问题与回答思路',
            """## 自我介绍

控制在 1 分钟，结构是：我是谁 → 我做过什么 → 我为什么适合这个岗位。

## 项目追问

面试官通常会问：

1. 这个项目你具体负责什么？
2. 遇到最大的困难是什么，怎么解决的？
3. 如果重做一次，你会改哪里？

回答时不要背稿，按「背景—行动—结果」讲清楚即可。

## 反问环节

可以问：

- 团队目前最缺什么样的人？
- 新人入职后前三个月的目标是什么？
- 这个岗位的成长路径是怎样的？

不要一上来问薪资和加班。
""",
        ),
        (
            '岗位能力画像怎么看',
            """## 十个维度

平台把岗位要求拆成十个维度：专业技能、证书要求、创新能力、学习能力、抗压能力、沟通能力、实习能力、团队协作、逻辑思维、行业认知。

## 怎么看分数

- **分数越高**：岗位在这个维度上的门槛越高；
- **岗位未提要求**：招聘信息里没写，这一项不参与打分；
- **匹配度**：是你的画像和岗位要求逐项比对的结果，不是绝对好坏。

## 使用建议

1. 先看「关键短板」，只补最影响匹配度的一两项；
2. 再看「技能缺口」，区分必须和优先；
3. 最后结合生涯报告，把缺口拆成接下来三个月的任务。
""",
        ),
    ]

    nodes = []
    for index, (name, content) in enumerate(article_contents, start=1):
        node, _ = ensure_node(kb_public, u1, name, content, index)
        nodes.append(node)

    # 私有库放一篇
    ensure_node(
        kb_private,
        u1,
        '我的投递记录',
        """## 投递记录

| 公司 | 岗位 | 状态 |
| --- | --- | --- |
| 示例科技 | Java 开发 | 已投递 |
| 星途网络 | 产品运营 | 待投递 |

每周更新一次，面试后补面经。
""",
        1,
    )

    # 标签
    tag_names = [('面试', '#ff6a33'), ('简历', '#2f80ed'), ('岗位分析', '#27ae60')]
    tags = []
    for name, color in tag_names:
        tag, _ = NodeTag.objects.get_or_create(
            name=name,
            defaults={'creator': u1, 'color': color},
        )
        tags.append(tag)

    if nodes:
        nodes[0].tags.add(tags[1])
        nodes[1].tags.add(tags[0])
        nodes[2].tags.add(tags[2])

    # 分享 / 关注 / 评论，保证权限相关页面有数据
    KnowledgeShare.objects.get_or_create(
        knowledge_base=kb_public,
        shared_to=u2,
        defaults={'permission_level': 'viewer'},
    )
    UserFollowKnowledgeBase.objects.get_or_create(
        user=u2,
        knowledge_base=kb_public,
        defaults={'is_active': True},
    )
    UserFollow.objects.get_or_create(follower=u2, followed=u1)

    if nodes:
        NodeComment.objects.get_or_create(
            article=nodes[1],
            commented_by=u2,
            comment_text='STAR 结构讲得很清楚，我准备按这个改一下简历。',
            defaults={'type': 'root'},
        )

    # 招聘岗位：列表、详情、岗位画像都有数据
    jobs = [
        {
            'enterprise_name': '示例科技（聊城）有限公司',
            'credit_code': '91371500MA3DEMO001',
            'enterprise_nature': '民营企业',
            'enterprise_scale': '100-499人',
            'enterprise_intro': '专注企业数字化服务的软件公司，校招合作企业。',
            'industry': '计算机软件',
            'job_name': 'Java 开发工程师',
            'recruit_major': '计算机科学与技术、软件工程',
            'recruit_number': '6-10人',
            'monthly_salary': '8k-12k',
            'contact_person': '张老师',
            'contact_phone': '0635-0000001',
            'company_address': '山东省聊城市东昌府区示例路 1 号',
            'email': 'hr@example-tech.com',
            'registration_time': date(2026, 3, 1),
            'audit_status': '已通过',
            'booth_number': 'A01',
            'check_in_status': '已签到',
            'is_alumni_enterprise': '是',
        },
        {
            'enterprise_name': '星途网络科技有限公司',
            'credit_code': '91371500MA3DEMO002',
            'enterprise_nature': '民营企业',
            'enterprise_scale': '50-99人',
            'enterprise_intro': '面向高校的互联网产品团队，主营校园服务产品。',
            'industry': '互联网',
            'job_name': '产品运营',
            'recruit_major': '专业不限，市场营销、汉语言文学优先',
            'recruit_number': '2人',
            'monthly_salary': '6k-9k',
            'contact_person': '李老师',
            'contact_phone': '0635-0000002',
            'company_address': '山东省聊城市高新区星途大厦',
            'email': 'hr@xingtu-demo.com',
            'registration_time': date(2026, 3, 2),
            'audit_status': '已通过',
            'booth_number': 'A02',
            'check_in_status': '已签到',
            'is_alumni_enterprise': '否',
        },
        {
            'enterprise_name': '云帆数据服务有限公司',
            'credit_code': '91371500MA3DEMO003',
            'enterprise_nature': '民营企业',
            'enterprise_scale': '20-49人',
            'enterprise_intro': '提供数据标注与数据分析服务，接收实习生。',
            'industry': '大数据',
            'job_name': '数据分析实习生',
            'recruit_major': '统计学、数学、计算机相关专业',
            'recruit_number': '3人',
            'monthly_salary': '150-200元/天',
            'contact_person': '王老师',
            'contact_phone': '0635-0000003',
            'company_address': '山东省聊城市开发区云帆中心',
            'email': 'hr@yunfan-demo.com',
            'registration_time': date(2026, 3, 3),
            'audit_status': '待审核',
            'booth_number': 'B01',
            'check_in_status': '未签到',
            'is_alumni_enterprise': '是',
        },
    ]

    job_created = 0
    for job in jobs:
        _, created = RecruitmentInfo.objects.get_or_create(
            enterprise_name=job['enterprise_name'],
            job_name=job['job_name'],
            defaults=job,
        )
        if created:
            job_created += 1

    print('=' * 50)
    print('演示数据初始化完成')
    print(f'用户 demo_user：{"新建" if created1 else "已存在"}')
    print(f'用户 demo_user2：{"新建" if created2 else "已存在"}')
    print(f'公开知识库「校招面试笔记」：{"新建" if kb_public_created else "已存在"}')
    print(f'私有知识库「我的求职资料」：{"新建" if kb_private_created else "已存在"}')
    print(f'文章：{len(nodes)} 篇公开 + 1 篇私有')
    print(f'招聘岗位：新加 {job_created} 条（共 {RecruitmentInfo.objects.count()} 条）')
    print('-' * 50)
    print('演示账号：demo_user / demo_user2')
    print(f'统一密码：{DEMO_PASSWORD}')
    print('=' * 50)


main()
