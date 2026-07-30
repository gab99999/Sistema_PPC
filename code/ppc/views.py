from django.shortcuts import render

def home(request):
    return render(request, "ppc/home.html")

def sobre(request):
    return render(request, 'ppc/sobre.html' )
# Create your views here.
