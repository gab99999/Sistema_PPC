from django.shortcuts import render

def home(request):
    return render(request, "ppc/home.html")

def ajuda(request):
    return render(request, 'ppc/ajuda.html' )
# Create your views here.
