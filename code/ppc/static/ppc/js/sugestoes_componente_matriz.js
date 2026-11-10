document.addEventListener("DOMContentLoaded", function () {
    const painel = document.getElementById("sugestoes-componente");
    const formulario = painel && painel.closest("form");
    const nome = document.getElementById("id_nome");
    const lista = document.getElementById("sugestoes-componente-lista");
    if (!painel || !formulario || !nome || !lista) return;

    let timer = null;
    let requisicao = null;
    let sequencia = 0;

    function elemento(tag, texto, classe) {
        const node = document.createElement(tag);
        if (texto !== undefined) node.textContent = texto;
        if (classe) node.className = classe;
        return node;
    }

    function campoOculto(form, name, value) {
        const campo = document.createElement("input");
        campo.type = "hidden";
        campo.name = name;
        campo.value = value == null ? "" : String(value);
        form.appendChild(campo);
    }

    function usarComponente(item) {
        const post = document.createElement("form");
        post.method = "post";
        post.action = painel.dataset.urlAdicionar;
        campoOculto(post, "csrfmiddlewaretoken", formulario.querySelector("[name=csrfmiddlewaretoken]")?.value || "");
        campoOculto(post, "componente_id", item.id);
        ["periodo", "nucleo", "natureza", "grupo_licenciatura"].forEach(function (campo) {
            const origem = formulario.elements.namedItem(campo);
            if (origem) campoOculto(post, campo, origem.value);
        });
        document.body.appendChild(post);
        post.submit();
    }

    function renderizar(data) {
        lista.replaceChildren();
        const itens = Array.isArray(data.itens) ? data.itens : [];
        painel.hidden = itens.length === 0;
        itens.forEach(function (item) {
            const li = elemento("li");
            const card = elemento("div", undefined, "card");
            const titulo = elemento("p");
            const codigoTexto = item.codigo ? item.codigo + " — " : "Sem código — ";
            titulo.appendChild(elemento("strong", codigoTexto + item.nome));
            if (item.status === "pendente") {
                titulo.appendChild(document.createTextNode(" "));
                titulo.appendChild(elemento("span", "Aguardando aprovação", "status-badge status-pendente"));
            }
            card.appendChild(titulo);
            card.appendChild(elemento("p", "CH: " + item.carga_horaria_label));

            const acoes = elemento("div");
            const link = elemento("a", "Abrir detalhes");
            link.href = item.url_detalhe;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            acoes.appendChild(link);
            acoes.appendChild(document.createTextNode(" "));
            const usar = elemento("button", "Usar este componente", "btn btn-secundario");
            usar.type = "button";
            usar.addEventListener("click", function () { usarComponente(item); });
            acoes.appendChild(usar);
            card.appendChild(acoes);
            li.appendChild(card);
            lista.appendChild(li);
        });
    }

    async function buscar() {
        const valorNome = nome.value.trim();
        if (requisicao) requisicao.abort();
        if (valorNome.length < 3) {
            painel.hidden = true;
            lista.replaceChildren();
            return;
        }
        const id = ++sequencia;
        requisicao = new AbortController();
        const params = new URLSearchParams({ nome: valorNome });
        try {
            const response = await fetch(painel.dataset.url + "?" + params.toString(), {
                headers: { "Accept": "application/json" },
                signal: requisicao.signal,
            });
            if (!response.ok) throw new Error("Busca indisponível");
            const data = await response.json();
            if (id === sequencia) renderizar(data);
        } catch (error) {
            if (error.name !== "AbortError") painel.hidden = true;
        }
    }

    function agendar() {
        window.clearTimeout(timer);
        if (requisicao) requisicao.abort();
        timer = window.setTimeout(buscar, 300);
    }

    nome.addEventListener("input", agendar);
});
