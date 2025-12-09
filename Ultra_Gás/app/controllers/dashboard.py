from flask import Blueprint, render_template, session, redirect, url_for, jsonify, abort
from app import db
from app.models.estoque import Estoque
from app.models.clientes import Cliente
from app.models.entregas import Entrega
from app.models.color import Color
from app.models.users import User

# IMPORTANTE - ISOLAMENTO POR AMBIENTE NO DASHBOARD
# --------------------------------------------------
# Todas as rotas JSON deste módulo (listas, cards, métricas) devem:
#   - exigir session['user_id'] e session['enviroment'] válidos;
#   - filtrar sempre por enviroment == session['enviroment'] nas queries
#     de Entrega, Cliente, Estoque, etc.;
#   - nunca retornar dados de outros ambientes.
# Ao criar novas rotas de dashboard, siga este padrão.

# Nota: o limite máximo do estoque (capacidade) está definido em
# `app/models/estoque.py` como DEFAULT_CAPACITY (atualmente 250).
# A constraint no banco (ck_estoque_total_max) também impõe que a soma dos
# campos p45+p20+p13+p8+p5+agua não ultrapasse esse limite. Se quiser alterar
# a capacidade, atualize DEFAULT_CAPACITY e ajuste a constraint no modelo/banco.


dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


def _get_theme_vars():
    """Monta o dicionário de variáveis de tema para o usuário logado.

    Retorna algo como:
    {
      "cor-fundo": "#ffffff",
      "cor-texto": "#000000",
      ...
    }

    Usa User.tema + enviroment da sessão para buscar em Color.
    Se não encontrar nada, tenta fallback global (enviroment NULL).
    """
    # Valores padrão mínimos para evitar falta de chave no template
    defaults = {
        "cor-fundo": "#ffffff",
        "cor-texto": "#000000",
        "cor-botao-texto": "#000000",
        "cor-primaria": "#bbbbbb",
        "cor-secundaria": "#ffffff",
        "cor-botao": "#bbbbbb",
        "tran-02": "all 0.2s ease",
        "tran-03": "all 0.3s ease",
        "tran-04": "all 0.4s ease",
        "tran-05": "all 0.5s ease",
    }

    env = session.get('enviroment')
    user_id = session.get('user_id')
    tema = 'root'
    if user_id:
        user = User.query.get(user_id)
        if user and user.tema:
            tema = user.tema

    # 1) tenta buscar cores específicas do ambiente + tema do usuário
    cores = []
    if env:
        cores = Color.query.filter_by(enviroment=env, tema=tema).all()

    # 2) se não encontrar, tenta globais para o tema
    if not cores:
        cores = Color.query.filter(Color.enviroment.is_(None), Color.tema == tema).all()

    # 3) se ainda não encontrar nada, tenta globais do root
    if not cores:
        cores = Color.query.filter(Color.enviroment.is_(None), Color.tema == 'root').all()

    result = dict(defaults)
    for c in cores:
        valor = c.valor_atual or c.valor_padrao
        if not valor:
            continue
        result[c.nome_variavel] = valor

    return result


@dashboard_bp.route('/', methods=['GET'])
def show_dashboard():
    user_type = session.get('user_type')
    user_id = session.get('user_id')

    if not user_type or not user_id:
        return redirect(url_for('auth.index'))

    user_name = session.get('user_name', 'Usuário')
    theme_vars = _get_theme_vars()

    if user_type == 'admin':
        return render_template('dashboard_admin.html', user_name=user_name, theme_vars=theme_vars)
    elif user_type == 'ambiente':
        return render_template('ambienteUserSettings.html', user_name=user_name, theme_vars=theme_vars)
    else:
        return render_template('dashboard.html', user_name=user_name, theme_vars=theme_vars)


@dashboard_bp.route('/entrega-atual', methods=['GET'])
def get_entrega_atual():
    """Retorna lista de entregas atribuídas ao usuário logado (encarregado == nome) e ainda não entregues.

    Se não houver sessão ou nenhuma entrega, retorna fallback com um exemplo.
    """
    # Requer usuário autenticado
    user_id = session.get('user_id')
    user_name = session.get('user_name')
    env = session.get('enviroment')
    if not user_id or not user_name or not env:
        return abort(401)
    try:
        entregas = Entrega.query.filter(
            Entrega.encarregado == user_name,
            Entrega.entregue.is_(False),
            Entrega.enviroment == env
        ).all()
        return jsonify([e.to_dict() for e in entregas])
    except Exception:
        # Fallback: um exemplo com preco
        return jsonify([
            {
                'id': 999,
                'endereco': 'Rua Exemplo, 100',
                'destinatario': 'Destinatário Exemplo',
                'produto': 'p20:1, agua:1',
                'metodo_pagamento': 'pix',
                'encarregado': user_name,
                'entregue': False,
                'pago': False,
                'preco': '210'
            }
        ])


