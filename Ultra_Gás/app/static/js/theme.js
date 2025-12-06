function mudarTema(tema) {
    // Atualiza a classe do body para manter compatibilidade
    document.body.className = tema;

    // Persiste o tema atual na sessão via API
    fetch(`/api/themes/${encodeURIComponent(tema)}/apply`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    }).catch((e) => console.error('Falha ao salvar tema na sessão', e));

    // Aplica imediatamente as variáveis CSS, se já carregadas
    document.body.dataset.theme = tema;
    aplicarTemaDinamico();
}

async function aplicarTemaDinamico() {
    try {
        const respTemas = await fetch('/api/themes');
        if (!respTemas.ok) return;
        const temas = await respTemas.json();

        const body = document.body;
        const temaAtual = (body.dataset.theme || body.className || 'root').toLowerCase();
        const varsTema = temas[temaAtual] || temas['root'] || {};
        const root = document.documentElement;

        Object.keys(varsTema).forEach((nome) => {
            const cssVar = `--${nome}`;
            root.style.setProperty(cssVar, varsTema[nome]);
        });
    } catch (e) {
        console.error('Falha ao aplicar tema dinâmico', e);
    }
}

window.addEventListener('DOMContentLoaded', aplicarTemaDinamico);
