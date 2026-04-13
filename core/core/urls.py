from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def home(request):
    return HttpResponse("OK")   # 🔥 simple response

urlpatterns = [
    path('', home),  # 🔥 REQUIRED

    path('admin/', admin.site.urls),
    path('users/', include('core.users.urls')),
    path('recommender/', include('core.recommender.urls')),
    path('courses/', include('core.courses.urls')),
]