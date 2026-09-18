from django.urls import path
from .views import ReportListCreateView, BlockListCreateView, BlockDestroyView

urlpatterns = [
    path('reports/', ReportListCreateView.as_view(), name='report-list-create'),
    path('blocks/', BlockListCreateView.as_view(), name='block-list-create'),
    path('blocks/<uuid:blocked_id>/', BlockDestroyView.as_view(), name='block-destroy'),
]