@dashboard_bp.route('/entregas-pendentes', methods=['GET'])
def get_entregas_pendentes():
    """Rota que retorna uma lista de entregas pendentes (dados simulados).

    Cada item contém os campos: endereco, destinatario
    """
    # Apenas usuários autenticados podem ver entregas pendentes
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return abort(401)

    try:
        # pendentes: encarregado vazio e entregue == False, apenas do mesmo enviroment
        entregas = Entrega.query.filter(
            Entrega.encarregado == '',
            Entrega.entregue.is_(False),
            Entrega.enviroment == env
        ).all()
        result = [e.to_dict() for e in entregas]
        return jsonify(result)
    except Exception:
        # Fallback inclui todos os campos, inclusive preco
        entregas = [
            {"endereco": "Rua São João, 340", "destinatario": "Fernanda", "produto": "agua:2, p45:1", "metodo_pagamento": "dinheiro", "encarregado": "", "entregue": False, "pago": False, "preco": "420"}
        ]
        return jsonify(entregas)


@dashboard_bp.route('/historico-entregas', methods=['GET'])
def get_historico_entregas():
    """Rota que retorna histórico de entregas (dados simulados).

    Cada item contém os campos: endereco, destinatario
    """
    # Apenas usuários autenticados podem ver histórico de entregas
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return abort(401)

    try:
        # histórico: entregue True e pago True, apenas do mesmo enviroment
        historico_db = Entrega.query.filter(
            Entrega.entregue.is_(True),
            Entrega.pago.is_(True),
            Entrega.enviroment == env
        ).all()
        return jsonify([e.to_dict() for e in historico_db])
    except Exception:
        historico = [
            {"endereco": "Rua das Flores, 123", "destinatario": "João", "produto": "p13:1", "metodo_pagamento": "pix", "encarregado": "Carlos", "entregue": True, "pago": True, "preco": "130"}
        ]
        return jsonify(historico)


@dashboard_bp.route('/clientes', methods=['GET'])
def get_clientes():
    """Rota que retorna uma lista de clientes (dados simulados).

    Cada item contém o campo: endereco
    """
    # Apenas usuários autenticados podem buscar a lista de clientes
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return abort(401)

    try:
        clientes = Cliente.query.filter_by(enviroment=env).all()
        result = [c.to_dict() for c in clientes]
        return jsonify(result)
    except Exception:
        # Se houver qualquer erro com o DB, usar fallback simples
        fallback = [{"endereco": "Rua das Flores, 123"}]
        return jsonify(fallback)


@dashboard_bp.route('/cards', methods=['GET'])
def get_dashboard_cards():
    """Rota que retorna os valores exibidos nos cartões da seção principal (dashboard-cards).

        Campos retornados (dinâmicos a partir de Entrega/Estoque):
            - pedidos_pendentes_num: número de entregas sem encarregado e entregue == False
            - vendas_do_dia_num: número de entregas do dia atual (data == hoje)
            - entregadores_em_rota_num: quantidade de encarregados distintos com entregas em aberto
            - status_estoque_percent_num: número (percentual) calculado a partir de Estoque
    """
    from datetime import date

    # Protege endpoint: requer usuário autenticado
    user_id = session.get('user_id')
    user_type = session.get('user_type')
    env = session.get('enviroment')
    if not user_id or not user_type or not env:
        return abort(401)

    # Valores default em caso de erro
    pedidos_pendentes = 0
    vendas_hoje = 0
    entregadores_rota = 0
    status_percent = 0

    # Calcula percent do estoque
    try:
        estoque = Estoque.query.filter_by(enviroment=env).first()
        if estoque:
            status_percent = estoque.percent()
    except Exception:
        status_percent = 0

    hoje_str = date.today().isoformat()

    try:
        # Pedidos pendentes (admin e entregador): entregas ainda não atribuídas (sem encarregado) e não entregues
        pedidos_pendentes = Entrega.query.filter(
            Entrega.encarregado == '',
            Entrega.entregue.is_(False),
            Entrega.enviroment == env
        ).count()

        # Vendas do dia (admin): quantidade de entregas criadas hoje
        vendas_hoje = Entrega.query.filter(
            Entrega.data == hoje_str,
            Entrega.enviroment == env
        ).count()

        # Entregadores em rota (admin): quantidade de encarregados distintos com entregas em aberto
        entregadores_rota = (
            db.session.query(Entrega.encarregado)
            .filter(
                Entrega.encarregado != '',
                Entrega.entregue.is_(False),
                Entrega.enviroment == env
            )
            .distinct()
            .count()
        )

        # Métricas por usuário logado (dashboard do entregador)
        user_name = session.get('user_name')
        if user_name:
            # Entrega atual: entregas atribuídas ao usuário e não entregues
            entregas_atual_usuario = Entrega.query.filter(
                Entrega.encarregado == user_name,
                Entrega.entregue.is_(False),
                Entrega.enviroment == env
            ).count()

            # Entregas concluídas: atribuídas ao usuário e marcadas como entregues
            entregas_concluidas_usuario = Entrega.query.filter(
                Entrega.encarregado == user_name,
                Entrega.entregue.is_(True),
                Entrega.enviroment == env
            ).count()
        else:
            entregas_atual_usuario = 0
            entregas_concluidas_usuario = 0
    except Exception:
        # Em caso de erro com a tabela de entregas, mantém zeros
        pedidos_pendentes = pedidos_pendentes or 0
        vendas_hoje = vendas_hoje or 0
        entregadores_rota = entregadores_rota or 0
        entregas_atual_usuario = 0
        entregas_concluidas_usuario = 0

    data = {
        "pedidos_pendentes_num": int(pedidos_pendentes or 0),
        "vendas_do_dia_num": int(vendas_hoje or 0),
        "entregadores_em_rota_num": int(entregadores_rota or 0),
        "status_estoque_percent_num": int(status_percent or 0),
        "entregas_atual_usuario_num": int(entregas_atual_usuario or 0),
        "entregas_concluidas_usuario_num": int(entregas_concluidas_usuario or 0)
    }
    return jsonify(data)


