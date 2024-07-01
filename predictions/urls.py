from django.urls import path, include
from . import views
from .views import LeaguePrediction, GeneralPrediction


urlpatterns = [
    # path('perdaypredictions/', views.home, name='home'),
    path('generalprediction/', GeneralPrediction.as_view(), name="xprediction"),
    path('leagueprediction/', LeaguePrediction.as_view(),
         name='league_prediction_api'),
    # path('vip/', views.vipsection, name='vipsection'),
    # path('x/', views.xpredictx, name='xpredictx'),
]
