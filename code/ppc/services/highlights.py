from pathlib import Path

from django.contrib.staticfiles.finders import find


def css_destaques_para_pdf():
    """Lê a mesma folha estática usada pelo CKEditor e pelas telas para embuti-la no PDF."""
    caminho = find("ppc/highlights.css")
    if not caminho:
        raise FileNotFoundError("Não foi possível localizar ppc/highlights.css.")
    return Path(caminho).read_text(encoding="utf-8")
