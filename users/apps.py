from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'users'
    verbose_name = '用户管理'

    def ready(self):
        """
        Override this method in subclasses to run code when Django starts.
        AppConfig 类的 ready() 方法是一个特殊的钩子（hook），当应用（app）加载完成并准备就绪时会自动调用该方法。
        预留初始化逻辑的入口
        :return:
        """
        # 注册
        import users.signals
        pass
