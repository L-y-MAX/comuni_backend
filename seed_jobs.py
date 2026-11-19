# -*- coding: utf-8 -*-
"""
从本地样例数据中整理出的 7 条校招岗位，导入 RecruitmentInfo。

用法（在服务器 /root/comuni_backend 下）：
    source venv/bin/activate
    python manage.py shell -c "exec(open('seed_jobs.py', encoding='utf-8').read())"

说明：
- 企业名、岗位名、行业、招聘专业、薪资、人数、岗位职责/任职要求来自本地样例数据；
- 信用代码、联系人、电话、地址、邮箱、展位号是为演示补的占位值，可在后台修改；
- 可重复执行，同企业+同岗位会更新而不是重复插入。
"""

from datetime import date

from employment.models import RecruitmentInfo

JOBS = [
    {
        'enterprise_name': '山东智造数字科技有限公司',
        'credit_code': '91371500MA3JOB0001',
        'enterprise_nature': '民营企业',
        'enterprise_scale': '100-499人',
        'industry': '数字经济',
        'job_name': 'Java开发工程师',
        'recruit_major': '计算机科学与技术、软件工程',
        'recruit_number': '5人',
        'monthly_salary': '7000-12000',
        'enterprise_intro': (
            '岗位职责：负责公司后端系统的设计与开发，参与需求分析与技术方案优化，配合团队完成项目落地。'
            '任职要求：熟练掌握Java、SpringBoot、MySQL、Redis、MyBatis，熟悉Linux常用命令与Git；'
            '具有良好的沟通表达能力和团队协作精神，能承受一定工作压力，责任心强，具备较强的学习能力；'
            '有相关实习经历或项目经验者优先；持有计算机二级证书者优先，有阿里云相关认证者优先。'
        ),
        'contact_person': '张老师',
        'contact_phone': '0635-0000001',
        'company_address': '山东省聊城市东昌府区智造路 1 号',
        'email': 'hr@zhizao-demo.com',
        'registration_time': date(2026, 3, 1),
        'audit_status': '已通过',
        'booth_number': 'A01',
        'check_in_status': '已签到',
        'is_alumni_enterprise': '是',
    },
    {
        'enterprise_name': '鲁西农业数字产业研究院',
        'credit_code': '91371500MA3JOB0002',
        'enterprise_nature': '事业单位',
        'enterprise_scale': '50-99人',
        'industry': '现代农业',
        'job_name': '数据分析师',
        'recruit_major': '数据科学与大数据技术、统计学、计算机科学与技术',
        'recruit_number': '3人',
        'monthly_salary': '6500-10000',
        'enterprise_intro': (
            '岗位职责：负责农产品市场数据的采集、清洗与分析建模，输出可视化分析报告支撑业务决策。'
            '任职要求：熟悉SQL与Python，掌握Excel、Tableau或Power BI等数据可视化工具，了解统计学基础；'
            '具备较强的逻辑思维与数据敏感度，能从数据中发现问题并提出改进建议；'
            '有数据分析相关实习或竞赛项目经历者优先；持有计算机二级证书者优先。'
        ),
        'contact_person': '李老师',
        'contact_phone': '0635-0000002',
        'company_address': '山东省聊城市东昌府区农业大厦 8 层',
        'email': 'hr@luxi-agri-demo.com',
        'registration_time': date(2026, 3, 2),
        'audit_status': '已通过',
        'booth_number': 'A02',
        'check_in_status': '已签到',
        'is_alumni_enterprise': '否',
    },
    {
        'enterprise_name': '聊城恒力智能装备有限公司',
        'credit_code': '91371500MA3JOB0003',
        'enterprise_nature': '民营企业',
        'enterprise_scale': '100-499人',
        'industry': '智能制造',
        'job_name': '机械设计工程师',
        'recruit_major': '机械设计制造及其自动化、车辆工程',
        'recruit_number': '4人',
        'monthly_salary': '6000-9000',
        'enterprise_intro': (
            '岗位职责：负责非标自动化设备的机械结构设计与三维建模，使用SolidWorks、AutoCAD完成图纸绘制，'
            '参与工艺方案改进与样机装配调试。任职要求：熟悉机械设计与机械制图，掌握SolidWorks、AutoCAD，'
            '了解PLC与电气控制者优先；具备较强的动手实操能力与团队协作意识，工作严谨细致，能适应车间现场环境；'
            '有机械相关实习或竞赛项目经历者优先。'
        ),
        'contact_person': '王老师',
        'contact_phone': '0635-0000003',
        'company_address': '山东省聊城市高新区恒力工业园',
        'email': 'hr@hengli-demo.com',
        'registration_time': date(2026, 3, 3),
        'audit_status': '已通过',
        'booth_number': 'A03',
        'check_in_status': '已签到',
        'is_alumni_enterprise': '是',
    },
    {
        'enterprise_name': '山东智汇数据科技有限公司',
        'credit_code': '91371500MA3JOB0004',
        'enterprise_nature': '民营企业',
        'enterprise_scale': '50-99人',
        'industry': '数字经济',
        'job_name': '大数据开发工程师',
        'recruit_major': '计算机科学与技术、数据科学与大数据技术、软件工程',
        'recruit_number': '3人',
        'monthly_salary': '8000-14000',
        'enterprise_intro': (
            '岗位职责：负责数据仓库与离线、实时数据链路的开发维护，完成数据采集、清洗、建模与调度。'
            '任职要求：熟练掌握Java与SQL，熟悉Hadoop、Spark、Hive，了解Flink与Kafka；'
            '熟悉Linux常用命令与Git，具备较强的逻辑思维与数据分析能力；'
            '有大数据相关实习或项目经验者优先；持有计算机二级证书者优先。'
        ),
        'contact_person': '赵老师',
        'contact_phone': '0635-0000004',
        'company_address': '山东省聊城市开发区智汇大厦 12 层',
        'email': 'hr@zhihui-demo.com',
        'registration_time': date(2026, 3, 4),
        'audit_status': '已通过',
        'booth_number': 'A04',
        'check_in_status': '已签到',
        'is_alumni_enterprise': '否',
    },
    {
        'enterprise_name': '聊城云启软件技术有限公司',
        'credit_code': '91371500MA3JOB0005',
        'enterprise_nature': '民营企业',
        'enterprise_scale': '20-49人',
        'industry': '数字经济',
        'job_name': '测试开发工程师',
        'recruit_major': '计算机科学与技术、软件工程、网络工程',
        'recruit_number': '4人',
        'monthly_salary': '6500-11000',
        'enterprise_intro': (
            '岗位职责：负责自动化测试框架搭建与用例开发，参与需求评审与缺陷跟踪，保障版本质量。'
            '任职要求：熟练掌握Java或Python，熟悉MySQL与Linux，了解Selenium、JUnit等测试工具；'
            '掌握Git协作流程，工作严谨细致，具备良好的沟通能力与团队协作精神；'
            '有测试相关实习或项目经验者优先；持有计算机二级证书者优先。'
        ),
        'contact_person': '孙老师',
        'contact_phone': '0635-0000005',
        'company_address': '山东省聊城市东昌府区云启科技园',
        'email': 'hr@yunqi-demo.com',
        'registration_time': date(2026, 3, 5),
        'audit_status': '待审核',
        'booth_number': 'B01',
        'check_in_status': '未签到',
        'is_alumni_enterprise': '否',
    },
    {
        'enterprise_name': '聊城农谷品牌管理有限公司',
        'credit_code': '91371500MA3JOB0006',
        'enterprise_nature': '民营企业',
        'enterprise_scale': '20-49人',
        'industry': '现代农业',
        'job_name': '新媒体运营专员',
        'recruit_major': '市场营销、新闻传播学、汉语言文学',
        'recruit_number': '2人',
        'monthly_salary': '4500-7000',
        'enterprise_intro': (
            '岗位职责：负责公司抖音、小红书等平台的内容策划与文案撰写，独立完成短视频脚本与剪辑，'
            '策划直播活动并跟进社群运营数据。任职要求：具备较强的文案表达与沟通协调能力，'
            '对农业品牌与农产品行业有一定认知，善于捕捉市场趋势；工作主动，学习能力强，能承受节点压力；'
            '有新媒体运营相关实习经历者优先。'
        ),
        'contact_person': '周老师',
        'contact_phone': '0635-0000006',
        'company_address': '山东省聊城市东昌府区农谷电商园',
        'email': 'hr@nonggu-demo.com',
        'registration_time': date(2026, 3, 6),
        'audit_status': '已通过',
        'booth_number': 'B02',
        'check_in_status': '已签到',
        'is_alumni_enterprise': '是',
    },
    {
        'enterprise_name': '聊城市东昌府区某中学',
        'credit_code': '91371500MA3JOB0007',
        'enterprise_nature': '事业单位',
        'enterprise_scale': '100-499人',
        'industry': '教育文旅',
        'job_name': '中学信息技术教师',
        'recruit_major': '计算机科学与技术、教育技术学、软件工程',
        'recruit_number': '2人',
        'monthly_salary': '5000-8000',
        'enterprise_intro': (
            '岗位职责：承担中学信息技术课程教学与教研工作，负责课程设计、教案编写与学生竞赛辅导。'
            '任职要求：具备教师资格证与普通话证书，熟悉Python或Scratch等编程教学工具；'
            '有较强的语言表达能力与责任心，善于沟通，能耐心指导学生；'
            '有支教、家教或教学实习经历者优先。'
        ),
        'contact_person': '刘老师',
        'contact_phone': '0635-0000007',
        'company_address': '山东省聊城市东昌府区教育路',
        'email': 'hr@school-demo.com',
        'registration_time': date(2026, 3, 7),
        'audit_status': '已通过',
        'booth_number': 'B03',
        'check_in_status': '已签到',
        'is_alumni_enterprise': '否',
    },
]


def main():
    created = 0
    updated = 0
    for job in JOBS:
        _, is_created = RecruitmentInfo.objects.update_or_create(
            enterprise_name=job['enterprise_name'],
            job_name=job['job_name'],
            defaults=job,
        )
        if is_created:
            created += 1
        else:
            updated += 1

    print('=' * 50)
    print(f'岗位导入完成：新增 {created} 条，更新 {updated} 条')
    print(f'当前招聘信息总数：{RecruitmentInfo.objects.count()} 条')
    print('=' * 50)


main()
