from django.conf import settings  # 导入settings
from django.conf.urls.static import static  # 导入static函数
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
urlpatterns = [
    path('admin/', admin.site.urls),  # admin
    path('api/', include(router.urls)),  # api root /
    path('api/v1/', include('rest_framework.urls', namespace='rest_framework')),  # api login
    path('', include('users.urls')),  # register users app urls
    path('', include('knowledge.urls')),  # register knowledge app urls
    path('', include('ai_chat.urls')),  # register knowledge app urls
    path('', include('pay.urls')),  # register knowledge app urls
    path('', include('employment.urls')),  # register employment app urls
]
# 核心添加：开发环境下，注册/media/开头的URL，映射到MEDIA_ROOT目录
if settings.DEBUG:  # 仅开发环境生效，生产环境用Nginx托管
    urlpatterns += static(
        settings.MEDIA_URL,  # 匹配/media/开头的URL
        document_root=settings.MEDIA_ROOT  # 指向本地媒体文件存储目录
    )
