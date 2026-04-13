from flask import Blueprint, jsonify, request, session, abort


# IMPORTANTE - ISOLAMENTO POR AMBIENTE
# -------------------------------------------------
# Regra geral deste módulo:
#   - Todo dado GRAVADO que pertença a uma "instância" lógica
#     (clientes, entregas, estoque, temas, usuários de ambiente)
#     deve receber enviroment=session['enviroment'] no momento da criação.
#   - Todo dado CONSULTADO para front-end (listas, cards, métricas,
#     gráficos) deve sempre filtrar por enviroment == session['enviroment'].
#   - Se não houver enviroment na sessão, os endpoints que dependem
#     disso devem responder com erro 401 e NUNCA retornar dados de
#     outros ambientes.
# Ao adicionar novas rotas/queries neste arquivo, siga este padrão.

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/estoque', methods=['GET'])
def api_estoque():
    """Retorna dados para o gráfico de estoque.

    Estrutura retornada:
    {
      "summary": { "statusText": "..." },
      "pie": { "p45": 10, "p20": 5, ... },
      "meta": { "capacity": 500, "total": 120, "percent": 24 }
    }

    Também é usada como base para a sessão de configuração de estoque.
    """
    # Requer usuário autenticado para acessar informações de estoque
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return jsonify({'error': 'Usuário não autenticado ou ambiente não definido'}), 401

    from app.models.estoque import Estoque, DEFAULT_CAPACITY

    # Tenta buscar dados reais do banco
    try:
        # Estoque apenas do mesmo enviroment do usuário
        estoque = Estoque.query.filter_by(enviroment=env).first()
        if estoque:
            capacidade = int(estoque.capacity or DEFAULT_CAPACITY)
            total = estoque.total()
            percent = estoque.percent(capacidade)
            data = {
                "summary": {
                    "statusText": f"Estoque: {total} / {capacidade} itens ({percent}%)"
                },
                "pie": estoque.to_pie(),
                "meta": {
                    "capacity": capacidade,
                    "total": total,
                    "percent": percent
                }
            }
            return jsonify(data)
    except Exception:
        # se houver qualquer problema com o DB, cai no mock abaixo
        pass

    # Fallback mock (sem dados reais de capacidade)
    data = {
        "summary": {"statusText": "Mock: estoque equilibrado — itens com baixa quantidade: 3"},
        "pie": {
            "p45": 20,
            "p20": 20,
            "p13": 13,
            "p8": 8,
            "p5": 5,
            "agua": 15
        },
        "meta": {
            "capacity": DEFAULT_CAPACITY,
            "total": 0,
            "percent": 0
        }
    }
    return jsonify(data)


@api_bp.route('/estoque/config', methods=['GET'])
def api_estoque_config():
    """Retorna configuração de estoque para o ambiente do usuário.

    Usado pela dashboard ambienteUserSettings para decidir entre modo
    inicial (setup) e modo recorrente (apenas adições).
    """
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return jsonify({'error': 'Usuário não autenticado ou ambiente não definido'}), 401

    from app.models.estoque import Estoque, DEFAULT_CAPACITY

    capacidade_niveis = [250, 500, 750, 1000]

    estoque = Estoque.query.filter_by(enviroment=env).first()
    if not estoque:
        return jsonify({
            'configured': False,
            'capacity_levels': capacidade_niveis,
            'capacity': None,
            'current_total': 0,
            'max_capacity': None,
            'remaining': None,
            'percent': 0,
            'items': {
                'p45': 0,
                'p20': 0,
                'p13': 0,
                'p8': 0,
                'p5': 0,
                'agua': 0,
            }
        })

    capacidade = int(estoque.capacity or DEFAULT_CAPACITY)
    total = estoque.total()
    percent = estoque.percent(capacidade)
    remaining = max(0, capacidade - total)

    return jsonify({
        'configured': True,
        'capacity_levels': capacidade_niveis,
        'capacity': capacidade,
        'current_total': total,
        'max_capacity': capacidade,
        'remaining': remaining,
        'percent': percent,
        'items': estoque.to_pie(),
    })


