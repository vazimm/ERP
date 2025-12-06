// JS da tela Ambiente de Usuário: gerenciar temas por ambiente

let temasAmbienteCache = [];

function showTemaModal(message, title = 'Aviso', type = 'info', autoClose = false) {
    const overlay = document.createElement('div');
    overlay.className = 'pedido-modal-overlay';
    overlay.setAttribute('aria-hidden', 'false');

    const card = document.createElement('div');
    card.className = `pedido-modal-card ${type}`;
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');

    const btnClose = document.createElement('button');
    btnClose.className = 'modal-close';
    btnClose.innerHTML = '&times;';
    btnClose.addEventListener('click', () => {
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    });

    const h3 = document.createElement('h3');
    h3.className = 'modal-title';
    h3.textContent = title;

    const content = document.createElement('div');
    content.className = 'modal-content';
    content.textContent = message;

    card.appendChild(btnClose);
    card.appendChild(h3);
    card.appendChild(content);
    overlay.appendChild(card);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay && overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
        }
    });

    document.body.appendChild(overlay);
    if (autoClose) {
        setTimeout(() => {
            if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        }, 4000);
    }
}

async function carregarTemasAmbiente() {
    try {
        const resp = await fetch('/api/themes/list-names');
        if (!resp.ok) return;
        const data = await resp.json();
        temasAmbienteCache = Array.isArray(data.temas) ? data.temas : [];
        const select = document.getElementById('select-temas');
        if (!select) return;

        // limpa opções atuais, mantém o placeholder
        select.innerHTML = '<option value="">Selecione um tema</option>';
        temasAmbienteCache.forEach((nome) => {
            const opt = document.createElement('option');
            opt.value = nome;
            opt.textContent = nome;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error('Falha ao carregar lista de temas do ambiente', e);
    }
}

async function salvarTema(event) {
    event.preventDefault();
    const nomeTema = document.getElementById('nome-tema').value.trim();
    if (!nomeTema) {
        showTemaModal('Informe um nome para o tema.', 'Erro', 'error');
        return;
    }

    // Verifica se já existe tema com mesmo nome (case-insensitive)
    const existe = (temasAmbienteCache || []).some(
        (t) => String(t).toLowerCase() === nomeTema.toLowerCase()
    );
    if (existe) {
        showTemaModal(
            `Já existe um tema chamado "${nomeTema}" neste ambiente. Use outro nome ou edite o tema existente.`,
            'Nome de tema duplicado',
            'error'
        );
        return;
    }

    const payload = {
        tema: nomeTema,
        cores: {
            'cor-fundo': document.getElementById('cor-fundo').value,
            'cor-texto': document.getElementById('cor-texto').value,
            'cor-botao-texto': document.getElementById('cor-botao-texto').value,
            'cor-primaria': document.getElementById('cor-primaria').value,
            'cor-secundaria': document.getElementById('cor-secundaria').value,
            'cor-botao': document.getElementById('cor-botao').value,
        },
    };

    try {
        const resp = await fetch('/api/themes/custom', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            showTemaModal(
                'Falha ao salvar tema: ' + (err.error || resp.status),
                'Erro ao salvar tema',
                'error'
            );
            return;
        }
        showTemaModal('Tema salvo com sucesso.', 'Sucesso', 'success', true);
        await carregarTemasAmbiente();
    } catch (e) {
        console.error('Erro ao salvar tema', e);
        showTemaModal('Erro inesperado ao salvar tema.', 'Erro', 'error');
    }
}

async function aplicarTemaAmbiente() {
    const select = document.getElementById('select-temas');
    if (!select || !select.value) {
        showTemaModal('Selecione um tema.', 'Aviso', 'info');
        return;
    }
    const tema = select.value;

    try {
        const resp = await fetch('/api/themes/apply-to-env', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tema }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            showTemaModal(
                'Falha ao aplicar tema: ' + (err.error || resp.status),
                'Erro ao aplicar tema',
                'error'
            );
            return;
        }
        showTemaModal(
            'Tema aplicado a todos os usuários do ambiente.',
            'Sucesso',
            'success',
            true
        );

        // Recarrega imediatamente a paleta de cores na tela atual, se disponível
        if (typeof aplicarTemaDinamico === 'function') {
            try {
                aplicarTemaDinamico();
            } catch (e) {
                console.debug('Falha ao reaplicar tema dinamicamente após aplicar ao ambiente', e);
            }
        }
    } catch (e) {
        console.error('Erro ao aplicar tema ao ambiente', e);
        showTemaModal('Erro inesperado ao aplicar tema.', 'Erro', 'error');
    }
}

window.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('form-criar-tema');
    if (form) form.addEventListener('submit', salvarTema);

    const btnAplicar = document.getElementById('btn-aplicar-tema');
    if (btnAplicar) btnAplicar.addEventListener('click', aplicarTemaAmbiente);

    carregarTemasAmbiente();
});