@dashboard_bp.route('/estoque-cards', methods=['GET'])
def get_estoque_cards():
    """Rota que retorna os valores exibidos nos cartões da seção Estoque/Financeiro (simulados).

    Campos retornados:
      - vendas_do_dia_num: soma de preco das entregas com data == hoje
      - pagamentos: { recebidos_num, pendentes_num } em centavos/reais inteiros
    """
    # Protege endpoint: requer usuário autenticado
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return abort(401)

    # Calcula valores reais a partir da tabela Entrega.
    try:
        from datetime import date
        hoje_str = date.today().isoformat()  # yyyy-mm-dd

        # Vendas do dia: todas as entregas criadas hoje (independente de pago/entregue), apenas do mesmo enviroment
        vendas_hoje = Entrega.query.filter(
            Entrega.data == hoje_str,
            Entrega.enviroment == env
        ).all()
        vendas_total = 0
        for e in vendas_hoje:
            try:
                vendas_total += int(e.preco or 0)
            except ValueError:
                # ignora preços inválidos
                pass

        # Total recebido: entregas pagas (pago=True)
        recebidas = Entrega.query.filter(
            Entrega.pago.is_(True),
            Entrega.enviroment == env
        ).all()
        recebidos_total = 0
        for e in recebidas:
            try:
                recebidos_total += int(e.preco or 0)
            except ValueError:
                # Ignora valores não numéricos
                pass

        # Total pendente: entregas já entregues mas não pagas (entregue=True, pago=False) Versão antiga
        # Total pendente: pedido realizado, mas ainda não pago (pago=False) Versão atual
        pendentes = Entrega.query.filter(
            Entrega.pago.is_(False),
            Entrega.enviroment == env
        ).all()
        pendentes_total = 0
        for e in pendentes:
            try:
                pendentes_total += int(e.preco or 0)
            except ValueError:
                pass

        data = {
            "vendas_do_dia_num": vendas_total,
            "pagamentos": {
                "recebidos_num": recebidos_total,
                "pendentes_num": pendentes_total
            }
        }
    except Exception:
        # Fallback para não quebrar o dashboard se ocorrer erro inesperado
        data = {
            "vendas_do_dia_num": 1000,
            "pagamentos": {
                "recebidos_num": 0,
                "pendentes_num": 0
            }
        }
    return jsonify(data)


@dashboard_bp.route('/pagamentos-pendentes', methods=['GET'])
def get_pagamentos_pendentes():
    """Retorna entregas já entregues mas ainda não pagas (entregue=True, pago=False)."""
    # Protege endpoint: requer usuário autenticado
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return abort(401)

    try:
        pendentes = Entrega.query.filter(
            Entrega.entregue.is_(True),
            Entrega.pago.is_(False),
            Entrega.enviroment == env
        ).all()
        return jsonify([e.to_dict() for e in pendentes])
    except Exception:
        # Fallback com exemplo
        return jsonify([
            {
                'id': 1001,
                'endereco': 'Rua Exemplo Pagamento, 50',
                'destinatario': 'Cliente Pagamento',
                'produto': 'p20:1',
                'metodo_pagamento': 'pix',
                'encarregado': 'Equipe A',
                'entregue': True,
                'pago': False,
                'preco': '200'
            }
        ])