@api_bp.route('/estoque/setup', methods=['POST'])
def api_estoque_setup():
    """Configuração inicial de estoque para um ambiente.

    Espera JSON:
    {
      "capacity": 250|500|750|1000,
      "p45": int,
      "p20": int,
      "p13": int,
      "p8": int,
      "p5": int,
      "agua": int
    }
    Só pode ser chamado se ainda não existir registro de estoque para o enviroment.
    """
    from app import db
    from app.models.estoque import Estoque, DEFAULT_CAPACITY

    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return jsonify({'error': 'Usuário não autenticado ou ambiente não definido'}), 401

    # Se já existir estoque para este ambiente, deve usar o endpoint de adição
    if Estoque.query.filter_by(enviroment=env).first():
        return jsonify({'error': 'Estoque já configurado para este ambiente'}), 400

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    if not isinstance(data, dict):
        return jsonify({'error': 'Payload inválido'}), 400

    capacidade_niveis = [250, 500, 750, 1000]
    capacidade = int(data.get('capacity') or 0)
    if capacidade not in capacidade_niveis:
        return jsonify({'error': 'Capacidade inválida'}), 400

    # Normaliza valores de cada tipo (não negativos)
    def to_int(value):
        try:
            v = int(value)
            return v if v >= 0 else 0
        except Exception:
            return 0

    p45 = to_int(data.get('p45'))
    p20 = to_int(data.get('p20'))
    p13 = to_int(data.get('p13'))
    p8 = to_int(data.get('p8'))
    p5 = to_int(data.get('p5'))
    agua = to_int(data.get('agua'))

    total = p45 + p20 + p13 + p8 + p5 + agua
    if total > capacidade:
        return jsonify({'error': 'Volume inicial excede a capacidade selecionada'}), 400

    # Também garante que nunca ultrapasse o limite físico global
    if total > DEFAULT_CAPACITY:
        return jsonify({'error': f'Volume inicial não pode ultrapassar {DEFAULT_CAPACITY} itens no total'}), 400

    try:
        estoque = Estoque(
            p45=p45,
            p20=p20,
            p13=p13,
            p8=p8,
            p5=p5,
            agua=agua,
            enviroment=env,
            capacity=capacidade,
        )
        db.session.add(estoque)
        db.session.commit()

        percent = estoque.percent(capacidade)
        remaining = max(0, capacidade - estoque.total())

        return jsonify({
            'ok': True,
            'capacity': capacidade,
            'current_total': estoque.total(),
            'percent': percent,
            'remaining': remaining,
            'items': estoque.to_pie(),
        }), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao configurar estoque', 'detail': str(e)}), 500


@api_bp.route('/estoque/add', methods=['POST'])
def api_estoque_add():
    """Adiciona volumes ao estoque já existente do ambiente.

    Mesmo payload de /estoque/setup, porém os valores são incrementais.
    """
    from app import db
    from app.models.estoque import Estoque, DEFAULT_CAPACITY

    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return jsonify({'error': 'Usuário não autenticado ou ambiente não definido'}), 401

    estoque = Estoque.query.filter_by(enviroment=env).first()
    if not estoque:
        return jsonify({'error': 'Estoque ainda não foi configurado para este ambiente'}), 400

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    if not isinstance(data, dict):
        return jsonify({'error': 'Payload inválido'}), 400

    def to_int(value):
        try:
            v = int(value)
            return v if v >= 0 else 0
        except Exception:
            return 0

    add_p45 = to_int(data.get('p45'))
    add_p20 = to_int(data.get('p20'))
    add_p13 = to_int(data.get('p13'))
    add_p8 = to_int(data.get('p8'))
    add_p5 = to_int(data.get('p5'))
    add_agua = to_int(data.get('agua'))

    # Calcula novos valores propostos
    new_p45 = (estoque.p45 or 0) + add_p45
    new_p20 = (estoque.p20 or 0) + add_p20
    new_p13 = (estoque.p13 or 0) + add_p13
    new_p8 = (estoque.p8 or 0) + add_p8
    new_p5 = (estoque.p5 or 0) + add_p5
    new_agua = (estoque.agua or 0) + add_agua

    capacidade = int(estoque.capacity or DEFAULT_CAPACITY)
    total_novo = new_p45 + new_p20 + new_p13 + new_p8 + new_p5 + new_agua

    if total_novo > capacidade:
        remaining = max(0, capacidade - estoque.total())
        return jsonify({
            'error': 'Adição excede a capacidade máxima do estoque',
            'remaining': remaining
        }), 400

    # Também respeita o limite físico global do modelo
    if total_novo > DEFAULT_CAPACITY:
        remaining_global = max(0, DEFAULT_CAPACITY - estoque.total())
        return jsonify({
            'error': f'Adição excede o limite físico global de {DEFAULT_CAPACITY} itens',
            'remaining': remaining_global
        }), 400

    try:
        estoque.p45 = new_p45
        estoque.p20 = new_p20
        estoque.p13 = new_p13
        estoque.p8 = new_p8
        estoque.p5 = new_p5
        estoque.agua = new_agua

        db.session.commit()

        total = estoque.total()
        percent = estoque.percent(capacidade)
        remaining = max(0, capacidade - total)

        return jsonify({
            'ok': True,
            'capacity': capacidade,
            'current_total': total,
            'percent': percent,
            'remaining': remaining,
            'items': estoque.to_pie(),
        })
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao adicionar ao estoque', 'detail': str(e)}), 500


