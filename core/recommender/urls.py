from django.urls import path
from django.shortcuts import redirect
from .views import home_view, recommend_view, roadmap_detail_view, search_view, custom_roadmap_view, get_skill_recommendations_api, fetch_fastapi_recommendations


def root_redirect(request):
    return redirect('home')


urlpatterns = [
    path("", root_redirect, name='root_redirect'),
    path("home/", home_view, name="home"),
    path("search/", search_view, name="search"),
    path("recommend/", recommend_view, name="recommend"),
    path("roadmap/custom/", custom_roadmap_view, name="custom_roadmap"),
    path("roadmap/<slug:category_slug>/", roadmap_detail_view, name="roadmap_detail"),
    path("api/skill-recommendations/", get_skill_recommendations_api, name="skill_recommendations_api"),
    path("api/fastapi-recommendations/", fetch_fastapi_recommendations, name="fastapi_recommendations"),
]
