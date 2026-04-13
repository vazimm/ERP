// Controlador da seção "Estoque" na dashboard ambienteUserSettings
// Responsável por:
//  - carregar configuração atual de estoque do ambiente
//  - decidir entre modo inicial (setup) e modo recorrente (adição)
//  - validar capacidade x volume
//  - exibir indicador visual de uso

(function () {
    function qs(id) {
        return document.getElementById(id);
    }

    function parseNonNegativeInt(value) {
        if (value === null || value === undefined || value === '') return 0;
        var n = parseInt(value, 10);
        return isNaN(n) || n < 0 ? 0 : n;
    }

    var CAMPOS = ['p45', 'p20', 'p13', 'p8', 'p5', 'agua'];
    var estoqueCapacidadeAtual = 0;
    var estoqueTotalAtual = 0;

    function atualizarResumoVolumes() {
        var partes = [];
        CAMPOS.forEach(function (campo) {
            var span = qs('qty-estoque-' + campo.replace('p', 'p'));
            var v = span ? parseNonNegativeInt(span.textContent) : 0;
            if (v > 0) {
                partes.push(campo.toUpperCase() + ': ' + v);
            }
        });
        var resumoEl = qs('estoque-resumo-text');
        if (!resumoEl) return;
        resumoEl.textContent = partes.length
            ? 'Volumes informados: ' + partes.join(' | ')
            : 'Nenhum volume informado ainda.';

        // Atualiza previsão de uso considerando os novos volumes
        atualizarPrevisaoUso();
    }

    function atualizarBarraProgresso(percent, texto) {
        var fill = qs('estoque-progress-fill');
        var statusText = qs('estoque-status-text');
        if (fill) {
            var p = Math.max(0, Math.min(100, percent || 0));
            fill.style.width = p + '%';
        }
        if (statusText && texto) {
            statusText.textContent = texto;
        }
    }

    function somaVolumesNovos() {
        var soma = 0;
        CAMPOS.forEach(function (campo) {
            var span = qs('qty-estoque-' + campo.replace('p', 'p'));
            var v = span ? parseNonNegativeInt(span.textContent) : 0;
            soma += v;
        });
        return soma;
    }

    function atualizarQuantidadesAtuais(itens) {
        itens = itens || {};
        CAMPOS.forEach(function (campo) {
            var elAtual = qs('estoque-atual-' + campo);
            if (!elAtual) return;
            var v = parseNonNegativeInt(itens[campo]);
            elAtual.textContent = 'Atual: ' + v;
        });
    }

    function atualizarPrevisaoUso() {
        var selectCap = qs('estoque-capacidade');
        var cap = estoqueCapacidadeAtual || parseNonNegativeInt(selectCap && selectCap.value);
        if (!cap) return;

        var somaNovos = somaVolumesNovos();
        var totalFinal = estoqueTotalAtual + somaNovos;
        var pct = cap ? Math.min(100, (totalFinal / cap) * 100) : 0;
        var remaining = cap - totalFinal;
        if (remaining < 0) remaining = 0;

        var texto = 'Uso: ' + totalFinal + ' / ' + cap + ' itens (' + Math.round(pct) + '%). Espaço livre: ' + remaining + '.';
        if (somaNovos > 0) {
            texto += ' (+' + somaNovos + ' a adicionar.)';
        }
        atualizarBarraProgresso(pct, texto);
    }

    function aplicarConfigUI(config) {
        var selectCap = qs('estoque-capacidade');
        var btn = qs('estoque-submit-btn');

        // Atualiza capacidade e modo
        var capacidade = config.capacity || 250;
        var total = config.current_total || 0;
        var percent = config.percent || 0;
        var remaining = config.remaining;

        estoqueCapacidadeAtual = capacidade;
        estoqueTotalAtual = total;

        if (selectCap) {
            selectCap.value = String(capacidade);
            // Se já estiver configurado, trava mudança de capacidade
            selectCap.disabled = !!config.configured;
        }

        // Atualiza barra e texto de status
        var textoStatus;
        if (!config.configured) {
            textoStatus = 'Estoque ainda não configurado. Defina capacidade e volumes iniciais.';
        } else {
            if (remaining !== null && remaining !== undefined) {
                textoStatus = 'Uso: ' + total + ' / ' + capacidade + ' itens (' + percent + '%). Espaço livre: ' + remaining + '.';
            } else {
                textoStatus = 'Uso: ' + total + ' / ' + capacidade + ' itens (' + percent + '%).';
            }
        }
        atualizarBarraProgresso(percent, textoStatus);

        // Atualiza volumes atuais nos campos apenas para informação (não somar 2x)
        var itens = (config.items) || {};
        CAMPOS.forEach(function (campo) {
            var el = qs('estoque-' + campo);
            if (!el) return;
            el.value = 0; // campos representam NOVAS adições, sempre zero por padrão
            el.setAttribute('data-atual', itens[campo] || 0);
        });
        atualizarQuantidadesAtuais(itens);
        atualizarResumoVolumes();

        // Define modo do botão
        if (btn) {
            if (!config.configured) {
                btn.textContent = 'Salvar estoque inicial';
                btn.setAttribute('data-mode', 'setup');
            } else {
                btn.textContent = 'Adicionar ao estoque';
                btn.setAttribute('data-mode', 'add');
            }
        }
    }

    function montarPayload() {
        var selectCap = qs('estoque-capacidade');
        var capacidade = parseNonNegativeInt(selectCap && selectCap.value);
        function getQty(campo) {
            var span = qs('qty-estoque-' + campo);
            return span ? parseNonNegativeInt(span.textContent) : 0;
        }
        var payload = {
            capacity: capacidade,
            p45: getQty('p45'),
            p20: getQty('p20'),
            p13: getQty('p13'),
            p8: getQty('p8'),
            p5: getQty('p5'),
            agua: getQty('agua')
        };
        return payload;
    }

    function showFeedback(message, type) {
        // Reutiliza o modal de tema, se existir; caso contrário usa alert.
        try {
            if (typeof showTemaModal === 'function') {
                showTemaModal(message, type === 'error' ? 'erro' : 'ok');
                return;
            }
        } catch (e) {
            // ignora e cai no alert
        }
        alert(message);
    }

    function initEstoqueConfig() {
        var section = qs('estoque');
        if (!section) return;

        var form = qs('form-estoque-config');
        if (!form) return;

        var selectCap = qs('estoque-capacidade');
        if (selectCap) {
            selectCap.addEventListener('change', function () {
                estoqueCapacidadeAtual = parseNonNegativeInt(selectCap.value);
                atualizarPrevisaoUso();
            });
        }

        // Liga botões +/- aos campos hidden de estoque
        document.querySelectorAll('.estoque-plus, .estoque-minus').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var targetId = btn.getAttribute('data-target');
                if (!targetId) return;
                var hiddenInput = qs(targetId);
                var spanQty = null;
                if (targetId === 'estoque-p45') spanQty = qs('qty-estoque-p45');
                else if (targetId === 'estoque-p20') spanQty = qs('qty-estoque-p20');
                else if (targetId === 'estoque-p13') spanQty = qs('qty-estoque-p13');
                else if (targetId === 'estoque-p8') spanQty = qs('qty-estoque-p8');
                else if (targetId === 'estoque-p5') spanQty = qs('qty-estoque-p5');
                else if (targetId === 'estoque-agua') spanQty = qs('qty-estoque-agua');
                if (!hiddenInput || !spanQty) return;

                var atual = parseNonNegativeInt(hiddenInput.value);
                if (btn.classList.contains('estoque-plus')) {
                    atual += 1;
                } else {
                    atual = Math.max(0, atual - 1);
                }
                hiddenInput.value = String(atual);
                spanQty.textContent = String(atual);
                atualizarResumoVolumes();
            });
        });

        // Carrega configuração atual do backend
        fetch('/api/estoque/config')
            .then(function (resp) {
                if (!resp.ok) throw new Error('Erro ao buscar configuração de estoque');
                return resp.json();
            })
            .then(function (data) {
                aplicarConfigUI(data);
            })
            .catch(function (err) {
                console.warn('[estoqueConfig] falha ao carregar configuração', err);
            });

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            var btn = qs('estoque-submit-btn');
            var mode = (btn && btn.getAttribute('data-mode')) || 'setup';
            var payload = montarPayload();

            // Regra: no modo setup, volume inicial não pode ser 0
            var soma = payload.p45 + payload.p20 + payload.p13 + payload.p8 + payload.p5 + payload.agua;
            if (mode === 'setup' && soma <= 0) {
                showFeedback('Informe pelo menos um volume inicial para configurar o estoque.', 'error');
                return;
            }

            var url = mode === 'setup' ? '/api/estoque/setup' : '/api/estoque/add';

            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            })
                .then(function (resp) {
                    return resp.json().then(function (data) {
                        return { ok: resp.ok, status: resp.status, body: data };
                    });
                })
                .then(function (result) {
                    if (!result.ok) {
                        var msg = (result.body && result.body.error) || 'Falha ao salvar configuração de estoque.';
                        if (result.body && typeof result.body.remaining !== 'undefined') {
                            msg += ' Espaço restante: ' + result.body.remaining + ' itens.';
                        }
                        showFeedback(msg, 'error');
                        return;
                    }
                    showFeedback('Configuração de estoque salva com sucesso.', 'ok');
                    aplicarConfigUI({
                        configured: true,
                        capacity: result.body.capacity,
                        current_total: result.body.current_total,
                        percent: result.body.percent,
                        remaining: result.body.remaining,
                        items: result.body.items
                    });
                })
                .catch(function (err) {
                    console.error('[estoqueConfig] erro ao enviar configuração', err);
                    showFeedback('Erro inesperado ao salvar configuração de estoque.', 'error');
                });
        });
    }

    document.addEventListener('DOMContentLoaded', initEstoqueConfig);
})();