@api_bp.route('/pedidos', methods=['POST'])
def api_pedidos():
    """Recebe um pedido do front-end, valida e grava como uma Entrega.

    Aceita payloads flexíveis:
      - já formatado: { endereco, destinatario, produto, metodo_pagamento }
      - ou raw: { endereco, cliente, produtos: [{nome,quantidade}], pagamentos: [metodo] }

    Retorna 201 com o registro salvo ou 400/500 em erro.
    """
    # Requer usuário autenticado para registrar pedidos
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return jsonify({'error': 'Usuário não autenticado ou ambiente não definido'}), 401

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    if not isinstance(data, dict):
        return jsonify({'error': 'Payload inválido'}), 400

    endereco = data.get('endereco') or data.get('rua')
    destinatario = data.get('destinatario') or data.get('cliente')

    # normalizar produto: pode vir como string ou como lista de objetos
    produto = data.get('produto')
    if not produto and isinstance(data.get('produtos'), list):
        parts = []
        for p in data.get('produtos'):
            nome = p.get('nome') if isinstance(p, dict) else None
            quantidade = p.get('quantidade') if isinstance(p, dict) else None
            if nome and quantidade:
                parts.append(f"{nome}:{quantidade}")
        produto = ', '.join(parts) if parts else None

    # normalizar método de pagamento (single)
    metodo = data.get('metodo_pagamento')
    if not metodo and isinstance(data.get('pagamentos'), list):
        metodo = data.get('pagamentos')[0] if len(data.get('pagamentos')) > 0 else None

    # validações básicas
    if not endereco or not destinatario:
        return jsonify({'error': 'Campos obrigatórios ausentes: endereco e destinatario'}), 400
    if not produto:
        return jsonify({'error': 'Nenhum produto informado'}), 400

    allowed = {'pix', 'a_prazo', 'cartao', 'dinheiro'}
    if metodo and metodo not in allowed:
        return jsonify({'error': 'metodo_pagamento inválido'}), 400

    # grava no banco
    try:
        from app import db
        from app.models.entregas import Entrega

        preco = data.get('preco') or ''

        entrega = Entrega(
            endereco=endereco,
            destinatario=destinatario,
            produto=produto,
            metodo_pagamento=metodo,
            encarregado='',   # inicia vazio
            entregue=False,   # inicia não entregue
            pago=False,        # inicia não pago
            preco=preco,       # valor calculado pelo front-end
            enviroment=env,    # isola a entrega no ambiente do criador
        )
        db.session.add(entrega)
        db.session.commit()

        return jsonify({'ok': True, 'entrega': entrega.to_dict()}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao gravar entrega', 'detail': str(e)}), 500


@api_bp.route('/financeiro', methods=['GET'])
def api_financeiro():
    """Retorna dados para o gráfico financeiro com base nas entregas.

    Conta quantas entregas (entregue=True) foram realizadas por cada método de pagamento.
    Estrutura retornada compatível com Chart.js (labels + datasets).
    """
    from sqlalchemy import func

    # Apenas usuários autenticados podem acessar dados financeiros
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return jsonify({'error': 'Usuário não autenticado ou ambiente não definido'}), 401
    try:
        from app import db
        from app.models.entregas import Entrega

        # Métodos conhecidos e ordem fixa
        metodos_ordem = ["a_prazo", "pix", "cartao", "dinheiro"]
        counts_map = {m: 0 for m in metodos_ordem}

        resultados = db.session.query(Entrega.metodo_pagamento, func.count(Entrega.id)) \
            .filter(
                Entrega.metodo_pagamento.isnot(None),
                Entrega.entregue.is_(True),
                Entrega.enviroment == env
            ) \
            .group_by(Entrega.metodo_pagamento).all()

        for metodo, qtd in resultados:
            if metodo in counts_map:
                counts_map[metodo] = qtd

        data = {
            "labels": ["A prazo", "Pix", "Cartão", "Dinheiro"],
            "datasets": [
                {
                    "data": [counts_map["a_prazo"], counts_map["pix"], counts_map["cartao"], counts_map["dinheiro"]],
                    "backgroundColor": ["#4dc9f6", "#f67019", "#f53794", "#537bc4"]
                }
            ]
        }
        return jsonify(data)
    except Exception:
        # Fallback simples se ocorrer erro com o DB
        data = {
            "labels": ["A prazo", "Pix", "Cartão", "Dinheiro"],
            "datasets": [
                {
                    "data": [0, 0, 0, 0],
                    "backgroundColor": ["#4dc9f6", "#f67019", "#f53794", "#537bc4"]
                }
            ],
            "summary": {"status": "Falha ao acessar entregas; retornando zeros."}
        }
        return jsonify(data)


@api_bp.route('/clientes', methods=['POST'])
def api_clientes_create():
    """Cria um novo cliente a partir do payload { endereco: '...' }.

    Retorna 201 com o cliente criado ou 400/500 em caso de falha.
    """
    # Requer usuário autenticado para criar clientes
    env = session.get('enviroment')
    if not session.get('user_id') or not env:
        return jsonify({'error': 'Usuário não autenticado ou ambiente não definido'}), 401

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    if not isinstance(data, dict):
        return jsonify({'error': 'Payload inválido'}), 400

    endereco = data.get('endereco')
    if not endereco or not str(endereco).strip():
        return jsonify({'error': 'Campo endereco é obrigatório'}), 400

    try:
        from app import db
        from app.models.clientes import Cliente

        # enviroment herdado do usuário que está cadastrando o cliente (já validado acima)
        cliente = Cliente(endereco=str(endereco).strip(), enviroment=env)
        db.session.add(cliente)
        db.session.commit()

        return jsonify({'ok': True, 'cliente': cliente.to_dict()}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao criar cliente', 'detail': str(e)}), 500


@api_bp.route('/entregas/<int:entrega_id>/confirm', methods=['POST'])
def api_entrega_confirm(entrega_id):
    """Marca uma entrega como entregue (entregue=True). Retorna registro atualizado."""
    # Requer usuário autenticado para confirmar entregas
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    try:
        from app import db
        from app.models.entregas import Entrega
        entrega = Entrega.query.get(entrega_id)
        if not entrega:
            return jsonify({'error': 'Entrega não encontrada'}), 404
        entrega.entregue = True
        db.session.commit()
        return jsonify({'ok': True, 'entrega': entrega.to_dict()})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao confirmar entrega', 'detail': str(e)}), 500


@api_bp.route('/entregas/<int:entrega_id>/retirar', methods=['POST'])
def api_entrega_retirar(entrega_id):
    """Atribui a entrega ao usuário logado (encarregado) e baixa o estoque.

    Momento da baixa de estoque: quando o usuário "retira" o pedido para entrega.

    Regras:
      - Requer sessão com user_name.
      - Se entrega já tiver encarregado diferente, retorna 409.
      - Se encarregado estiver vazio ou igual ao usuário, tenta atribuir e baixar estoque.
      - Campo produto da entrega é uma string no formato "agua:2, p45:1".
    """

    def _parse_produtos(produto_str):
        """Converte a string de produtos em um dicionário de quantidades.

        Exemplo de entrada: "agua:2, p45:1" -> {"agua": 2, "p45": 1}
        Ignora partes vazias e quantidades inválidas (<=0).
        """
        result = {}
        if not produto_str:
            return result
        for part in produto_str.split(','):
            part = part.strip()
            if not part:
                continue
            if ':' not in part:
                continue
            tipo, qtd_str = part.split(':', 1)
            tipo = (tipo or '').strip().lower()
            qtd_str = (qtd_str or '').strip()
            if not tipo or not qtd_str:
                continue
            try:
                qtd = int(qtd_str)
            except ValueError:
                continue
            if qtd <= 0:
                continue
            # acumula se houver repetição do mesmo tipo
            result[tipo] = result.get(tipo, 0) + qtd
        return result

    user_name = session.get('user_name')
    env = session.get('enviroment')
    if not user_name or not env:
        return jsonify({'error': 'Usuário não autenticado ou ambiente não definido'}), 401
    try:
        from app import db
        from app.models.entregas import Entrega
        from app.models.estoque import Estoque

        entrega = Entrega.query.get(entrega_id)
        if not entrega:
            return jsonify({'error': 'Entrega não encontrada'}), 404

        # Se já atribuída a outro usuário, não permite retirar
        if entrega.encarregado and entrega.encarregado != user_name:
            return jsonify({'error': 'Entrega já atribuída', 'encarregado': entrega.encarregado}), 409

        # Carrega registro de estoque APENAS do mesmo enviroment do usuário
        estoque = Estoque.query.filter_by(enviroment=env).first()
        if not estoque:
            return jsonify({'error': 'Estoque não configurado para este ambiente'}), 500

        # Se a entrega já estiver atribuída ao mesmo usuário, não baixa estoque de novo
        if entrega.encarregado == user_name:
            return jsonify({'ok': True, 'entrega': entrega.to_dict(), 'warning': 'Entrega já atribuída a este usuário. Nenhuma nova baixa de estoque executada.'})

        itens = _parse_produtos(entrega.produto)

        # Mapeia chaves de produto para campos do modelo Estoque
        campo_map = {
            'p45': 'p45',
            'p20': 'p20',
            'p13': 'p13',
            'p8': 'p8',
            'p5': 'p5',
            'agua': 'agua',
        }

        # Validação de estoque suficiente
        for tipo, qtd in itens.items():
            campo = campo_map.get(tipo)
            if not campo:
                # Produto desconhecido, ignora na baixa mas avisa
                continue
            atual = getattr(estoque, campo) or 0
            if atual < qtd:
                return jsonify({'error': f'Estoque insuficiente para {tipo}. Disponível: {atual}, necessário: {qtd}'}), 400

        # Aplica baixa
        for tipo, qtd in itens.items():
            campo = campo_map.get(tipo)
            if not campo:
                continue
            atual = getattr(estoque, campo) or 0
            setattr(estoque, campo, atual - qtd)

        # Atribui entrega ao usuário
        entrega.encarregado = user_name

        db.session.commit()
        return jsonify({'ok': True, 'entrega': entrega.to_dict()})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao retirar entrega', 'detail': str(e)}), 500


@api_bp.route('/entregas/<int:entrega_id>/pagar', methods=['POST'])
def api_entrega_pagar(entrega_id):
    """Marca uma entrega como paga (pago=True) somente se já estiver entregue."""
    # Requer usuário autenticado para registrar pagamento
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    try:
        from app import db
        from app.models.entregas import Entrega
        entrega = Entrega.query.get(entrega_id)
        if not entrega:
            return jsonify({'error': 'Entrega não encontrada'}), 404
        if not entrega.entregue:
            return jsonify({'error': 'Entrega ainda não marcada como entregue'}), 400
        entrega.pago = True
        db.session.commit()
        return jsonify({'ok': True, 'entrega': entrega.to_dict()})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao marcar pagamento', 'detail': str(e)}), 500


@api_bp.route('/themes', methods=['GET'])
def api_list_themes():
    """Lista as variáveis de cor agrupadas por tema.

    Retorno:
    {
      "root": {"cor-fundo": "#ffffff", ...},
      "rosa": {"cor-fundo": "#ffcbcd", ...},
      ...
    }
    Usa valor_atual se existir, senão valor_padrao.
    As cores são filtradas pelo campo enviroment, que deve
    corresponder ao enviroment do usuário logado. Se não houver
    usuário logado ou nenhuma cor para aquele enviroment, volta
    para as cores globais (enviroment NULL).
    """
    # Requer usuário autenticado para consultar temas do ambiente
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    try:
        from app.models.color import Color

        temas = {}

        # Ambiente do usuário logado
        env = session.get('enviroment')

        # 1) tenta buscar cores específicas do ambiente
        cores = []
        if env:
            cores = Color.query.filter_by(enviroment=env).all()

        # 2) se não encontrou cores específicas, usa cores globais (enviroment NULL)
        if not cores:
            cores = Color.query.filter(Color.enviroment.is_(None)).all()

        for c in cores:
            tema = c.tema or 'root'
            if tema not in temas:
                temas[tema] = {}
            temas[tema][c.nome_variavel] = c.valor_atual or c.valor_padrao

        return jsonify(temas)
    except Exception as e:
        return jsonify({'error': 'Falha ao buscar temas', 'detail': str(e)}), 500


@api_bp.route('/themes/<tema>/apply', methods=['POST'])
def api_apply_theme(tema):
    """Define o tema atual na sessão do usuário.

    O front-end deve ler esse tema e requisitar /api/themes
    para obter as variáveis e aplicá-las via CSS custom properties.
    """
    # Requer usuário autenticado para aplicar tema na sessão
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    tema = (tema or '').strip().lower()
    if not tema:
        return jsonify({'error': 'Tema inválido'}), 400

    # Apenas grava na sessão; a aplicação do tema é via JS/CSS.
    session['current_theme'] = tema
    return jsonify({'ok': True, 'tema': tema})


@api_bp.route('/themes/custom', methods=['POST'])
def api_create_custom_theme():
    """Cria ou atualiza um tema para o ambiente do usuário de ambiente.

    Espera JSON:
    {
      "tema": "nome_tema",
      "cores": {
         "cor-fundo": "#ffffff",
         ...
      }
    }
    Remove entradas anteriores com mesmo (enviroment, tema) e recria.
    """
    from app import db
    from app.models.color import Color

    # Requer usuário autenticado e ambiente definido na sessão
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    env = session.get('enviroment')
    if not env:
        return jsonify({'error': 'Ambiente não encontrado na sessão'}), 401

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    tema = (data.get('tema') or '').strip()
    cores = data.get('cores') or {}

    if not tema:
        return jsonify({'error': 'Campo tema é obrigatório'}), 400
    if not isinstance(cores, dict) or not cores:
        return jsonify({'error': 'Campo cores é obrigatório'}), 400

    try:
        # Remove qualquer tema anterior com mesmo nome para este ambiente
        Color.query.filter_by(enviroment=env, tema=tema).delete()

        # Cria novas entradas para cada variável de cor
        novos = []
        for nome_var, valor in cores.items():
            if not valor:
                continue
            novos.append(
                Color(
                    nome_variavel=nome_var,
                    valor_padrao=str(valor),
                    tema=tema,
                    enviroment=env,
                )
            )

        if not novos:
            return jsonify({'error': 'Nenhuma cor válida informada'}), 400

        db.session.add_all(novos)
        db.session.commit()
        return jsonify({'ok': True, 'tema': tema}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao salvar tema', 'detail': str(e)}), 500


@api_bp.route('/themes/list-names', methods=['GET'])
def api_list_theme_names():
    """Lista apenas os nomes de tema disponíveis para o ambiente do usuário."""
    from app import db
    from app.models.color import Color

    # Requer usuário autenticado para listar temas do ambiente
    if not session.get('user_id'):
        return jsonify({'temas': []}), 401

    env = session.get('enviroment')
    if not env:
        return jsonify({'temas': []})

    try:
        rows = (
            db.session.query(Color.tema)
            .filter(Color.enviroment == env)
            .distinct()
            .all()
        )
        temas = sorted({r[0] for r in rows if r[0]})
        return jsonify({'temas': list(temas)})
    except Exception as e:
        return jsonify({'error': 'Falha ao listar temas', 'detail': str(e)}), 500


@api_bp.route('/themes/apply-to-env', methods=['POST'])
def api_apply_theme_to_env():
    """Define o tema para todos os usuários de um mesmo enviroment.

    Espera JSON: { "tema": "nome_tema" }
    Atualiza User.tema de todos os usuários com User.enviroment == env atual.
    """
    from app import db
    from app.models.users import User

    # Requer usuário autenticado e ambiente definido
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    env = session.get('enviroment')
    if not env:
        return jsonify({'error': 'Ambiente não encontrado na sessão'}), 401

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    tema = (data.get('tema') or '').strip()
    if not tema:
        return jsonify({'error': 'Campo tema é obrigatório'}), 400

    try:
        db.session.query(User).filter(User.enviroment == env).update({User.tema: tema})
        db.session.commit()
        # Também salva na sessão do usuário atual
        session['current_theme'] = tema
        return jsonify({'ok': True, 'tema': tema})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao aplicar tema ao ambiente', 'detail': str(e)}), 500


@api_bp.route('/current-theme', methods=['GET'])
def api_current_theme():
    """Retorna o tema atual do usuário (coluna User.tema), com fallback para 'root'."""
    from app.models.users import User

    user_id = session.get('user_id')
    if not user_id:
        # se não logado, usa tema salvo na sessão (se houver) ou root
        tema = session.get('current_theme') or 'root'
        return jsonify({'tema': tema})

    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'tema': 'root'})
        return jsonify({'tema': user.tema or 'root'})
    except Exception:
        return jsonify({'tema': 'root'})


@api_bp.route('/users', methods=['POST'])
def api_create_user():
    """Cria um novo usuário (admin ou entregador) no mesmo ambiente do criador.

    Espera JSON:
    {
      "name": "...",
      "email": "...",
      "password": "...",
      "user_type": "admin" | "user"
    }

    - enviroment é herdado da sessão de quem está criando
    - tema recebe o tema atual do ambiente (User.tema do criador ou 'root')
    """
    from werkzeug.security import generate_password_hash
    from app import db
    from app.models.users import User

    # Requer usuário autenticado
    creator_id = session.get('user_id')
    env = session.get('enviroment')
    if not creator_id or not env:
        return jsonify({'error': 'Usuário não autenticado ou ambiente não definido'}), 401

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = (data.get('password') or '').strip()
    user_type = (data.get('user_type') or '').strip()

    if not name or not email or not password or user_type not in ('admin', 'user'):
        return jsonify({'error': 'Campos obrigatórios inválidos'}), 400

    # Verifica se já existe usuário com este e-mail
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'E-mail já cadastrado'}), 400

    # Tema do novo usuário: herda do criador, com fallback
    creator = User.query.get(creator_id)
    tema_inicial = 'root'
    if creator and creator.tema:
        tema_inicial = creator.tema
    else:
        # fallback: se sessão tiver tema atual, usa-o
        tema_inicial = session.get('current_theme') or 'root'

    try:
        novo = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            enviroment=env,
            user_type=user_type,
            tema=tema_inicial,
        )
        db.session.add(novo)
        db.session.commit()

        return jsonify({'ok': True, 'user': {
            'id': novo.id,
            'name': novo.name,
            'email': novo.email,
            'enviroment': novo.enviroment,
            'user_type': novo.user_type,
            'tema': novo.tema,
        }}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao criar usuário', 'detail': str(e)}), 500
